"""Bounded log handling and conservative Church Cap storage accounting.

Only known, reproducible downloads and archived logs are offered for cleanup.
Runtime settings, transcripts, current logs, and active models are never cleanup
candidates.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Iterable


MAX_LOG_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 2
TAIL_MAX_BYTES = 256 * 1024

WHISPER_MODEL_LABELS = {
    "tiny.en": "Whisper tiny.en",
    "base.en": "Whisper base.en",
    "small.en": "Whisper small.en",
    "medium.en": "Whisper medium.en",
}


def _path_size(path: Path) -> int:
    """Return a best-effort size without following symlinks."""
    try:
        if path.is_symlink():
            return path.lstat().st_size
        if path.is_file():
            return path.stat().st_size
        if not path.is_dir():
            return 0
    except OSError:
        return 0

    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _cache_roots(
    *,
    huggingface_hub_cache: Path | None = None,
    whisper_cache: Path | None = None,
) -> tuple[Path, Path]:
    if huggingface_hub_cache is None:
        hf_home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
        huggingface_hub_cache = Path(os.environ.get("HUGGINGFACE_HUB_CACHE") or hf_home / "hub")
    if whisper_cache is None:
        xdg_cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        whisper_cache = xdg_cache / "whisper"
    return Path(huggingface_hub_cache), Path(whisper_cache)


def _category(identifier: str, label: str, path: Path, description: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "bytes": _path_size(path),
        "description": description,
    }


def _faster_whisper_model_from_dir(path: Path) -> str | None:
    name = path.name.lower()
    marker = "faster-whisper-"
    if marker not in name:
        return None
    model = name.split(marker, 1)[1].replace("--", "/")
    return model if model in WHISPER_MODEL_LABELS else None


def _cleanup_candidates(
    project_root: Path,
    app_support: Path,
    runtime: dict[str, Any],
    hub_cache: Path,
    whisper_cache: Path,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    active_model = str(runtime.get("whisper_model") or "base.en").lower()
    active_backend = str(runtime.get("transcriber_mode") or "faster_whisper").lower()

    if hub_cache.is_dir():
        try:
            hub_entries = list(hub_cache.iterdir())
        except OSError:
            hub_entries = []
        for path in hub_entries:
            model = _faster_whisper_model_from_dir(path)
            if not model or (active_backend == "faster_whisper" and model == active_model):
                continue
            size = _path_size(path)
            if not size:
                continue
            candidates.append({
                "id": f"faster-whisper:{model}",
                "label": f"Unused {WHISPER_MODEL_LABELS[model]} download",
                "bytes": size,
                "description": "Safe to remove while inactive; selecting this model later downloads it again.",
                "recommended": False,
                "_paths": [path],
            })

    if whisper_cache.is_dir():
        for model, label in WHISPER_MODEL_LABELS.items():
            path = whisper_cache / f"{model}.pt"
            if not path.exists() or (active_backend == "whisper" and model == active_model):
                continue
            candidates.append({
                "id": f"openai-whisper:{model}",
                "label": f"Unused {label} download",
                "bytes": _path_size(path),
                "description": "Safe to remove while inactive; selecting this model later downloads it again.",
                "recommended": False,
                "_paths": [path],
            })

    source_cache = hub_cache / "models--alirezamsh--small100"
    converted_model = project_root / "data" / "models" / "small100-ct2-int8" / "model.bin"
    translation_provider = str(runtime.get("translation_provider") or "argos").lower()
    if (
        source_cache.exists()
        and converted_model.exists()
        and translation_provider not in {"small100", "both"}
    ):
        candidates.append({
            "id": "small100-source-cache",
            "label": "SMaLL-100 conversion source download",
            "bytes": _path_size(source_cache),
            "description": "The converted Recommended package is installed. Small tokenizer files may download again when it next starts.",
            "recommended": True,
            "_paths": [source_cache],
        })

    archived_logs: list[Path] = []
    for logs_root in (project_root / "logs", app_support / "logs"):
        if not logs_root.is_dir():
            continue
        try:
            entries = list(logs_root.iterdir())
        except OSError:
            continue
        archived_logs.extend(path for path in entries if path.is_file() and path.suffix in {".1", ".2"})
    archived_size = sum(_path_size(path) for path in archived_logs)
    if archived_size:
        candidates.append({
            "id": "archived-logs",
            "label": "Archived diagnostic logs",
            "bytes": archived_size,
            "description": "Older rotated logs only. Current troubleshooting logs are kept.",
            "recommended": True,
            "_paths": archived_logs,
        })

    return sorted(candidates, key=lambda item: (-int(item["bytes"]), str(item["label"])))


def storage_snapshot(
    project_root: Path,
    app_support: Path,
    runtime: dict[str, Any],
    *,
    huggingface_hub_cache: Path | None = None,
    whisper_cache: Path | None = None,
) -> dict[str, Any]:
    project_root = Path(project_root)
    app_support = Path(app_support)
    hub_cache, whisper_cache = _cache_roots(
        huggingface_hub_cache=huggingface_hub_cache,
        whisper_cache=whisper_cache,
    )
    logs_bytes = _path_size(project_root / "logs") + _path_size(app_support / "logs")
    categories = [
        _category("application", "Application and environment", project_root, "Church Cap code, local environment, and converted models."),
        _category("application-data", "Church Cap data", app_support, "Settings, retained measurements, transcripts, and support logs."),
        _category("huggingface-cache", "Hugging Face model downloads", hub_cache, "Downloaded Faster Whisper and SMaLL-100 source files."),
        _category("whisper-cache", "OpenAI Whisper model downloads", whisper_cache, "Downloaded models used by the compatibility transcription backend."),
    ]
    if _is_within(app_support, project_root):
        total_bytes = sum(item["bytes"] for item in categories if item["id"] != "application-data")
    else:
        total_bytes = sum(item["bytes"] for item in categories)

    candidates = _cleanup_candidates(project_root, app_support, runtime, hub_cache, whisper_cache)
    public_candidates = [{key: value for key, value in item.items() if key != "_paths"} for item in candidates]
    return {
        "total_bytes": total_bytes,
        "logs_bytes": logs_bytes,
        "categories": categories,
        "cleanup_candidates": public_candidates,
        "recommended_reclaimable_bytes": sum(int(item["bytes"]) for item in candidates if item.get("recommended")),
        "log_policy": {"maximum_bytes_per_log": MAX_LOG_BYTES, "backup_count": LOG_BACKUPS},
    }


def clear_storage_candidates(
    candidate_ids: Iterable[str],
    project_root: Path,
    app_support: Path,
    runtime: dict[str, Any],
    *,
    huggingface_hub_cache: Path | None = None,
    whisper_cache: Path | None = None,
) -> dict[str, Any]:
    hub_cache, whisper_cache = _cache_roots(
        huggingface_hub_cache=huggingface_hub_cache,
        whisper_cache=whisper_cache,
    )
    allowed = {
        item["id"]: item
        for item in _cleanup_candidates(Path(project_root), Path(app_support), runtime, hub_cache, whisper_cache)
    }
    selected = list(dict.fromkeys(str(item) for item in candidate_ids))
    unknown = [item for item in selected if item not in allowed]
    if unknown:
        raise ValueError("One or more cleanup selections are no longer available. Refresh Storage use and try again.")

    allowed_roots = (Path(project_root), Path(app_support), hub_cache, whisper_cache)
    reclaimed = 0
    cleared: list[str] = []
    for identifier in selected:
        item = allowed[identifier]
        for path in item["_paths"]:
            if not any(_is_within(path, root) for root in allowed_roots):
                raise ValueError("Cleanup path failed the Church Cap safety check.")
            reclaimed += _path_size(path)
            try:
                if path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
                else:
                    path.unlink(missing_ok=True)
            except OSError as exc:
                raise RuntimeError(f"Could not clear {item['label']}: {exc}") from exc
        cleared.append(str(item["label"]))
    return {"reclaimed_bytes": reclaimed, "cleared": cleared}


def rotate_log_file(path: Path, *, max_bytes: int = MAX_LOG_BYTES, backups: int = LOG_BACKUPS) -> bool:
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size <= max_bytes:
            return False
    except OSError:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    for number in range(max(1, backups), 0, -1):
        source = path if number == 1 else path.with_name(f"{path.name}.{number - 1}")
        destination = path.with_name(f"{path.name}.{number}")
        if not source.exists():
            continue
        if destination.exists():
            destination.unlink(missing_ok=True)
        source.replace(destination)
    return True


def rotate_runtime_logs(project_root: Path, app_support: Path) -> None:
    names = (
        Path(project_root) / "logs" / "update.log",
        Path(project_root) / "logs" / "update-restart.log",
        Path(project_root) / "logs" / "cuda-runtime-install.log",
        Path(project_root) / "logs" / "launchagent.out.log",
        Path(project_root) / "logs" / "launchagent.err.log",
        Path(app_support) / "logs" / "translation-install.log",
        Path(app_support) / "logs" / "church-cap.out.log",
        Path(app_support) / "logs" / "church-cap.err.log",
    )
    for path in names:
        rotate_log_file(path)


def tail_log_lines(path: Path, *, max_lines: int = 160, max_bytes: int = TAIL_MAX_BYTES) -> list[str]:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            start = max(0, size - max_bytes)
            handle.seek(start)
            data = handle.read(max_bytes)
    except OSError as exc:
        return [f"Could not read log: {exc}"]
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if start and lines:
        lines = lines[1:]
    return lines[-max_lines:]
