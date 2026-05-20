#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.hardware import detect_hardware_acceleration, resolve_whisper_runtime


parser = argparse.ArgumentParser(description="Check Church Cap GPU/CUDA support.")
parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
args = parser.parse_args()

status = detect_hardware_acceleration()
device, compute_type = resolve_whisper_runtime("auto", "auto", status)

if args.json:
    payload = status.as_dict()
    payload["resolved_device"] = device
    payload["resolved_compute_type"] = compute_type
    print(json.dumps(payload))
    raise SystemExit(0)

print("Church Cap GPU check")
print(f"Platform: {status.platform}")
print(f"CUDA available to faster-whisper: {'yes' if status.cuda_available else 'no'}")
print(f"CUDA device count: {status.cuda_device_count}")
print(f"CUDA runtime DLLs ready: {'yes' if status.cuda_runtime_ready else 'no'}")
if status.missing_cuda_libraries:
    print("Missing CUDA runtime files:", ", ".join(status.missing_cuda_libraries))
print(f"nvidia-smi available: {'yes' if status.nvidia_smi_available else 'no'}")
print(f"Automatic Whisper runtime: device={device}, compute_type={compute_type}")
print(status.message)
