"""Explicit public source allowlist; never package working data or Git internals."""
from pathlib import Path
import re

ROOT_FILES = ('README.md', 'LICENSE', 'THIRD_PARTY.md',
              'pyproject.toml', 'requirements.lock.txt', 'requirements-build.lock.txt',
              '.gitignore', '.gitattributes', 'resources/BrandMark.svg')
DIRECTORIES = ('app', 'src', 'resources')
BUILD_FILES = ('scripts/build_app.py', 'scripts/build_runtime.py',
               'scripts/build_audio_tools.py', 'scripts/draw_icon.swift',
               'scripts/verify_bundle.py', 'scripts/build_dmg.py', 'scripts/public_source.py')
SUFFIXES = {'.py', '.swift', '.md', '.toml', '.txt', '.yml', '.yaml'}
SECRET = re.compile(rb'(?:hf_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def public_files(root: Path) -> list[Path]:
    files = [root / name for name in (*ROOT_FILES, *BUILD_FILES) if (root / name).is_file()]
    for name in DIRECTORIES:
        files.extend(p for p in (root / name).rglob('*')
                     if p.is_file() and not p.is_symlink() and p.suffix in SUFFIXES
                     and '__pycache__' not in p.parts and not any(part.endswith('.egg-info') for part in p.parts))
    for path in files:
        data = path.read_bytes()
        if SECRET.search(data) or (b'/' + b'Users' + b'/') in data or (b'/' + b'home' + b'/') in data:
            raise ValueError(f'Private path or credential pattern in {path.relative_to(root)}')
    return sorted(files)
