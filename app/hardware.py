from __future__ import annotations

import platform
import shutil
import subprocess
import os
import site
import sys
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path


_DLL_DIRECTORY_HANDLES = []


@dataclass(frozen=True)
class HardwareAccelerationStatus:
    platform: str
    cuda_available: bool
    cuda_device_count: int
    cuda_runtime_ready: bool
    missing_cuda_libraries: list[str]
    nvidia_smi_available: bool
    message: str
    nvidia_driver_status: str = "unknown"
    nvidia_gpu_names: list[str] = field(default_factory=list)
    ctranslate2_cuda_status: str = "unknown"
    cuda_runtime_status: str = "unknown"
    fallback_mode: str = "unknown"

    def as_dict(self) -> dict:
        return asdict(self)


def _ctranslate2_cuda_device_count() -> tuple[int, str | None]:
    try:
        import ctranslate2  # type: ignore
    except Exception as exc:
        return 0, f"CTranslate2 is not available: {exc}"

    detector = getattr(ctranslate2, "get_cuda_device_count", None)
    if detector is None:
        return 0, "This CTranslate2 build does not expose CUDA detection."

    try:
        return max(0, int(detector())), None
    except Exception as exc:
        return 0, f"CTranslate2 CUDA detection failed: {exc}"


def _nvidia_smi_info() -> tuple[bool, list[str], str | None]:
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False, [], "nvidia-smi was not found on PATH."
    try:
        result = subprocess.run(
            [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return True, names, None
    except Exception as exc:
        return False, [], f"nvidia-smi could not query the GPU: {exc}"


def _has_nvidia_smi() -> bool:
    available, _names, _message = _nvidia_smi_info()
    return available


def _dll_exists_on_path(name: str) -> bool:
    for item in _python_cuda_dll_dirs():
        try:
            if (item / name).exists():
                return True
        except OSError:
            continue
    for item in os.environ.get("PATH", "").split(os.pathsep):
        if not item:
            continue
        try:
            if os.path.exists(os.path.join(item, name)):
                return True
        except OSError:
            continue
    return False


def _dll_pattern_exists_on_path(pattern: str) -> bool:
    for item in _python_cuda_dll_dirs():
        try:
            if any(item.glob(pattern)):
                return True
        except OSError:
            continue
    for item in os.environ.get("PATH", "").split(os.pathsep):
        if not item:
            continue
        try:
            if any(Path(item).glob(pattern)):
                return True
        except OSError:
            continue
    return False


@lru_cache(maxsize=1)
def _python_cuda_dll_dirs() -> tuple[Path, ...]:
    if platform.system() != "Windows":
        return ()

    roots: list[Path] = []
    try:
        roots.extend(Path(p) for p in site.getsitepackages())
    except Exception:
        pass
    try:
        roots.append(Path(site.getusersitepackages()))
    except Exception:
        pass
    roots.append(Path(sys.prefix) / "Lib" / "site-packages")

    dirs: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        nvidia_root = root / "nvidia"
        if not nvidia_root.exists():
            continue
        for candidate in nvidia_root.glob("**/*"):
            if not candidate.is_dir() or candidate.name.lower() not in {"bin", "lib"}:
                continue
            key = str(candidate.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            dirs.append(candidate)
    return tuple(dirs)


def prepare_python_cuda_dll_dirs() -> tuple[str, ...]:
    """Expose venv-installed NVIDIA CUDA wheel DLLs to Windows loaders."""
    dirs = _python_cuda_dll_dirs()
    if platform.system() != "Windows":
        return tuple(str(path) for path in dirs)

    existing_path = os.environ.get("PATH", "")
    path_parts = existing_path.split(os.pathsep) if existing_path else []
    added: list[str] = []
    for path in dirs:
        path_str = str(path)
        if path_str not in path_parts:
            path_parts.insert(0, path_str)
            added.append(path_str)
        add_dll_directory = getattr(os, "add_dll_directory", None)
        if add_dll_directory is not None:
            try:
                _DLL_DIRECTORY_HANDLES.append(add_dll_directory(path_str))
            except OSError:
                pass
    if added:
        os.environ["PATH"] = os.pathsep.join(path_parts)
    return tuple(str(path) for path in dirs)


def _cuda_runtime_status(system_name: str) -> tuple[bool, list[str]]:
    if system_name != "Windows":
        return True, []

    # CTranslate2's Windows CUDA backend needs NVIDIA runtime DLLs available
    # on PATH. Missing cuBLAS or cuDNN DLLs can make model loading fail even when
    # the NVIDIA driver and CUDA device are visible.
    required = ["cublas64_12.dll"]
    missing = [name for name in required if not _dll_exists_on_path(name)]
    if not _dll_pattern_exists_on_path("cudnn*.dll"):
        missing.append("cudnn*.dll")
    return not missing, missing


@lru_cache(maxsize=1)
def detect_hardware_acceleration() -> HardwareAccelerationStatus:
    system_name = platform.system()
    prepare_python_cuda_dll_dirs()
    cuda_count, cuda_message = _ctranslate2_cuda_device_count()
    nvidia_smi_available, nvidia_gpu_names, nvidia_message = _nvidia_smi_info()
    cuda_runtime_ready, missing_cuda_libraries = _cuda_runtime_status(system_name)
    cuda_ready = cuda_count > 0 and cuda_runtime_ready

    if system_name == "Windows":
        nvidia_driver_status = "detected" if nvidia_smi_available else "not_detected"
        if cuda_count > 0:
            ctranslate2_cuda_status = "usable"
        elif nvidia_smi_available:
            ctranslate2_cuda_status = "not_exposed"
        else:
            ctranslate2_cuda_status = "not_detected"
        cuda_runtime_status = "ready" if cuda_runtime_ready else "missing_dlls"
    else:
        nvidia_driver_status = "not_applicable"
        ctranslate2_cuda_status = "not_applicable"
        cuda_runtime_status = "not_applicable"

    fallback_mode = "faster-whisper CUDA" if cuda_ready else "CPU / int8"

    if cuda_ready:
        names = f" ({', '.join(nvidia_gpu_names)})" if nvidia_gpu_names else ""
        message = f"CUDA ready: NVIDIA driver detected{names}, CTranslate2 sees {cuda_count} CUDA device(s), and required runtime DLLs are available. Church Cap can use faster-whisper on CUDA."
    elif cuda_count > 0 and not cuda_runtime_ready:
        missing = ", ".join(missing_cuda_libraries)
        message = (
            f"CUDA not ready: CTranslate2 can see {cuda_count} CUDA device(s), but required runtime DLLs are missing: {missing}. "
            "Church Cap will fall back to CPU / int8 until the local NVIDIA CUDA runtime is repaired."
        )
    elif nvidia_smi_available:
        names = f" ({', '.join(nvidia_gpu_names)})" if nvidia_gpu_names else ""
        detail = f" {cuda_message}" if cuda_message else ""
        message = (
            f"CUDA not ready: NVIDIA driver/GPU detected{names}, but CTranslate2 does not expose CUDA to faster-whisper.{detail} "
            "Church Cap will fall back to CPU / int8."
        )
    else:
        detail = cuda_message or nvidia_message or "No NVIDIA CUDA-capable GPU was detected."
        message = f"CUDA not ready: {detail} Church Cap will use CPU / int8."

    return HardwareAccelerationStatus(
        platform=system_name,
        cuda_available=cuda_ready,
        cuda_device_count=cuda_count,
        cuda_runtime_ready=cuda_runtime_ready,
        missing_cuda_libraries=missing_cuda_libraries,
        nvidia_smi_available=nvidia_smi_available,
        message=message,
        nvidia_driver_status=nvidia_driver_status,
        nvidia_gpu_names=nvidia_gpu_names,
        ctranslate2_cuda_status=ctranslate2_cuda_status,
        cuda_runtime_status=cuda_runtime_status,
        fallback_mode=fallback_mode,
    )


def resolve_whisper_runtime(
    requested_device: str,
    requested_compute_type: str,
    status: HardwareAccelerationStatus | None = None,
) -> tuple[str, str]:
    """Resolve user-friendly auto settings into explicit faster-whisper values."""
    status = status or detect_hardware_acceleration()
    device = (requested_device or "auto").strip().lower()
    compute_type = (requested_compute_type or "auto").strip().lower()

    if device == "auto":
        device = "cuda" if status.cuda_available else "cpu"

    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    return device, compute_type
