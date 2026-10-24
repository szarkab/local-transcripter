"""Build a self-contained Apple Silicon app; models are prepared on first use."""
import argparse
from importlib.metadata import distributions
import os
import platform
import sys
from pathlib import Path
import json
import plistlib
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build'
APP = BUILD / 'Local Transcripter.app'
PROJECT = tomllib.loads((ROOT / 'pyproject.toml').read_text())
MACHO_MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}


def sign_application(app: Path, identity: str) -> None:
    """Sign native code first, then seal the outer app bundle."""
    arguments = ['codesign', '--force', '--sign', identity]
    if identity != '-':
        arguments.extend(['--options', 'runtime', '--timestamp'])
    native_code = []
    for path in app.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as source:
            if source.read(4) in MACHO_MAGICS:
                native_code.append(path)
    for path in sorted(native_code, key=lambda item: len(item.parts), reverse=True):
        subprocess.run([*arguments, str(path)], check=True)
    subprocess.run([*arguments, str(app)], check=True)


def write_notices(resources: Path) -> None:
    directory = resources / 'ThirdParty'
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir()
    versions = {}
    for package_info in distributions():
        package = package_info.metadata['Name']
        if package in ('local-transcripter', 'torch'):
            continue
        versions[package] = package_info.version
        for item in package_info.files or ():
            name = str(item)
            if '..' not in item.parts and any(word in item.name.lower() for word in ('license', 'copying', 'notice')):
                source = Path(str(package_info.locate_file(item)))
                if source.is_file():
                    target = directory / package / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    ffmpeg = ROOT / 'build/audio-tools/bin/ffmpeg'
    shutil.copytree(ROOT / 'build/audio-tools/source', directory / 'FFmpeg')
    shutil.copy2(ROOT / 'LICENSE', resources / 'LICENSE.txt')
    shutil.copy2(ROOT / 'THIRD_PARTY.md', directory / 'README.md')
    shutil.copytree(ROOT / 'resources/licenses', directory / 'models')
    python_license = Path(sys.base_prefix) / 'lib/python3.13/LICENSE.txt'
    if python_license.is_file():
        shutil.copy2(python_license, directory / 'CPython-LICENSE.txt')
    versions['python'] = platform.python_version()
    versions['macOS_build_host'] = platform.mac_ver()[0]
    versions['ffmpeg'] = subprocess.check_output([str(ffmpeg), '-version'], text=True,
                                               stderr=subprocess.DEVNULL).splitlines()[0]
    (directory / 'versions.json').write_text(json.dumps(versions, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-runtime', action='store_true', help='Reuse a previously frozen runtime for UI-only edits')
    parser.add_argument('--signing-identity', default=os.environ.get('LOCAL_TRANSCRIPTER_CODESIGN_IDENTITY', '-'),
                        help='Developer ID Application identity; defaults to ad-hoc signing.')
    args = parser.parse_args()
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('Build on an Apple Silicon Mac.')
    runtime = BUILD / 'worker-dist/local-transcripter-worker'
    if not args.reuse_runtime:
        if not (ROOT / 'build/audio-tools/bin/ffmpeg').is_file():
            subprocess.run([sys.executable, str(ROOT / 'scripts/build_audio_tools.py')], check=True)
        subprocess.run([sys.executable, str(ROOT / 'scripts/build_runtime.py')], check=True)
    if not (runtime / 'local-transcripter-worker').is_file():
        raise SystemExit('Missing bundled runtime; run the build without --reuse-runtime.')
    macos = APP / 'Contents/MacOS'
    resources = APP / 'Contents/Resources'
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    cache = BUILD / 'module-cache'
    cache.mkdir(exist_ok=True)
    subprocess.run(['swiftc', '-swift-version', '6', '-target',
                    'arm64-apple-macosx' + PROJECT['tool']['local-transcripter']['minimum-macos'],
                    '-module-cache-path', str(cache),
                    str(ROOT / 'app/LocalTranscripter.swift'), '-o', str(macos / 'LocalTranscripter'),
                    '-framework', 'AppKit', '-framework', 'UniformTypeIdentifiers'], check=True)
    bundled = resources / 'runtime'
    if bundled.exists():
        shutil.rmtree(bundled)
    shutil.copytree(runtime, bundled, symlinks=True)
    (resources / 'configuration.json').write_text(json.dumps({
        'worker': 'runtime/local-transcripter-worker', 'tools': 'runtime/_internal/tools',
    }), encoding='utf-8')
    shutil.copy2(ROOT / 'resources/BrandMark.svg', resources / 'BrandMark.svg')
    write_notices(resources)
    with (APP / 'Contents/Info.plist').open('wb') as target:
        plistlib.dump({'CFBundleExecutable': 'LocalTranscripter',
                      'CFBundleIdentifier': 'hu.localtranscripter.desktop',
                      'CFBundleName': 'Local Transcripter', 'CFBundleDisplayName': 'Local Transcripter',
                      'CFBundlePackageType': 'APPL', 'CFBundleVersion': PROJECT['tool']['local-transcripter']['build-number'],
                      'CFBundleShortVersionString': PROJECT['project']['version'],
                      'CFBundleIconFile': 'AppIcon', 'LSMinimumSystemVersion': PROJECT['tool']['local-transcripter']['minimum-macos'],
                      'NSHighResolutionCapable': True}, target)
    subprocess.run(['swift', '-module-cache-path', str(cache), str(ROOT / 'scripts/draw_icon.swift'),
                    str(resources / 'AppIcon.icns'), str(resources / 'BrandMark.svg')], check=True)
    sign_application(APP, args.signing_identity)
    print(APP)


if __name__ == '__main__':
    main()
