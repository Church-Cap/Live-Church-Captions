"""Safe, bounded removal of Church Cap's mutable local state."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.paths import app_support_dir, model_data_dir


FACTORY_RESET_MARKER_NAME = "factory_reset.flag"
FACTORY_RESET_DIRECTORIES = (
    "data",
    "config",
    "cache",
    "logs",
    "updates",
    "recovery",
    "exports",
    "models",
    "tts",
    "cuda-runtime",
)


@dataclass(frozen=True)
class FactoryResetResult:
    support_dir: Path
    removed: tuple[Path, ...]
    marker: Path


def _resolved_safe_target(path: Path, *, forbidden: tuple[Path, ...]) -> Path:
    target = path.expanduser().resolve(strict=False)
    if target == Path(target.anchor) or any(target == item.resolve(strict=False) for item in forbidden):
        raise ValueError(f"Refusing unsafe factory-reset target: {target}")
    return target


def _remove_staged(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def factory_reset_local_state(
    *,
    support_dir: Path | None = None,
    models_dir: Path | None = None,
) -> FactoryResetResult:
    """Reset known mutable paths without deleting the application or source tree.

    Known paths are renamed into a staging directory first. If staging fails,
    already moved paths are restored. This keeps the destructive boundary
    explicit and prevents a broad recursive delete of an unresolved directory.
    """

    support = _resolved_safe_target(
        support_dir or app_support_dir(),
        forbidden=(Path.home(), Path.cwd()),
    )
    requested_models = (models_dir or model_data_dir()).expanduser().resolve(strict=False)
    models = (
        support / "models"
        if requested_models == support
        else _resolved_safe_target(
            requested_models,
            forbidden=(Path.home(), Path.cwd(), support),
        )
    )

    support.mkdir(parents=True, exist_ok=True)
    staging = support / ".factory-reset-staging"
    if staging.exists() or staging.is_symlink():
        raise RuntimeError(
            "A previous Church Cap factory-reset staging folder still exists. "
            "Leave it in place and seek support before trying again."
        )
    staging.mkdir(mode=0o700)

    candidates = [support / name for name in FACTORY_RESET_DIRECTORIES]
    if support not in models.parents and models != support:
        candidates.append(models)

    moved: list[tuple[Path, Path]] = []
    try:
        for index, candidate in enumerate(candidates):
            if not candidate.exists() and not candidate.is_symlink():
                continue
            destination = staging / f"item-{index}"
            candidate.rename(destination)
            moved.append((candidate, destination))

        data_dir = support / "data"
        data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        marker = data_dir / FACTORY_RESET_MARKER_NAME
        marker.write_text("factory-reset\n", encoding="utf-8")
    except Exception:
        for original, staged in reversed(moved):
            if staged.exists() or staged.is_symlink():
                original.parent.mkdir(parents=True, exist_ok=True)
                staged.rename(original)
        _remove_staged(staging)
        raise

    # The reset is already active once the marker exists. Failure to remove the
    # private staging folder must not restore state that onboarding could use.
    try:
        _remove_staged(staging)
    except OSError:
        pass
    return FactoryResetResult(
        support_dir=support,
        removed=tuple(original for original, _ in moved),
        marker=marker,
    )
