"""Freeze the local worker, Python, model libraries and audio tools for Apple Silicon."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'src'
DIST = ROOT / 'build/worker-dist'
RUNTIME = DIST / 'local-transcripter-worker'


def main() -> None:
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
               '--target-architecture', 'arm64', '--name', 'local-transcripter-worker',
               '--distpath', str(DIST), '--workpath', str(ROOT / 'build/pyinstaller-work'),
               '--specpath', str(ROOT / 'build'), '--log-level', 'WARN',
               '--paths', str(SOURCE)]
    for package in ('mlx', 'mlx_whisper', 'sherpa_onnx'):
        command += ['--collect-all', package]
    for package in ('mlx', 'mlx-metal', 'mlx-whisper', 'sherpa-onnx', 'sherpa-onnx-core', 'onnxruntime'):
        command += ['--copy-metadata', package]
    command += ['--collect-binaries', 'onnxruntime', '--collect-data', 'certifi',
                '--hidden-import', 'tiktoken_ext.openai_public']
    for package in ('torch', 'faster_whisper', 'ctranslate2', 'pandas', 'matplotlib',
                    'sklearn', 'PIL', 'tensorflow', 'parakeet_mlx', 'numba.np.ufunc.omppool'):
        command += ['--exclude-module', package]
    for name in ('ffmpeg', 'ffprobe'):
        tool = ROOT / 'build/audio-tools/bin' / name
        if not tool.is_file():
            raise SystemExit('First run: python scripts/build_audio_tools.py')
        command += ['--add-binary', f'{tool}:tools']
    command.append(str(SOURCE / 'local_transcripter/__main__.py'))
    subprocess.run(command, check=True, cwd=ROOT)
    print(RUNTIME)


if __name__ == '__main__':
    main()
