"""Non-sensitive hardware and local artifact identity for reproducible trials."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess


def artifact_identity(model: Path) -> dict[str, str]:
    identities = {}
    for name in ('config.json', 'model.bin', 'weights.npz', 'weights.safetensors',
                 'tokenizer.json', 'vocabulary.json', 'preprocessor_config.json'):
        path = model / name
        if path.is_file():
            with path.open('rb') as source:
                identities[name] = hashlib.file_digest(source, 'sha256').hexdigest()
    return identities


def hardware_identity() -> dict[str, str | int]:
    hardware: dict[str, str | int] = {
        'platform': platform.platform(), 'architecture': platform.machine(),
        'logical_cpus': os.cpu_count() or 0, 'chip':'Unavailable', 'memory':'Unavailable',
    }
    if platform.system() == 'Darwin':
        try:
            output = subprocess.check_output(
                ['system_profiler', 'SPHardwareDataType', '-json'], text=True, timeout=15)
            record = json.loads(output)['SPHardwareDataType'][0]
            for key, field in [('chip', 'chip_type'), ('memory', 'physical_memory'),
                               ('model', 'machine_model')]:
                value = record.get(field)
                if isinstance(value, str):
                    hardware[key] = value
        except (subprocess.SubprocessError, KeyError, IndexError, ValueError, OSError):
            pass  # Report unavailable facts explicitly, rather than inventing hardware.
    return hardware
