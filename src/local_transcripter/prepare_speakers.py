"""Prepare public, pinned local speaker models. No account, token or audio upload."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

from .execution import RunControl

BASE = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
SEGMENTATION_URL = BASE + 'speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2'
EMBEDDING_URL = BASE + 'speaker-recongition-models/nemo_en_titanet_large.onnx'
SEGMENTATION_SHA = '220ad67ca923bef2fa91f2390c786097bf305bceb5e261d4af67b38e938e1079'
ARCHIVE_SHA = '24615ee884c897d9d2ba09bb4d30da6bb1b15e685065962db5b02e76e4996488'
EMBEDDING_SHA = 'd51abcf31717ef28162f26acb9d44dd4127c3d44c9b8624f699f3425daca8e77'
EMBEDDING_NOTICE = (
    'NVIDIA TitaNet-Large (en-US), NVIDIA. License: CC-BY-4.0.\n'
    'Model: https://huggingface.co/nvidia/speakerverification_en_titanet_large\n'
    'License: https://creativecommons.org/licenses/by/4.0/\n'
    'ONNX conversion distributed by k2-fsa/sherpa-onnx.\n'
    'This application uses the distributed weights unchanged.\n'
)


def matches(path: Path, sha: str) -> bool:
    if not path.is_file():
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == sha


def download(url: str, target: Path, sha: str, control: RunControl, *,
             label: str = 'Beszélőmodell', expected_bytes: int | None = None) -> None:
    if matches(target, sha):
        return
    temporary = target.with_suffix('.download')
    try:
        with urllib.request.urlopen(url, timeout=10) as source, temporary.open('wb') as output:
            done = 0
            while chunk := source.read(256 * 1024):
                control.check()
                output.write(chunk)
                done += len(chunk)
                total = f' / {expected_bytes / 1_000_000:.1f} MB' if expected_bytes else ' MB'
                control.announce(f'{label} letöltése · {done / 1_000_000:.1f}{total}')
        if not matches(temporary, sha):
            raise ValueError('Downloaded speaker model identity mismatch')
        control.check()
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(directory: Path, control: RunControl) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    control.announce('Beszélőmodell ellenőrzése és előkészítése…')
    if (not matches(directory / 'segmentation.onnx', SEGMENTATION_SHA)
            or not (directory / 'SEGMENTATION_LICENSE').is_file()):
        archive = directory / 'segmentation.tar.bz2'
        download(SEGMENTATION_URL, archive, ARCHIVE_SHA, control)
        with tarfile.open(archive) as source:
            # Read only named files; no archive path is ever extracted to the filesystem.
            for member, target in [('model.onnx', 'segmentation.onnx'),
                                   ('LICENSE', 'SEGMENTATION_LICENSE')]:
                stream = source.extractfile('sherpa-onnx-pyannote-segmentation-3-0/' + member)
                if stream is None:
                    raise ValueError('Incomplete speaker model archive')
                with stream:
                    data = stream.read()
                if member == 'model.onnx' and hashlib.sha256(data).hexdigest() != SEGMENTATION_SHA:
                    raise ValueError('Extracted speaker model identity mismatch')
                control.check()
                (directory / target).write_bytes(data)
    download(EMBEDDING_URL, directory / 'embedding.onnx', EMBEDDING_SHA, control)
    (directory / 'EMBEDDING_NOTICE.txt').write_text(EMBEDDING_NOTICE, encoding='utf-8')
    files: dict[str, dict[str, str | int]] = {}
    manifest = {'provider': 'k2-fsa/sherpa-onnx official release', 'files': files}
    for name, url, sha in [('segmentation.onnx', SEGMENTATION_URL, SEGMENTATION_SHA),
                           ('embedding.onnx', EMBEDDING_URL, EMBEDDING_SHA)]:
        files[name] = {'url': url, 'sha256': sha,
                                  'bytes': (directory / name).stat().st_size}
    temporary = directory / 'provenance.tmp'
    temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    control.check()
    temporary.replace(directory / 'provenance.json')
    control.announce('A beszélőmodell készen áll.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Path(__file__).parent / 'models/speakers')
    prepare(parser.parse_args().directory, RunControl(on_status=print))
