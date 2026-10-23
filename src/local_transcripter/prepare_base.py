"""Pinned, atomic first-use preparation of the accepted local Whisper model."""
import json
from pathlib import Path
from .execution import RunControl
from .prepare_speakers import download, matches

REPOSITORY = 'mlx-community/whisper-large-v3-mlx'
REVISION = '49e6aa286ad60c14352c404340ded53710378a11'
FILES = {
    'config.json': ('34982ce6ae286095000f82ae9583b3431639e8b092bf60c961f203745e6500e3', 269),
    'weights.npz': ('05ff791ce3630fae47e7c51004e9666204d786246ec07cac6110af768099b40d', 3083520416),
}


def ready(directory: Path) -> bool:
    try:
        provenance = json.loads((directory / 'provenance.json').read_text())
        return (provenance.get('repository') == REPOSITORY and provenance.get('revision') == REVISION
                and all(matches(directory / name, sha) for name, (sha, _) in FILES.items()))
    except (OSError, ValueError, AttributeError):
        return False


def prepare(directory: Path, control: RunControl) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    control.announce('Whisper modell ellenőrzése…')
    for name, (sha, size) in FILES.items():
        download(f'https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}',
                 directory / name, sha, control, label='Whisper modell', expected_bytes=size)
    control.check()
    temporary = directory / 'provenance.tmp'
    temporary.write_text(json.dumps({'repository': REPOSITORY, 'revision': REVISION,
                                     'files': {n: {'sha256': sha, 'bytes': size}
                                               for n, (sha, size) in FILES.items()}}, indent=2))
    control.check()
    temporary.replace(directory / 'provenance.json')
    control.announce('A Whisper modell készen áll.')
