"""Audit a built app for escaping symlinks and external native dependencies."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import plistlib

MAGICS = {b'\xcf\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}


def audit(app: Path) -> dict[str, object]:
    root = app.resolve()
    escaped = [str(p.relative_to(root)) for p in root.rglob('*')
               if p.is_symlink() and not p.resolve().is_relative_to(root)]
    binaries = []
    for path in root.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as source:
            if source.read(4) in MAGICS:
                binaries.append(path)

    def dependencies(path: Path) -> tuple[list[str], str | None]:
        output = subprocess.check_output(['otool', '-L', str(path)], text=True)
        external = [f'{path.relative_to(root)}: {line.strip()}' for line in output.splitlines()[1:]
                    if not line.strip().startswith(('@', '/System/Library/', '/usr/lib/'))]
        architectures = subprocess.check_output(['lipo', '-archs', str(path)], text=True).split()
        return external, str(path.relative_to(root)) if 'arm64' not in architectures else None

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(dependencies, binaries))
    external = [item for dependencies_, _ in results for item in dependencies_]
    non_arm64 = [path for _, path in results if path is not None]
    with (root / 'Contents/Info.plist').open('rb') as source:
        info = plistlib.load(source)
    resources = root / 'Contents/Resources'
    configuration = json.loads((resources / 'configuration.json').read_text())
    for key in ('worker', 'tools'):
        target = resources / configuration[key]
        if not target.resolve().is_relative_to(root) or not target.exists():
            escaped.append(f'configuration: {key}')
    result: dict[str, object] = {'macho_files': len(binaries), 'escaping_symlinks': escaped,
                                 'external_native_dependencies': external,
                                 'non_arm64_binaries': non_arm64,
                                 'version': info['CFBundleShortVersionString'],
                                 'minimum_macos': info['LSMinimumSystemVersion']}
    if escaped or external or non_arm64 or not binaries:
        raise ValueError(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    print(json.dumps(audit(Path(sys.argv[1])), indent=2))
