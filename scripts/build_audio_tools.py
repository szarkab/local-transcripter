"""Build the pinned, audio-only LGPL FFmpeg tools without Homebrew libraries."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tomllib
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
VERSION = '8.1.2'
SHA256 = '464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c'
URL = f'https://ffmpeg.org/releases/ffmpeg-{VERSION}.tar.xz'
PREFIX = ROOT / 'build/audio-tools'


def main() -> None:
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('Build on an Apple Silicon Mac.')
    minimum = tomllib.loads((ROOT / 'pyproject.toml').read_text())['tool']['local-transcripter']['minimum-macos']
    archive = ROOT / f'build/downloads/ffmpeg-{VERSION}.tar.xz'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        with urllib.request.urlopen(URL, timeout=30) as source, archive.open('wb') as target:
            shutil.copyfileobj(source, target)
    with archive.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != SHA256:
            raise SystemExit('Unexpected FFmpeg source identity; remove the download and retry.')
    source_root = ROOT / f'build/ffmpeg-{VERSION}'
    if not source_root.exists():
        with tarfile.open(archive) as source:
            source.extractall(ROOT / 'build', filter='data')
    config = [str(source_root / 'configure'), '--prefix=/usr/local', '--arch=aarch64',
              '--target-os=darwin', '--cc=clang', '--disable-everything',
              '--disable-autodetect', '--disable-network', '--disable-shared', '--enable-static',
              '--disable-doc', '--disable-debug', '--disable-avdevice', '--disable-swscale',
              '--disable-audiotoolbox', '--disable-videotoolbox', '--disable-securetransport',
              '--enable-ffmpeg', '--enable-ffprobe', '--enable-protocol=file,pipe',
              '--enable-demuxer=mov,mp3,wav,aac', '--enable-muxer=wav,pcm_s16le',
              '--enable-decoder=aac,alac,mp3,mp3float,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s24be,pcm_s32le,pcm_s32be,pcm_f32le,pcm_f32be,pcm_f64le,pcm_f64be,pcm_u8,pcm_alaw,pcm_mulaw',
              '--enable-encoder=pcm_s16le', '--enable-parser=aac,mpegaudio',
              '--enable-filter=abuffer,abuffersink,aresample,aformat,anull,atrim',
              f'--extra-cflags=-mmacosx-version-min={minimum}',
              f'--extra-ldflags=-mmacosx-version-min={minimum}']
    subprocess.run(config, cwd=source_root, check=True)
    subprocess.run(['make', '-j', str(min(os.cpu_count() or 2, 8))], cwd=source_root, check=True)
    staging = ROOT / 'build/audio-tools-install'
    subprocess.run(['make', 'install', f'DESTDIR={staging}'], cwd=source_root, check=True)
    PREFIX.mkdir(parents=True, exist_ok=True)
    shutil.copytree(staging / 'usr/local/bin', PREFIX / 'bin', dirs_exist_ok=True)
    notices = PREFIX / 'source'
    notices.mkdir(exist_ok=True)
    shutil.copy2(archive, notices / archive.name)
    shutil.copy2(source_root / 'COPYING.LGPLv2.1', notices)
    shutil.copy2(__file__, notices / 'build_audio_tools.py')
    (notices / 'build.json').write_text(json.dumps({
        'version': VERSION, 'url': URL, 'sha256': SHA256,
        'configure': [p.replace(str(ROOT), '<PROJECT>') for p in config],
        'modifications': 'None; original source archive included.',
        'license': 'LGPL-2.1-or-later',
    }, indent=2))
    print(PREFIX)


if __name__ == '__main__':
    main()
