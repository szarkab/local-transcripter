"""Local overlap-model boundary; notices never rewrite recognized words."""
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from .execution import RunControl, worker_command


@dataclass(frozen=True)
class Overlap:
    start: float
    end: float


@dataclass(frozen=True)
class QualityAnalysis:
    overlaps: tuple[Overlap, ...]
    model: dict[str, object]


@dataclass(frozen=True)
class ProcessQualityAnalyzer:
    model: Path
    control: RunControl

    def __call__(self, audio: Path) -> QualityAnalysis:
        result = audio.parent / 'quality-analysis.json'
        progress = audio.parent / 'quality-progress.json'
        self.control.run(worker_command(Path(__file__).with_name('quality_worker.py'), [
                          '--audio', str(audio), '--model', str(self.model.resolve()),
                          '--result', str(result), '--progress', str(progress)]),
                         audio.parent / 'quality.log', progress_path=progress,
                         progress_label='Egyszerre beszélés vizsgálata')
        try:
            raw = json.loads(result.read_text())
            return QualityAnalysis(tuple(Overlap(float(t['start']), float(t['end']))
                                         for t in raw['overlaps']), raw['model'])
        except (KeyError, TypeError) as error:
            raise ValueError('Invalid local overlap-model response') from error
