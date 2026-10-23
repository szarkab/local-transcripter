"""Offline, globally clustered speaker turns; receives no transcript or reference."""
import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import wave

import numpy as np
import sherpa_onnx

CLUSTER_THRESHOLD = 1.15


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('audio', 'models', 'result', 'progress'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.models / 'provenance.json').read_text())
    for name in ('segmentation.onnx', 'embedding.onnx'):
        with (args.models / name).open('rb') as source:
            if hashlib.file_digest(source, 'sha256').hexdigest() != manifest['files'][name]['sha256']:
                raise ValueError('Speaker model identity mismatch')
    with wave.open(str(args.audio)) as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError('Expected prepared mono 16 kHz PCM audio')
        samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32) / 32768
    duration = len(samples) / 16000
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                model=str(args.models / 'segmentation.onnx'), window_shift_ratio=.1),
            num_threads=4, provider='cpu'),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
            model=str(args.models / 'embedding.onnx'), num_threads=4, provider='cpu'),
        clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=CLUSTER_THRESHOLD),
        min_duration_on=.3, min_duration_off=.5)
    if not config.validate():
        raise ValueError('Invalid local speaker model configuration')
    diarizer = sherpa_onnx.OfflineSpeakerDiarization(config)

    def progress(done: int, total: int) -> int:
        temporary = args.progress.with_suffix('.tmp')
        temporary.write_text(json.dumps({'seconds': duration * done / max(total, 1), 'total': duration}))
        temporary.replace(args.progress)
        return 0

    turns = diarizer.process(samples, callback=progress).sort_by_start_time()
    output: list[dict[str, str | float]] = [{'start': max(0.0, float(t.start)), 'end': min(duration, float(t.end)),
               'speaker': str(t.speaker)} for t in turns if 0 <= t.start < min(duration, t.end)]
    count = len({turn['speaker'] for turn in output})
    warnings = [f'Automatikusan becsült beszélőszám: {count}. '
                'A címkék tévesen szétválaszthatnak vagy összevonhatnak hangokat; ellenőrizd őket a hang alapján.']
    args.result.write_text(json.dumps({'turns': output, 'uncertain_speakers': [],
                                      'warnings': warnings, 'model': {
        'backend': 'sherpa-onnx', 'version': version('sherpa-onnx'),
        'files': manifest['files'], 'clustering': 'whole recording; automatic count', 'threshold': CLUSTER_THRESHOLD,
        'estimated_speakers': count,
        'device': 'cpu', 'threads': 4,
    }}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
