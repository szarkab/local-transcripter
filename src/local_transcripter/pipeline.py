"""Reproducible local audio-to-export quality trial, independent of a UI."""
from dataclasses import asdict, dataclass, field, replace
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import resource
import platform
import subprocess
import sys
import time
from typing import Callable, Literal

from .text import clean_reference, normalize, repetitions, timestamp
from .provenance import hardware_identity
from .execution import RunControl, ProcessingTimeout, worker_command
from .speakers import Diarization, labels_for_ranges
from .speech_quality import QualityAnalysis


WORD_REVIEW_THRESHOLD = .15


@dataclass(frozen=True)
class Word:
    start: float
    end: float
    text: str
    probability: float | None = None


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    speaker: str | None = None
    words: tuple[Word, ...] = ()


@dataclass(frozen=True)
class ModelInfo:
    backend: str
    repository: str
    revision: str
    settings: dict[str, str | int | float | bool]
    artifact_sha256: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Recognition:
    segments: tuple[Segment, ...]
    model: ModelInfo


@dataclass(frozen=True)
class TrialResult:
    text_path: Path
    markdown_path: Path
    report_path: Path


@dataclass(frozen=True)
class ProcessRecognizer:
    engine: Literal['mlx']
    model: Path
    language: Literal['hu', 'en'] = 'hu'
    timeout_seconds: float = 1800
    inactivity_seconds: float = 120
    worker_script: Path = Path(__file__).with_name('recognizer_worker.py')
    # Carrying a mistaken sentence into later windows caused whole-file loops.
    reset_context: bool = True
    control: RunControl = field(default_factory=RunControl)

    def __call__(self, audio: Path) -> Recognition:
        raw_path = audio.parent / 'recognition.json'
        command = worker_command(self.worker_script, ['--engine', self.engine, '--model', str(self.model.resolve()),
                   '--audio', str(audio), '--result', str(raw_path),
                   '--progress', str(audio.parent / 'progress.json'), '--language', self.language])
        if self.reset_context:
            command.append('--reset-context')
        else:
            command.append('--carry-context')
        progress = audio.parent / 'progress.json'
        progress.unlink(missing_ok=True)
        self.control.run(command, audio.parent / f'recognition-{self.control.attempt}.log',
                         timeout_seconds=self.timeout_seconds,
                         inactivity_seconds=self.inactivity_seconds, progress_path=progress)
        raw = json.loads(raw_path.read_text())
        info = raw['model']
        return Recognition(tuple(Segment(float(s['start']), float(s['end']), str(s['text']),
                                         words=tuple(Word(float(w['start']), float(w['end']), str(w['text']),
                                                          probability=float(w['probability']) if w.get('probability') is not None else None)
                                                     for w in s.get('words', [])))
                                 for s in raw['segments']),
                           ModelInfo(info['backend'], info['repository'], info['revision'],
                                     info['settings'], info['artifact_sha256']))


def label_segments(segments: tuple[Segment, ...], detected: Diarization) -> tuple[Segment, ...]:
    labelled: list[Segment] = []
    for segment in segments:
        words = segment.words
        previous = segment.start
        aligned = bool(words) and ''.join(w.text for w in words) == segment.text
        for word in words:
            aligned = aligned and (math.isfinite(word.start) and math.isfinite(word.end)
                                   and previous <= word.start <= word.end <= segment.end)
            previous = word.start
        if not aligned:
            label = labels_for_ranges([(segment.start, segment.end)], detected.turns, detected.uncertain_speakers)[0]
            labelled.append(replace(segment, speaker=label))
            continue
        labels = labels_for_ranges([(w.start, w.end) for w in words], detected.turns, detected.uncertain_speakers)
        group: list[Word] = []
        for word, label in zip(words, labels):
            if group and label != labelled[-1].speaker:
                group = []
            if not group:
                labelled.append(replace(segment, start=word.start, end=word.end,
                                        text=word.text, speaker=label, words=(word,)))
            else:
                part = labelled[-1]
                labelled[-1] = replace(part, end=word.end, text=part.text + word.text,
                                       words=part.words + (word,))
            group.append(word)
    return tuple(labelled)


def run_transcription(
    audio: Path,
    output: Path,
    recognizer: Callable[[Path], Recognition],
    *,
    retry_recognizer: Callable[[Path], Recognition] | None = None,
    control: RunControl | None = None,
    duration_seconds: float | None = None,
    reference: Path | None = None,
    diarizer: Callable[[Path], Diarization] | None = None,
    quality_analyzer: Callable[[Path], QualityAnalysis] | None = None,
) -> TrialResult:
    """Decode the source, call a local recognizer and export its unchanged text."""
    if isinstance(recognizer, ProcessRecognizer):
        control = control or recognizer.control
        retry_recognizer = retry_recognizer or replace(recognizer, reset_context=True)
    control = control or RunControl()
    control.check()
    resource_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    audio = audio.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    prepared = output / 'audio.wav'
    command = ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(audio)]
    if duration_seconds is not None:
        command += ['-t', str(duration_seconds)]
    control.announce('Hang előkészítése…')
    control.run(command + ['-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le', str(prepared)],
                output / 'decode.log')
    control.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=nw=1:nk=1', str(prepared)], output / 'duration.log')
    duration = float((output / 'duration.log').read_text())
    started = time.monotonic()
    control.announce('1. próba · Helyi felismerés…')
    attempts = 1
    recovered_timeout = False
    try:
        recognition = recognizer(prepared)
    except ProcessingTimeout:
        control.check()
        control.attempt = attempts = 2
        control.announce('Nincs előrehaladás. 2. és utolsó próba, visszaállított felismerési állapottal…')
        recognition = (retry_recognizer or recognizer)(prepared)
        recovered_timeout = True
    control.check()
    if not any(segment.text.strip() for segment in recognition.segments):
        raise ValueError('No speech was recognized')
    repetition_flags = repetitions(' '.join(s.text for s in recognition.segments))
    # A repeated phrase can be real speech. Warn without another whole-file pass
    # or destructive text deduplication; timeout recovery above remains bounded.
    control.check()
    elapsed = time.monotonic() - started
    previous_start = 0.0
    for segment in recognition.segments:
        if not (math.isfinite(segment.start) and math.isfinite(segment.end)
                and previous_start <= segment.start <= segment.end <= duration):
            raise ValueError('Recognizer returned invalid or unordered timestamps')
        previous_start = segment.start
    segments = recognition.segments
    diarization: dict[str, object] = {'status': 'disabled'}
    diarization_warnings: tuple[str, ...] = ()
    if diarizer is not None:
        control.announce('Beszélők elkülönítése…')
        diarization_started = time.monotonic()
        try:
            detected = diarizer(prepared)
            if not detected.turns:
                raise ValueError('No speaker turns detected')
            if any(not (math.isfinite(t.start) and math.isfinite(t.end)
                        and 0 <= t.start < t.end <= duration) for t in detected.turns):
                raise ValueError('Invalid speaker timestamps')
            segments = label_segments(segments, detected)
            diarization_warnings = detected.warnings
            diarization = {'status': 'completed', 'model': detected.model,
                           'turns': [asdict(t) for t in detected.turns],
                           'warnings': list(detected.warnings),
                           'uncertain_speakers': list(detected.uncertain_speakers)}
        except (OSError, ValueError, subprocess.SubprocessError, ProcessingTimeout) as error:
            diarization = {'status': 'failed', 'error': type(error).__name__}
        diarization['seconds'] = time.monotonic() - diarization_started
    control.check()
    review_notices: list[dict[str, float | str]] = [{'start': w.start, 'end': w.end, 'kind': 'low_probability'}
                      for s in recognition.segments for w in s.words
                      if w.probability is not None and math.isfinite(w.probability)
                      and 0 <= w.probability < WORD_REVIEW_THRESHOLD
                      and math.isfinite(w.start) and math.isfinite(w.end)
                      and s.start <= w.start < w.end <= s.end]
    quality_warnings: list[str] = []
    overlap_analysis: dict[str, object] = {'status': 'not_requested'}
    if quality_analyzer is not None:
        control.announce('Egyszerre beszélés vizsgálata…')
        quality_warnings.append('A jelölések ellenőrizendő modelljelzések. '
                                'Az érthetetlen részeket nem ismerjük fel megbízhatóan; '
                                'a jelölés hiánya nem bizonyít hibátlan leiratot.')
        try:
            analysis = quality_analyzer(prepared)
            if any(not (math.isfinite(t.start) and math.isfinite(t.end)
                        and 0 <= t.start < t.end <= duration) for t in analysis.overlaps):
                raise ValueError('Invalid overlap timestamps')
            review_notices.extend({'start': t.start, 'end': t.end, 'kind': 'overlap'}
                                  for t in analysis.overlaps)
            overlap_analysis = {'status': 'completed', 'model': analysis.model}
        except (OSError, ValueError, subprocess.SubprocessError, ProcessingTimeout) as error:
            overlap_analysis = {'status': 'failed', 'error': type(error).__name__}
            quality_warnings.append('Az egyszerre beszélés vizsgálata nem sikerült; '
                                    'ilyen jelölés nélkül készült a leirat.')
        if not any(w.probability is not None for s in recognition.segments for w in s.words):
            quality_warnings.append('A felismerő nem adott szószintű bizonytalansági jelet; '
                                    'ez alapján nem jelölhetők ellenőrizendő szavak.')
    elif review_notices:
        quality_warnings.append('Az alacsony szóvalószínűség ellenőrzési jel, '
                                'nem bizonyítja a hang érthetetlenségét.')
    control.check()
    timed_lines = [(s.start, 1, f'[{timestamp(s.start)} – {timestamp(s.end)}] '
                    f'{s.speaker + ": " if s.speaker else ""}{s.text.strip()}')
                   for s in segments if s.text.strip()]
    timed_lines.extend((float(n['start']), 0,
                        f'[{timestamp(float(n["start"]))} – {timestamp(float(n["end"]))}] '
                        + ('[egyszerre beszélnek]' if n['kind'] == 'overlap'
                           else '[ellenőrizendő: bizonytalan felismerés]')) for n in review_notices)
    lines = [line for _, _, line in sorted(timed_lines)]
    result = TrialResult(output / 'transcript.txt', output / 'transcript.md', output / 'report.json')
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    with audio.open('rb') as source:
        source_sha = hashlib.file_digest(source, 'sha256').hexdigest()
    report: dict[str, object] = {
        'attempts': attempts,
        'retry': {},
        'recovered_timeout': recovered_timeout,
        'segmentation': 'Whisper internal windows; no application cuts or text deduplication',
        'model': asdict(recognition.model),
        'audio_seconds': duration,
        'recognition_seconds': elapsed,
        'source_sha256': source_sha,
        'resources': {'child_user_cpu_seconds': usage.ru_utime - resource_start.ru_utime,
                      'child_system_cpu_seconds': usage.ru_stime - resource_start.ru_stime,
                      'maximum_child_rss_bytes': usage.ru_maxrss * (1 if platform.system() == 'Darwin' else 1024),
                      'note': 'Process-lifetime maximum child RSS; not combined GPU/CPU memory.'},
        'segments': [asdict(s) for s in segments],
        'diarization': diarization,
        'quality': {'notices': review_notices, 'overlap': overlap_analysis,
                    'warnings': quality_warnings, 'unintelligibility_detection': 'unsupported',
                    'word_probability_threshold': WORD_REVIEW_THRESHOLD,
                    'note': 'Whisper token likelihood is not calibrated transcription accuracy.'},
        'human_quality_accepted': False,
        'repetition_flags': repetition_flags,
        'hardware': hardware_identity(),
    }
    if reference is not None:
        from jiwer import process_words
        selected = []
        for block in re.split(r'\n\s*\n', reference.read_text(encoding='utf-8').strip()):
            match = re.match(r'(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)', block)
            if match is None:
                raise ValueError('Reference must contain timestamped speaker blocks')
            h, m, s, ms, eh, em, es, ems = map(int, match.groups())
            start = h * 3600 + m * 60 + s + ms / 1000
            end = eh * 3600 + em * 60 + es + ems / 1000
            if start < duration and end > duration + 0.001:
                raise ValueError('Reference block crosses the audio boundary; align the audio cut')
            if start < duration and end <= duration + 0.001:
                selected.append(block)
        text = normalize(clean_reference('\n\n'.join(selected)))
        if not text:
            raise ValueError('No complete reference blocks inside the audio window')
        comparison = process_words(text, normalize(' '.join(s.text for s in recognition.segments)))
        report['comparison'] = {
            'reference_words': len(text.split()),
            'word_error_rate': comparison.wer,
            'substitutions': comparison.substitutions,
            'deletions': comparison.deletions,
            'insertions': comparison.insertions,
            'note': 'Agreement with an automatic reference; not verified accuracy.',
        }
    for warning in reversed([*diarization_warnings, *quality_warnings]):
        lines.insert(0, f'Figyelmeztetés: {warning}')
    if diarization['status'] == 'failed':
        lines.insert(0, 'Figyelmeztetés: Beszélők elkülönítése nem sikerült; '
                     'a leirat beszélőjelölés nélkül készült. Ellenőrizd a kiegészítő modell beállítását.')
    if report['repetition_flags']:
        suspect = [s for s in recognition.segments if repetitions(s.text)]
        start = min(s.start for s in suspect) if suspect else 0.0
        end = max(s.end for s in suspect) if suspect else duration
        lines.insert(0, f'[{timestamp(start)} – {timestamp(end)}] Figyelmeztetés: gyanús ismétlődés; '
                     'Nem bizonyított felismerési hiba. Az eredeti szöveget megőriztük; '
                     'ellenőrizd a jelzett hangrészt.')
    if recovered_timeout:
        lines.insert(0, f'[00:00:00 – {timestamp(duration)}] Figyelmeztetés: az első próba elakadt; '
                     'a leirat az egyszeri újrapróba eredménye.')
    control.announce('Leirat exportálása…')
    result.text_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    result.markdown_path.write_text('# Leirat\n\n' + '\n\n'.join(lines) + '\n', encoding='utf-8')
    result.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--engine', choices=['mlx'], required=True)
    parser.add_argument('--language', choices=['hu', 'en'], default='hu')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--speakers', action='store_true')
    parser.add_argument('--speaker-models', type=Path, default=Path(__file__).parent / 'models/speakers')
    args = parser.parse_args()
    engine: Literal['mlx'] = 'mlx'
    control = RunControl()
    recognizer = ProcessRecognizer(engine, args.model, language=args.language, control=control)
    from .speakers import ProcessDiarizer
    from .speech_quality import ProcessQualityAnalyzer
    diarizer = ProcessDiarizer(args.speaker_models, control, prepare_on_demand=True) if args.speakers else None
    result = run_transcription(args.audio, args.output, recognizer, control=control,
                       duration_seconds=args.duration, reference=args.reference, diarizer=diarizer,
                       quality_analyzer=ProcessQualityAnalyzer(args.speaker_models / 'segmentation.onnx', control))
    summary = json.loads(result.report_path.read_text())
    del summary['segments']
    summary['report_path'] = str(result.report_path)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
