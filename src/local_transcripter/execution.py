"""Cancellable local child processes with real-progress and absolute deadlines."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Callable

from .text import timestamp


def worker_command(script: Path, arguments: list[str]) -> list[str]:
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--worker', script.stem, *arguments]
    if script.parent == Path(__file__).parent:
        return [sys.executable, '-m', 'local_transcripter', '--worker', script.stem, *arguments]
    return [sys.executable, str(script), *arguments]


class CancelledError(Exception):
    """User cancellation; never export a successful transcript."""


class ProcessingTimeout(TimeoutError):
    """The recognizer stopped advancing or exceeded its absolute deadline."""


@dataclass
class RunControl:
    cancelled: Callable[[], bool] = lambda: False
    on_status: Callable[[str], None] = lambda message: None
    on_progress: Callable[[float | None, float | None], None] = lambda seconds, total: None
    attempt: int = 1

    def check(self) -> None:
        if self.cancelled():
            raise CancelledError('Processing cancelled')

    def announce(self, message: str) -> None:
        self.check()
        self.on_progress(None, None)
        self.on_status(message)

    def run(self, command: list[str], log: Path, *, timeout_seconds: float = 1800,
            inactivity_seconds: float = 120, progress_path: Path | None = None,
            progress_label: str | None = None) -> None:
        self.check()
        started = last_advance = time.monotonic()
        last_position = -1.0
        with log.open('w') as target:
            child = subprocess.Popen(command, stdout=target, stderr=subprocess.STDOUT,
                                     start_new_session=True,
                                     env={**os.environ, 'HF_HUB_OFFLINE': '1',
                                          'HF_HUB_DISABLE_TELEMETRY': '1'})
            try:
                while child.poll() is None:
                    self.check()
                    now = time.monotonic()
                    if progress_path is not None and progress_path.exists():
                        try:
                            state = json.loads(progress_path.read_text())
                            position, total = float(state['seconds']), float(state['total'])
                            if position > last_position:
                                last_position = position
                                last_advance = now
                                if progress_label is None:
                                    self.on_progress(position, total)
                                self.on_status(f'{progress_label or str(self.attempt) + ". próba"} · Feldolgozva: '
                                               f'{timestamp(position)} / {timestamp(total)}')
                        except (OSError, ValueError, KeyError):
                            pass  # A transient status read never changes the result.
                    if now - started > timeout_seconds or now - last_advance > inactivity_seconds:
                        raise ProcessingTimeout('No recognition progress or absolute deadline exceeded')
                    time.sleep(0.1)
                self.check()
                if child.returncode:
                    raise subprocess.CalledProcessError(child.returncode, command)
            finally:
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # Child exited between poll and kill; preserve cancellation/timeout.
                child.wait()
