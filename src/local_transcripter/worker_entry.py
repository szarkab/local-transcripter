"""Entry point for the self-contained worker and its isolated model subprocesses."""
import os
from pathlib import Path
import sys


def main() -> None:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    role = 'app_worker'
    if len(sys.argv) >= 3 and sys.argv[1] == '--worker':
        role = sys.argv[2]
        sys.argv = [sys.argv[0], *sys.argv[3:]]
    # Local compiled kernels stay in the user's cache, never in the signed bundle.
    cache = Path.home() / 'Library/Caches/hu.localtranscripter.desktop'
    os.environ.setdefault('NUMBA_CACHE_DIR', str(cache / 'numba'))
    if role == 'app_worker':
        from .app_worker import main as run
    elif role == 'recognizer_worker':
        from .recognizer_worker import main as run
    elif role == 'speaker_worker':
        from .speaker_worker import main as run
    elif role == 'quality_worker':
        from .quality_worker import main as run
    else:
        raise SystemExit('Unknown local worker role')
    run()


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    main()
