"""Create a verified local-preview DMG, public source ZIP and SHA-256 manifest."""
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tomllib
import zipfile

from public_source import public_files
from verify_bundle import audit

ROOT = Path(__file__).resolve().parent.parent


def signing_kind(app: Path) -> str:
    details = subprocess.check_output(['codesign', '-dv', '--verbose=2', str(app)],
                                      stderr=subprocess.STDOUT, text=True)
    return 'ad-hoc' if 'Signature=adhoc' in details else 'developer-id'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-candidate', action='store_true',
                        help='Require a clean Git tree and a Developer ID-signed app.')
    args = parser.parse_args()
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    version = project['project']['version']
    app = ROOT / 'build/Local Transcripter.app'
    with (app / 'Contents/Info.plist').open('rb') as source:
        if plistlib.load(source)['CFBundleShortVersionString'] != version:
            raise SystemExit('App version is stale; rebuild first.')
    result = audit(app)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
    signing = signing_kind(app)
    revision = None
    dirty = None
    if (ROOT / '.git').exists():
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    if args.release_candidate and dirty:
        raise SystemExit('A release candidate must be built from a clean Git tree.')
    if args.release_candidate and signing == 'ad-hoc':
        raise SystemExit('A release candidate requires a Developer ID-signed app.')
    files = public_files(ROOT)
    staging = ROOT / 'build/dmg-root'
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    subprocess.run(['ditto', str(app), str(staging / app.name)], check=True)
    (staging / 'Applications').symlink_to('/Applications', target_is_directory=True)
    shutil.copy2(ROOT / 'README.md', staging / 'Telepites.txt')
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    dmg = destination / f'Local-Transcripter-{version}-apple-silicon-local.dmg'
    temporary = destination / (dmg.stem + '.partial.dmg')
    temporary.unlink(missing_ok=True)
    subprocess.run(['hdiutil', 'create', '-volname', 'Local Transcripter', '-srcfolder', str(staging),
                    '-format', 'UDZO', '-ov', str(temporary)], check=True)
    subprocess.run(['hdiutil', 'verify', str(temporary)], check=True)
    temporary.replace(dmg)
    source_zip = destination / f'Local-Transcripter-{version}-source.zip'
    with zipfile.ZipFile(source_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, str(Path(f'local-transcripter-{version}') / path.relative_to(ROOT)))
    manifest = destination / 'release.json'
    manifest.write_text(json.dumps({
        'version': version, 'architecture': 'arm64', 'minimum_macos': result['minimum_macos'],
        'channel': 'release-candidate' if args.release_candidate else 'local-preview',
        'signing': signing, 'notarized': False,
        'source_git_revision': revision, 'source_git_dirty': dirty,
        'audit': result,
    }, indent=2))
    sums = []
    for path in (dmg, source_zip, manifest):
        with path.open('rb') as source:
            sums.append(f'{hashlib.file_digest(source, "sha256").hexdigest()}  {path.name}')
    (destination / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
    print(dmg)


if __name__ == '__main__':
    main()
