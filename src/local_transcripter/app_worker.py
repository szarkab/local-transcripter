"""Native app bridge to the same file-to-export pipeline as the quality trial."""
import argparse
import signal
import threading
import json
from pathlib import Path
import subprocess
import sys

from .pipeline import ProcessRecognizer, run_transcription
from .execution import RunControl, CancelledError, ProcessingTimeout
from .speakers import ProcessDiarizer
from .speech_quality import ProcessQualityAnalyzer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--speaker-models', type=Path, default=Path(__file__).parent / 'models/speakers')
    parser.add_argument('--speakers', action='store_true')
    parser.add_argument('--language', choices=['hu', 'en'], default='hu')
    parser.add_argument('--prepare-speakers', action='store_true')
    parser.add_argument('--prepare-model', action='store_true')
    parser.add_argument('--check-model', action='store_true')
    args = parser.parse_args()
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda signum, frame: stopped.set())
    signal.signal(signal.SIGINT, lambda signum, frame: stopped.set())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    status_path = args.output.with_suffix('.status.json')
    progress_seconds: float | None = None
    progress_total: float | None = None

    def publish(message: str) -> None:
        state: dict[str, str | float] = {'message': message}
        if progress_seconds is not None and progress_total is not None:
            state['seconds'] = progress_seconds
            state['total'] = progress_total
        temporary = status_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
        temporary.replace(status_path)

    def update_progress(seconds: float | None, total: float | None) -> None:
        nonlocal progress_seconds, progress_total
        progress_seconds, progress_total = seconds, total

    control = RunControl(cancelled=stopped.is_set, on_status=publish, on_progress=update_progress)
    try:
        if args.prepare_model or args.check_model:
            from .prepare_base import prepare, ready
            if args.model is None:
                raise ValueError('Model directory is required')
            note = None
            if args.prepare_model:
                prepare(args.model, control)
                # Optional model preparation may fail without blocking the accepted base recognizer.
                from .prepare_speakers import prepare as prepare_speakers
                try:
                    prepare_speakers(args.speaker_models, control)
                except (OSError, ValueError):
                    note = 'A kiegészítő beszélőmodell előkészítése nem sikerült; az alapátírás használható.'
            print(json.dumps({'ready': ready(args.model), 'note': note}), flush=True)
            return
        if args.prepare_speakers:
            from .prepare_speakers import prepare
            prepare(args.speaker_models, control)
            print(json.dumps({'prepared': True}), flush=True)
            return
        if args.audio is None or args.model is None:
            raise ValueError('Audio and recognition model are required')
        recognizer = ProcessRecognizer('mlx', args.model, language=args.language, control=control)
        diarizer = ProcessDiarizer(args.speaker_models, control, prepare_on_demand=True) if args.speakers else None
        result = run_transcription(args.audio, args.output, recognizer, control=control,
                           diarizer=diarizer,
                           quality_analyzer=ProcessQualityAnalyzer(args.speaker_models / 'segmentation.onnx', control))
        report = json.loads(result.report_path.read_text())
        print(json.dumps({'transcript': str(result.text_path),
                          'markdown': str(result.markdown_path),
                          'quality_note': 'Az érthetetlenség automatikus felismerése nem támogatott.'
                          + (' Az egyszerre beszélés vizsgálata nem sikerült.'
                             if report['quality']['overlap']['status'] == 'failed' else ''),
                          'repetition_warnings': len(report['repetition_flags']) + int(report['recovered_timeout'])
                          + int(report['diarization']['status'] == 'failed')
                          + int(bool(report['diarization'].get('warnings')))
                          + int(any(s['speaker'] == 'Beszélő bizonytalan' for s in report['segments']))
                          + len(report['quality']['warnings']) + len(report['quality']['notices'])}), flush=True)
    except CancelledError:
        print('A modell előkészítése megszakítva.' if args.prepare_speakers or args.prepare_model else
              'A feldolgozás megszakítva. Nem készült teljes leirat.', file=sys.stderr, flush=True)
        sys.exit(130)
    except ProcessingTimeout:
        print('A felismerő két próbálkozás után sem haladt előre, ezért leállítottuk. '
              'Nem készült teljes leirat.', file=sys.stderr, flush=True)
        sys.exit(1)
    except (OSError, ValueError, subprocess.SubprocessError):
        if args.prepare_speakers or args.prepare_model or args.check_model:
            print('A modell előkészítése nem sikerült. Ellenőrizd az internetkapcsolatot és a szabad tárhelyet.',
                  file=sys.stderr, flush=True)
            sys.exit(1)
        # Keep model logs locally; do not expose private audio text in UI diagnostics.
        print('A hang beolvasása vagy a helyi felismerés nem sikerült. '
              'Ellenőrizd a hangfájlt, a helyi modellt és a szabad tárhelyet. '
              f'A futás mappája: {args.output}', file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
