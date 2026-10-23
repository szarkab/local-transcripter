"""Bounded-memory, offline overlap candidates from pinned powerset segmentation."""
import argparse
import hashlib
import json
from pathlib import Path
import wave

import numpy as np
import onnxruntime as ort

from .prepare_speakers import SEGMENTATION_SHA

MIN_OVERLAP_SECONDS = .3
MIN_WINDOW_AGREEMENT = .8


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('audio', 'model', 'result', 'progress'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with args.model.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != SEGMENTATION_SHA:
            raise ValueError('Unexpected overlap model identity')
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 4
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(args.model), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    metadata = session.get_modelmeta().custom_metadata_map
    if (metadata.get('model_type'), metadata.get('num_classes'), metadata.get('sample_rate'),
            metadata.get('powerset_max_classes')) != ('pyannote-segmentation-3.0', '7', '16000', '2'):
        raise ValueError('Unsupported powerset model')
    rate = int(metadata['sample_rate'])
    window = int(metadata['window_size'])
    shift = int(metadata['receptive_field_shift'])
    receptive_field = int(metadata['receptive_field_size'])
    hop = (window // 2 // shift) * shift  # Frame-aligned, approximately 5 seconds.
    with wave.open(str(args.audio)) as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, rate):
            raise ValueError('Expected prepared mono 16 kHz PCM audio')
        samples = source.getnframes()
        duration = samples / rate
        count = (samples + shift - 1) // shift
        overlap_votes = np.zeros(count, dtype=np.int32)
        window_votes = np.zeros(count, dtype=np.int32)
        for start in range(0, samples, hop):
            source.setpos(start)
            audio = np.frombuffer(source.readframes(window), dtype='<i2').astype(np.float32) / 32768
            audio = np.pad(audio, (0, window - len(audio)))
            scores = session.run(None, {'x': audio.reshape(1, 1, -1)})[0][0]
            if scores.ndim != 2 or scores.shape[1] != 7 or not np.isfinite(scores).all():
                raise ValueError('Invalid powerset output')
            indexes = start // shift + np.arange(scores.shape[0])
            valid = (indexes * shift + receptive_field / 2 < samples) & (indexes < count)
            indexes = indexes[valid]
            # Classes 0=non-speech, 1..3=one voice, 4..6=two simultaneous voices.
            overlap_votes[indexes] += (np.argmax(scores[valid], axis=1) >= 4).astype(np.int32)
            window_votes[indexes] += 1
            temporary = args.progress.with_suffix('.tmp')
            temporary.write_text(json.dumps({'seconds': min(duration, (start + hop) / rate),
                                             'total': duration}))
            temporary.replace(args.progress)
    active = ((window_votes > 0)
              & (overlap_votes >= MIN_WINDOW_AGREEMENT * window_votes))
    intervals: list[dict[str, float]] = []
    begin: int | None = None
    for index, enabled in enumerate(np.append(active, False)):
        if enabled and begin is None:
            begin = index
        if not enabled and begin is not None:
            # Model frame centres define approximate boundaries; never go beyond the audio.
            start_time = max(0.0, (begin * shift + receptive_field / 2 - shift / 2) / rate)
            end_time = min(duration, (index * shift + receptive_field / 2 - shift / 2) / rate)
            if end_time - start_time >= MIN_OVERLAP_SECONDS:
                intervals.append({'start': start_time, 'end': end_time})
            begin = None
    args.result.write_text(json.dumps({'overlaps': intervals, 'model': {
        'backend': 'onnxruntime', 'version': ort.__version__, 'sha256': SEGMENTATION_SHA,
        'model': 'pyannote-segmentation-3.0 (sherpa-onnx public ONNX)',
        'device': 'cpu', 'threads': 4, 'sample_rate': rate, 'window_samples': window,
        'hop_samples': hop, 'receptive_field_size': receptive_field, 'frame_shift': shift,
        'minimum_duration_seconds': MIN_OVERLAP_SECONDS,
        'minimum_window_agreement': MIN_WINDOW_AGREEMENT,
        'note': 'Heuristic model candidates, not verified overlap or calibrated confidence.',
    }}, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
