"""Notarize a Developer ID-signed DMG and refresh its release metadata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def sha256(path: Path) -> str:
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dmg', type=Path)
    parser.add_argument('--notary-profile', default=os.environ.get('LOCAL_TRANSCRIPTER_NOTARY_PROFILE'))
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--source-zip', type=Path, required=True)
    parser.add_argument('--checksums', type=Path, required=True)
    args = parser.parse_args()
    if not args.notary_profile:
        raise SystemExit('Set LOCAL_TRANSCRIPTER_NOTARY_PROFILE or pass --notary-profile.')
    manifest = json.loads(args.manifest.read_text())
    if manifest.get('signing') != 'developer-id':
        raise SystemExit('Notarization requires a Developer ID-signed app.')
    subprocess.run(['xcrun', 'notarytool', 'submit', str(args.dmg), '--keychain-profile',
                    args.notary_profile, '--wait'], check=True)
    subprocess.run(['xcrun', 'stapler', 'staple', str(args.dmg)], check=True)
    subprocess.run(['xcrun', 'stapler', 'validate', str(args.dmg)], check=True)
    manifest['channel'] = 'stable'
    manifest['notarized'] = True
    manifest['notarization'] = {'stapled': True, 'validated': True}
    args.manifest.write_text(json.dumps(manifest, indent=2) + '\n')
    sums = [f'{sha256(path)}  {path.name}' for path in (args.dmg, args.source_zip, args.manifest)]
    args.checksums.write_text('\n'.join(sums) + '\n')


if __name__ == '__main__':
    main()
