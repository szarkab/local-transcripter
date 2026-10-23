import AppKit
import UniformTypeIdentifiers

struct Configuration: Decodable {
    let worker: String
    let tools: String
}

struct ModelSetupOutput: Decodable {
    let ready: Bool
    let note: String?
}

struct ProcessingStatus: Decodable {
    let message: String
    let seconds: Double?
    let total: Double?
}

struct RecognitionOutput: Decodable {
    let transcript: String
    let markdown: String
    let repetition_warnings: Int
    let quality_note: String?
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private enum Work { case checking, preparing, transcribing(URL) }
    private var work = Work.checking
    private var modelReady = false
    private let setup = NSButton(title: "Modell letöltése (3,2 GB)…", target: nil, action: nil)
    private var dataDirectory: URL {
        // Keep the existing data directory so installed models survive the visible app rename.
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Helyi leirat", isDirectory: true)
    }
    private var window: NSWindow!
    private let status = NSTextField(wrappingLabelWithString: "Válassz egy M4A-, MP3- vagy WAV-hangfelvételt az átíráshoz.")
    private let filename = NSTextField(labelWithString: "Nincs kiválasztott hangfelvétel")
    private let choose = NSButton(title: "Hangfelvétel kiválasztása…", target: nil, action: nil)
    private let save = NSButton(title: "Leirat mentése…", target: nil, action: nil)
    private let cancel = NSButton(title: "Megszakítás", target: nil, action: nil)
    private var statusTimer: Timer?
    private var cancelling = false
    private let speakers = NSButton(checkboxWithTitle: "Beszélők elkülönítése", target: nil, action: nil)
    private let language = NSPopUpButton(frame: .zero, pullsDown: false)
    private let format = NSPopUpButton(frame: .zero, pullsDown: false)
    private let progress = NSProgressIndicator()
    private let progressBar = NSProgressIndicator()
    private let progressDetail = NSTextField(labelWithString: "")
    private var transcript: URL?
    private var markdown: URL?
    private var source: URL?
    private var process: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let applicationItem = NSMenuItem()
        menu.addItem(applicationItem)
        let applicationMenu = NSMenu()
        let about = applicationMenu.addItem(withTitle: "A Local Transcripter névjegye", action: #selector(showAbout), keyEquivalent: "")
        about.target = self
        let licenses = applicationMenu.addItem(withTitle: "Licencek és források…", action: #selector(showLicenses), keyEquivalent: "")
        licenses.target = self
        applicationMenu.addItem(.separator())
        applicationMenu.addItem(withTitle: "Kilépés", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        applicationItem.submenu = applicationMenu
        NSApp.mainMenu = menu
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 760, height: 590),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Local Transcripter"
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 720, height: 560)
        let backdrop = NSVisualEffectView()
        backdrop.material = .windowBackground
        backdrop.blendingMode = .behindWindow
        backdrop.state = .active
        window.contentView = backdrop
        let title = NSTextField(labelWithString: "Local Transcripter")
        title.font = .systemFont(ofSize: 27, weight: .semibold)
        let detail = NSTextField(wrappingLabelWithString: "Magyar és angol leirat, helyben a Maceden.\nWhisper large-v3 · Apple Silicon")
        detail.textColor = .secondaryLabelColor
        let brandTile = NSView()
        brandTile.wantsLayer = true
        brandTile.layer?.backgroundColor = NSColor.white.cgColor
        brandTile.layer?.cornerRadius = 15
        brandTile.layer?.borderColor = NSColor.black.withAlphaComponent(0.08).cgColor
        brandTile.layer?.borderWidth = 1
        brandTile.translatesAutoresizingMaskIntoConstraints = false
        let brand = NSImageView()
        brand.image = Bundle.main.url(forResource: "BrandMark", withExtension: "svg").flatMap(NSImage.init(contentsOf:))
        brand.imageScaling = .scaleProportionallyUpOrDown
        brand.translatesAutoresizingMaskIntoConstraints = false
        brandTile.addSubview(brand)
        NSLayoutConstraint.activate([
            brandTile.widthAnchor.constraint(equalToConstant: 66),
            brandTile.heightAnchor.constraint(equalToConstant: 66),
            brand.leadingAnchor.constraint(equalTo: brandTile.leadingAnchor, constant: 10),
            brand.trailingAnchor.constraint(equalTo: brandTile.trailingAnchor, constant: -10),
            brand.topAnchor.constraint(equalTo: brandTile.topAnchor, constant: 10),
            brand.bottomAnchor.constraint(equalTo: brandTile.bottomAnchor, constant: -10)
        ])
        let headerText = NSStackView(views: [title, detail])
        headerText.orientation = .vertical
        headerText.alignment = .leading
        headerText.spacing = 5
        let header = NSStackView(views: [brandTile, headerText])
        header.spacing = 18
        header.alignment = .centerY
        filename.lineBreakMode = .byTruncatingMiddle
        filename.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        choose.target = self
        choose.action = #selector(selectAudio)
        save.target = self
        save.action = #selector(saveTranscript)
        save.isEnabled = false
        cancel.target = self
        cancel.action = #selector(cancelRun)
        cancel.isEnabled = false
        choose.isEnabled = false
        setup.target = self
        setup.action = #selector(prepareModel)
        setup.isHidden = true
        speakers.toolTip = "A beszélőszám automatikus becslés. Első használatkor kb. 108 MB modell töltődik le; a hang a gépen marad."
        language.addItems(withTitles: ["Magyar", "Angol"])
        language.selectItem(at: 0)
        language.setAccessibilityLabel("Felvétel nyelve")
        format.addItems(withTitles: ["TXT (.txt)", "Markdown (.md)"])
        format.setAccessibilityLabel("Export formátuma")
        progress.style = .spinning
        progress.isDisplayedWhenStopped = false
        progressBar.style = .bar
        progressBar.isIndeterminate = false
        progressBar.isHidden = true
        progressDetail.textColor = .secondaryLabelColor
        progressDetail.isHidden = true
        status.setAccessibilityIdentifier("transcriptionStatus")
        let options = NSStackView(views: [NSTextField(labelWithString: "Felvétel nyelve"), language, speakers])
        options.spacing = 14
        options.alignment = .centerY
        let languageHint = NSTextField(labelWithString: "A felvétel fő nyelvét válaszd; a leirat nem fordítás.")
        languageHint.textColor = .secondaryLabelColor
        languageHint.font = .systemFont(ofSize: 12)
        let settings = NSStackView(views: [sectionTitle("BEÁLLÍTÁSOK"), options, languageHint])
        settings.orientation = .vertical
        settings.alignment = .leading
        settings.spacing = 10

        let fileRow = NSStackView(views: [filename, choose])
        fileRow.spacing = 14
        fileRow.alignment = .centerY
        let fileSection = NSStackView(views: [sectionTitle("HANGFELVÉTEL"), fileRow, setup])
        fileSection.orientation = .vertical
        fileSection.alignment = .leading
        fileSection.spacing = 12

        let processing = NSStackView(views: [progress, cancel])
        processing.spacing = 12
        processing.alignment = .centerY
        let statusSection = NSStackView(views: [sectionTitle("FELDOLGOZÁS"), status,
                                                progressDetail, progressBar, processing])
        statusSection.orientation = .vertical
        statusSection.alignment = .leading
        statusSection.spacing = 10
        let settingsCard = card(containing: settings)
        let fileCard = card(containing: fileSection)
        let statusCard = card(containing: statusSection)
        fileRow.widthAnchor.constraint(equalTo: fileSection.widthAnchor).isActive = true
        status.widthAnchor.constraint(equalTo: statusSection.widthAnchor).isActive = true
        progressBar.widthAnchor.constraint(equalTo: statusSection.widthAnchor).isActive = true

        let export = NSStackView(views: [NSTextField(labelWithString: "Leirat formátuma"), format, save])
        export.spacing = 12
        export.alignment = .centerY
        let stack = NSStackView(views: [header, settingsCard, fileCard, statusCard, export])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        backdrop.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: backdrop.leadingAnchor, constant: 30),
            stack.trailingAnchor.constraint(equalTo: backdrop.trailingAnchor, constant: -30),
            stack.topAnchor.constraint(equalTo: backdrop.topAnchor, constant: 24),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: backdrop.bottomAnchor, constant: -24),
            settingsCard.widthAnchor.constraint(equalTo: stack.widthAnchor),
            fileCard.widthAnchor.constraint(equalTo: stack.widthAnchor),
            statusCard.widthAnchor.constraint(equalTo: stack.widthAnchor)
        ])
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        start(.checking)
    }

    private func sectionTitle(_ text: String) -> NSTextField {
        let label = NSTextField(labelWithString: text)
        label.font = .systemFont(ofSize: 11, weight: .semibold)
        label.textColor = .secondaryLabelColor
        return label
    }

    private func card(containing content: NSView) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .popover
        view.blendingMode = .withinWindow
        view.state = .active
        view.wantsLayer = true
        view.layer?.cornerRadius = 18
        view.layer?.masksToBounds = true
        content.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
            content.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20),
            content.topAnchor.constraint(equalTo: view.topAnchor, constant: 18),
            content.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -18)
        ])
        return view
    }

    @objc private func showAbout() {
        NSApp.orderFrontStandardAboutPanel(options: [
            .applicationName: "Local Transcripter",
            .applicationVersion: Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "",
            .credits: NSAttributedString(string: "Ingyenes, helyi magyar és angol átírás Apple Siliconra.\nMIT licenc.\nWhisper large-v3 · MLX\nFFmpeg: LGPL-2.1-or-later.\nLicencek és FFmpeg-forrás: a Licencek és források menüben.")
        ])
    }

    @objc private func showLicenses() {
        guard let resources = Bundle.main.resourceURL else { return }
        NSWorkspace.shared.open(resources.appendingPathComponent("ThirdParty", isDirectory: true))
    }

    @objc private func selectAudio() {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [UTType(filenameExtension: "m4a")!, .mp3, .wav]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let url = panel.url else { return }
            self?.start(.transcribing(url))
        }
    }

    @objc private func prepareModel() { start(.preparing) }

    private func start(_ nextWork: Work) {
        work = nextWork
        cancelling = false
        if case let .transcribing(audio) = work {
            transcript = nil
            markdown = nil
            source = audio
            filename.stringValue = audio.lastPathComponent
        }
        save.isEnabled = false
        choose.isEnabled = false
        cancel.isEnabled = true
        speakers.isEnabled = false
        language.isEnabled = false
        setup.isEnabled = false
        switch work {
        case .checking: status.stringValue = "Helyi modell ellenőrzése…"; cancel.isEnabled = false
        case .preparing: status.stringValue = "A Whisper modell előkészítése…"
        case .transcribing: status.stringValue = "Helyi átírás folyamatban…"
        }
        progress.startAnimation(nil)
        progressBar.isHidden = true
        progressDetail.isHidden = true
        do {
            guard let configURL = Bundle.main.url(forResource: "configuration", withExtension: "json") else {
                throw CocoaError(.fileNoSuchFile)
            }
            let config = try JSONDecoder().decode(Configuration.self, from: Data(contentsOf: configURL))
            guard let resources = Bundle.main.resourceURL else { throw CocoaError(.fileNoSuchFile) }
            let root = dataDirectory
            try FileManager.default.createDirectory(at: root.appendingPathComponent("runs"),
                                                     withIntermediateDirectories: true,
                                                     attributes: [.posixPermissions: 0o700])
            let run = root.appendingPathComponent("runs").appendingPathComponent(UUID().uuidString)
            let model = root.appendingPathComponent("models/large-v3")
            let speakerModels = root.appendingPathComponent("models/speakers")
            let task = Process()
            let outputURL = run.appendingPathExtension("stdout.json")
            let errorsURL = run.appendingPathExtension("stderr.log")
            FileManager.default.createFile(atPath: outputURL.path, contents: nil, attributes: [.posixPermissions: 0o600])
            FileManager.default.createFile(atPath: errorsURL.path, contents: nil, attributes: [.posixPermissions: 0o600])
            let output = try FileHandle(forWritingTo: outputURL)
            let errors = try FileHandle(forWritingTo: errorsURL)
            defer { try? output.close(); try? errors.close() }
            task.executableURL = resources.appendingPathComponent(config.worker)
            var arguments = ["--output", run.path, "--model", model.path, "--speaker-models", speakerModels.path]
            switch work {
            case .checking: arguments.append("--check-model")
            case .preparing: arguments.append("--prepare-model")
            case let .transcribing(audio):
                arguments += ["--audio", audio.path, "--language", language.indexOfSelectedItem == 1 ? "en" : "hu"]
                if speakers.state == .on { arguments.append("--speakers") }
            }
            task.arguments = arguments
            task.currentDirectoryURL = root
            var environment = ProcessInfo.processInfo.environment
            environment["PATH"] = resources.appendingPathComponent(config.tools).path + ":/usr/bin:/bin:/usr/sbin:/sbin"
            for key in ["PYTHONHOME", "PYTHONPATH", "__PYVENV_LAUNCHER__", "PYTHONUSERBASE"] {
                environment.removeValue(forKey: key)
            }
            environment["HF_HUB_OFFLINE"] = "1"
            environment["HF_HUB_DISABLE_TELEMETRY"] = "1"
            task.environment = environment
            task.standardOutput = output
            task.standardError = errors
            // Files avoid pipe-buffer deadlocks while the worker is running.
            task.terminationHandler = { [weak self] completed in
                let data = (try? Data(contentsOf: outputURL)) ?? Data()
                let errorData = (try? Data(contentsOf: errorsURL)) ?? Data()
                let succeeded = completed.terminationStatus == 0
                DispatchQueue.main.async {
                    self?.finish(data: data, errors: errorData, succeeded: succeeded)
                }
            }
            try task.run()
            process = task
            let statusURL = run.appendingPathExtension("status.json")
            statusTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated {
                    guard let self, !self.cancelling,
                          let data = try? Data(contentsOf: statusURL),
                          let state = try? JSONDecoder().decode(ProcessingStatus.self, from: data) else { return }
                    self.status.stringValue = state.message
                    self.updateProgress(state)
                }
            }
        } catch {
            finish(data: Data(), errors: Data("Az alkalmazás helyi futtatókörnyezete nem indítható. Ellenőrizd, hogy az alkalmazás teljes egészében át lett másolva.".utf8), succeeded: false)
        }
    }

    @objc private func cancelRun() {
        guard let process, !cancelling else { return }
        cancelling = true
        cancel.isEnabled = false
        status.stringValue = "Megszakítás folyamatban…"
        process.terminate()
    }

    private func updateProgress(_ state: ProcessingStatus) {
        guard let seconds = state.seconds, let total = state.total,
              seconds.isFinite, total.isFinite, seconds >= 0, total > 0 else {
            progressBar.isHidden = true
            progressDetail.isHidden = true
            return
        }
        progressBar.maxValue = total
        progressBar.doubleValue = min(seconds, total)
        progressBar.isHidden = false
        progressDetail.stringValue = "Feldolgozott hang: \(formatTime(seconds)) / \(formatTime(total))"
        progressDetail.isHidden = false
    }

    private func formatTime(_ seconds: Double) -> String {
        let whole = Int(seconds)
        return String(format: "%02d:%02d:%02d", whole / 3600, (whole / 60) % 60, whole % 60)
    }

    private func finish(data: Data, errors: Data, succeeded: Bool) {
        statusTimer?.invalidate()
        statusTimer = nil
        process = nil
        cancel.isEnabled = false
        progress.stopAnimation(nil)
        progressBar.isHidden = true
        progressDetail.isHidden = true
        setup.isEnabled = true
        switch work {
        case .checking, .preparing:
            let result = try? JSONDecoder().decode(ModelSetupOutput.self, from: data)
            let ready = succeeded && result?.ready == true
            modelReady = ready
            setup.isHidden = ready
            choose.isEnabled = ready
            speakers.isEnabled = ready
            language.isEnabled = true
            if cancelling {
                status.stringValue = "A modell letöltése megszakítva. Az előkészítést újraindíthatod."
            } else if ready {
                status.stringValue = "A helyi modell készen áll. Válassz egy hangfelvételt."
                if let note = result?.note { status.stringValue += " " + note }
            } else if succeeded {
                status.stringValue = "Első használathoz töltsd le a Whisper modellt (kb. 3,2 GB). Utána internet nélkül is átírhatsz."
            } else {
                status.stringValue = "A modell ellenőrzése vagy letöltése nem sikerült. Ellenőrizd az internetkapcsolatot és a szabad tárhelyet, majd próbáld újra."
            }
            return
        case .transcribing: break
        }
        choose.isEnabled = modelReady
        speakers.isEnabled = true
        language.isEnabled = true
        if cancelling {
            status.stringValue = "A feldolgozás megszakítva. Nem készült teljes leirat."
            return
        }
        guard succeeded, let result = try? JSONDecoder().decode(RecognitionOutput.self, from: data),
              FileManager.default.isReadableFile(atPath: result.transcript),
              FileManager.default.isReadableFile(atPath: result.markdown) else {
            status.stringValue = String(data: errors, encoding: .utf8).flatMap { $0.isEmpty ? nil : $0 }
                ?? "A helyi átírás nem sikerült. Új hangfelvétellel ismét megpróbálhatod."
            return
        }
        transcript = URL(fileURLWithPath: result.transcript)
        markdown = URL(fileURLWithPath: result.markdown)
        save.isEnabled = true
        status.stringValue = result.repetition_warnings > 0
            ? "A leirat elkészült, figyelmeztetést tartalmaz. Mentés után ellenőrizd a jelölt részeket a hang alapján."
            : "A leirat elkészült. A Leirat mentése gombbal választhatod ki a mentés helyét."
        if let note = result.quality_note { status.stringValue += " " + note }
    }

    @objc private func saveTranscript() {
        let isMarkdown = format.indexOfSelectedItem == 1
        guard let export = isMarkdown ? markdown : transcript else { return }
        let suffix = isMarkdown ? "md" : "txt"
        let panel = NSSavePanel()
        panel.allowedContentTypes = [isMarkdown ? UTType(filenameExtension: "md")! : .plainText]
        panel.nameFieldStringValue = (source?.deletingPathExtension().lastPathComponent ?? "Leirat") + "." + suffix
        panel.beginSheetModal(for: window) { [weak self] response in
            guard response == .OK, let destination = panel.url, let self else { return }
            do {
                // A text export must never overwrite the original recording.
                if destination.resolvingSymlinksInPath() == self.source?.resolvingSymlinksInPath() {
                    throw CocoaError(.fileWriteInvalidFileName)
                }
                try Data(contentsOf: export).write(to: destination, options: .atomic)
                self.status.stringValue = "Leirat elmentve: \(destination.path)"
            } catch {
                self.status.stringValue = "A leirat mentése nem sikerült. Válassz másik nevet vagy írható mappát."
            }
        }
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        if process != nil {
            status.stringValue = "Átírás folyamatban. A Megszakítás gombbal leállíthatod; közben kis méretre teheted."
            return false
        }
        return true
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if process != nil {
            status.stringValue = "Átírás folyamatban. Kilépés előtt a Megszakítás gombbal leállíthatod."
            return .terminateCancel
        }
        return .terminateNow
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.setActivationPolicy(.regular)
application.delegate = delegate
application.run()
