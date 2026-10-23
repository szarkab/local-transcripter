"""Offline recognizer process. Receives audio and model paths, never a reference."""
import argparse
from contextlib import redirect_stderr
import io
import re
import sys
from importlib.metadata import version
import json
import os
from pathlib import Path
from .provenance import artifact_identity


class ProgressStream(io.TextIOBase):
    """Adapt MLX Whisper's existing frame progress, without altering its decoding."""
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, text: str) -> int:
        assert sys.__stderr__ is not None
        sys.__stderr__.write(text)
        match = re.search(r'(\d+)/(\d+)\s*\[', text)
        if match:
            current, total = map(int, match.groups())
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(json.dumps({'seconds': current / 100, 'total': total / 100}))
            temporary.replace(self.path)
        return len(text)

    def flush(self) -> None:
        assert sys.__stderr__ is not None
        sys.__stderr__.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=['mlx'], required=True)
    parser.add_argument('--language', choices=['hu', 'en'], default='hu')
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--result', type=Path, required=True)
    parser.add_argument('--progress', type=Path)
    context = parser.add_mutually_exclusive_group()
    context.add_argument('--reset-context', dest='reset_context', action='store_true', default=True)
    context.add_argument('--carry-context', dest='reset_context', action='store_false',
                         help='Diagnostic comparison only: feed recognized text into later windows')
    args = parser.parse_args()
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    model_path: Path = args.model.resolve(strict=True)
    provenance = json.loads((model_path / 'provenance.json').read_text())
    artifacts = artifact_identity(model_path)
    import mlx_whisper
    stream = ProgressStream(args.progress) if args.progress else sys.stderr
    with redirect_stderr(stream):
        result = mlx_whisper.transcribe(
            str(args.audio), path_or_hf_repo=str(model_path), language=args.language,
            task='transcribe', word_timestamps=True, temperature=0.0, verbose=False,
            condition_on_previous_text=not args.reset_context,
        )
    output = [{'start':s['start'], 'end':s['end'], 'text':s['text'],
               'words': [{'start':w['start'], 'end':w['end'], 'text':w['word'], 'probability':w.get('probability')}
                         for w in s.get('words', [])]} for s in result['segments']]
    settings = {'device':'gpu', 'compute_type':'float16', 'language':args.language, 'temperature':0.0,
                'condition_on_previous_text':not args.reset_context, 'mlx_version':version('mlx'),
                'mlx_whisper_version':version('mlx-whisper'), 'mlx_metal_version':version('mlx-metal')}
    tokenizer = provenance.get('tokenizer', {})
    for key in ('repository', 'revision'):
        if key in tokenizer:
            settings[f'tokenizer_{key}'] = str(tokenizer[key])
    args.result.write_text(json.dumps({
        'segments':output,
        'model': {'backend':args.engine, 'repository':provenance['repository'],
                  'revision':provenance['revision'], 'settings':settings,
                  'artifact_sha256':artifacts},
    }, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
