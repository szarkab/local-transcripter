import AppKit

let destination = CommandLine.arguments[1]
let source = CommandLine.arguments[2]
guard let mark = NSImage(contentsOfFile: source) else {
    fatalError("Cannot open the supplied vector brand mark: \(source)")
}

let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()

let tile = NSBezierPath(roundedRect: NSRect(x: 64, y: 64, width: 896, height: 896),
                        xRadius: 205, yRadius: 205)
let shadow = NSShadow()
shadow.shadowColor = NSColor.black.withAlphaComponent(0.23)
shadow.shadowBlurRadius = 44
shadow.shadowOffset = NSSize(width: 0, height: -18)
NSGraphicsContext.saveGraphicsState()
shadow.set()
NSColor.white.setFill()
tile.fill()
NSGraphicsContext.restoreGraphicsState()

NSGradient(starting: NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 1),
           ending: NSColor(calibratedRed: 0.96, green: 0.94, blue: 0.97, alpha: 1))!
    .draw(in: tile, angle: -75)
NSColor(calibratedRed: 0.33, green: 0.10, blue: 0.30, alpha: 0.15).setStroke()
tile.lineWidth = 3
tile.stroke()

// Keep the user's SVG as the sole foreground mark, including its original gradient.
mark.draw(in: NSRect(x: 192, y: 202, width: 640, height: 608),
          from: .zero, operation: .sourceOver, fraction: 1)

image.unlockFocus()
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
let png = bitmap.representation(using: .png, properties: [:])!
if CommandLine.arguments.count > 3 {
    try png.write(to: URL(fileURLWithPath: CommandLine.arguments[3]))
}

// PNG-backed 1024px icon in a reproducible icns container.
var data = Data("icns".utf8)
func bigEndian(_ value: Int) -> Data {
    var number = UInt32(value).bigEndian
    return withUnsafeBytes(of: &number) { Data($0) }
}
data.append(bigEndian(png.count + 16))
data.append(Data("ic10".utf8))
data.append(bigEndian(png.count + 8))
data.append(png)
try data.write(to: URL(fileURLWithPath: destination))
