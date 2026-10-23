"""Anonymous labels from one globally clustered recording, never real identities."""
from dataclasses import dataclass
import json
import sys
from typing import Sequence
from pathlib import Path
from .execution import RunControl, worker_command


@dataclass(frozen=True)
class SpeakerTurn:
    start: float
    end: float
    speaker: str


@dataclass(frozen=True)
class Diarization:
    turns: tuple[SpeakerTurn, ...]
    model: dict[str, object]
    uncertain_speakers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def labels_for_ranges(ranges: Sequence[tuple[float, float]],
                      turns: Sequence[SpeakerTurn],
                      uncertain_speakers: Sequence[str] = ()) -> tuple[str, ...]:
    names: dict[str, str] = {}
    for turn in sorted(turns, key=lambda t: t.start):
        if turn.speaker not in names:
            number = sum(name != 'Beszélő bizonytalan' for name in names.values()) + 1
            names[turn.speaker] = ('Beszélő bizonytalan' if turn.speaker in uncertain_speakers
                                   else f'Beszélő {number}')
    labels = []
    for start, end in ranges:
        coverage: dict[str, float] = {}
        for turn in turns:
            overlap = max(0.0, min(end, turn.end) - max(start, turn.start))
            if start == end and turn.start <= start < turn.end:
                overlap = 1.0
            coverage[turn.speaker] = coverage.get(turn.speaker, 0.0) + overlap
        ranked = sorted(coverage.items(), key=lambda pair: pair[1], reverse=True)
        duration = end - start if end > start else 1.0
        if (ranked and ranked[0][1] >= duration * .65
                and (len(ranked) == 1 or ranked[1][1] <= duration * .15)):
            labels.append(names[ranked[0][0]])
        else:
            labels.append('Beszélő bizonytalan')
    return tuple(labels)


@dataclass(frozen=True)
class ProcessDiarizer:
    models: Path
    control: RunControl
    prepare_on_demand: bool = False

    def __call__(self, audio: Path) -> Diarization:
        if self.prepare_on_demand:
            from .prepare_speakers import prepare
            prepare(self.models, self.control)
        result = audio.parent / 'speakers.json'
        progress = audio.parent / 'speakers-progress.json'
        self.control.run(worker_command(Path(__file__).with_name('speaker_worker.py'), [
                          '--audio', str(audio), '--models', str(self.models.resolve()),
                          '--result', str(result), '--progress', str(progress)]),
                         audio.parent / 'speakers.log', progress_path=progress,
                         progress_label='Beszélők elkülönítése')
        raw = json.loads(result.read_text())
        return Diarization(tuple(SpeakerTurn(float(t['start']), float(t['end']), str(t['speaker']))
                                 for t in raw['turns']), raw['model'],
                           tuple(raw.get('uncertain_speakers', [])), tuple(raw.get('warnings', [])))
