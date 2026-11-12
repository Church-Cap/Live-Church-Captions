"""Install the optional Windows CUDA runtime into per-user Church Cap data.

The desktop build cannot use the source checkout's ``.venv`` repair script.
Instead it downloads exact NVIDIA Windows wheels from PyPI, verifies their
published SHA-256 digests, and extracts only runtime DLLs into mutable user
data.  No system CUDA Toolkit or administrator access is required.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from app.install_progress import write_install_progress
from app.paths import app_support_dir


PYPI_HOST = "pypi.org"
PYPI_FILE_HOST = "files.pythonhosted.org"
USER_AGENT = "Church-Cap/0.9.0 CUDA-runtime-installer"
MINIMUM_FREE_OVERHEAD_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class WindowsCudaPackage:
    project: str
    version: str
    filename: str
    sha256: str
    component: str


# CUDA 12.4 plus cuDNN 9.1 is compatible with the CTranslate2 4.8.1 /
# faster-whisper 1.2.1 Windows runtime pinned by this release.  Exact wheel
# hashes are published by PyPI and checked again after every download.
WINDOWS_CUDA_PACKAGES = (
    WindowsCudaPackage(
        project="nvidia-cuda-runtime-cu12",
        version="12.4.127",
        filename="nvidia_cuda_runtime_cu12-12.4.127-py3-none-win_amd64.whl",
        sha256="09c2e35f48359752dfa822c09918211844a3d93c100a715d79b59591130c5e1e",
        component="cuda_runtime",
    ),
    WindowsCudaPackage(
        project="nvidia-cublas-cu12",
        version="12.4.5.8",
        filename="nvidia_cublas_cu12-12.4.5.8-py3-none-win_amd64.whl",
        sha256="5a796786da89203a0657eda402bcdcec6180254a8ac22d72213abc42069522dc",
        component="cublas",
    ),
    WindowsCudaPackage(
        project="nvidia-cudnn-cu12",
        version="9.1.0.70",
        filename="nvidia_cudnn_cu12-9.1.0.70-py3-none-win_amd64.whl",
        sha256="6278562929433d68365a07a4a1546c237ba2849852c0d4b2262a486e805b977a",
        component="cudnn",
    ),
)


def windows_cuda_runtime_dir() -> Path:
    return app_support_dir() / "cuda-runtime"


def windows_cuda_dll_dir() -> Path:
    return windows_cuda_runtime_dir() / "bin"


def _request_json(url: str) -> dict:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != PYPI_HOST:
        raise RuntimeError("CUDA package metadata URL is not an approved PyPI HTTPS source.")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:  # nosec B310 - host allow-listed above
        if urllib.parse.urlparse(response.geturl()).hostname != PYPI_HOST:
            raise RuntimeError("CUDA package metadata redirected away from PyPI.")
        payload = response.read(4 * 1024 * 1024 + 1)
    if len(payload) > 4 * 1024 * 1024:
        raise RuntimeError("CUDA package metadata exceeded the safety limit.")
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError("CUDA package metadata was invalid.")
    return decoded


def _package_download(package: WindowsCudaPackage) -> tuple[str, int]:
    metadata = _request_json(f"https://pypi.org/pypi/{package.project}/{package.version}/json")
    candidates = [item for item in metadata.get("urls", ()) if item.get("filename") == package.filename]
    if len(candidates) != 1:
        raise RuntimeError(f"Pinned CUDA package is unavailable: {package.filename}")
    item = candidates[0]
    published_hash = str((item.get("digests") or {}).get("sha256") or "").casefold()
    if published_hash != package.sha256:
        raise RuntimeError(f"PyPI hash changed for pinned CUDA package: {package.filename}")
    url = str(item.get("url") or "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != PYPI_FILE_HOST:
        raise RuntimeError("CUDA package download URL is not an approved PyPI file source.")
    return url, max(0, int(item.get("size") or 0))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(
    url: str,
    destination: Path,
    *,
    expected_size: int,
    on_progress,
) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:  # nosec B310
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != PYPI_FILE_HOST:
            raise RuntimeError("CUDA package download redirected away from the approved PyPI file host.")
        downloaded = 0
        while True:
            chunk = response.read(4 * 1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if expected_size and downloaded > expected_size + 1024:
                raise RuntimeError("CUDA package download exceeded its published size.")
            on_progress(downloaded)
    if expected_size and downloaded != expected_size:
        raise RuntimeError("CUDA package download size did not match PyPI metadata.")


def _safe_runtime_members(archive: zipfile.ZipFile, package: WindowsCudaPackage) -> list[zipfile.ZipInfo]:
    dll_prefix = PurePosixPath("nvidia") / package.component / "bin"
    members: list[zipfile.ZipInfo] = []
    for info in archive.infolist():
        name = PurePosixPath(info.filename)
        if name.is_absolute() or ".." in name.parts:
            raise RuntimeError(f"Unsafe path in CUDA wheel: {package.filename}")
        is_dll = len(name.parts) >= 4 and PurePosixPath(*name.parts[:3]) == dll_prefix and name.suffix.casefold() == ".dll"
        is_license = ".dist-info" in info.filename and name.name.casefold().startswith(("license", "notice"))
        if (is_dll or is_license) and not info.is_dir():
            members.append(info)
    if not any(PurePosixPath(item.filename).suffix.casefold() == ".dll" for item in members):
        raise RuntimeError(f"Pinned CUDA wheel contained no runtime DLLs: {package.filename}")
    return members


def _extract_runtime_wheel(wheel: Path, package: WindowsCudaPackage, staging: Path) -> None:
    bin_dir = staging / "bin"
    license_dir = staging / "licenses" / f"{package.project}-{package.version}"
    bin_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        for info in _safe_runtime_members(archive, package):
            name = PurePosixPath(info.filename)
            destination = bin_dir / name.name if name.suffix.casefold() == ".dll" else license_dir / name.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as output:
                shutil.copyfileobj(source, output, length=4 * 1024 * 1024)


def _verify_staging(staging: Path) -> None:
    bin_dir = staging / "bin"
    required = ("cudart64_12.dll", "cublas64_12.dll", "cublasLt64_12.dll", "cudnn64_9.dll")
    missing = [name for name in required if not (bin_dir / name).is_file()]
    if not any(bin_dir.glob("cudnn_*64_9.dll")):
        missing.append("cudnn_*64_9.dll")
    if missing:
        raise RuntimeError("Verified CUDA wheels were missing required runtime DLLs: " + ", ".join(missing))


def install_windows_cuda_runtime() -> Path:
    if platform.system() != "Windows":
        raise RuntimeError("The packaged CUDA runtime installer is only available on Windows.")

    support = app_support_dir()
    support.mkdir(parents=True, exist_ok=True)
    write_install_progress(2, "metadata", "Checking pinned NVIDIA CUDA package metadata.", indeterminate=True)
    resolved = [(package, *_package_download(package)) for package in WINDOWS_CUDA_PACKAGES]
    total_bytes = sum(size for _package, _url, size in resolved)
    # Downloads and extracted DLLs coexist during verification. Keep an extra
    # 512 MiB margin for wheel metadata, rollback, and filesystem overhead.
    minimum_free = (total_bytes * 2) + MINIMUM_FREE_OVERHEAD_BYTES
    free = shutil.disk_usage(support).free
    if free < minimum_free:
        raise RuntimeError(
            f"CUDA setup needs about {minimum_free / (1024 ** 3):.1f} GB free in the Church Cap data location; "
            f"only {free / (1024 ** 3):.1f} GB is available."
        )

    items = [
        {"id": package.component, "label": f"{package.project} {package.version}", "state": "pending", "percent": 0}
        for package, _url, _size in resolved
    ]
    with tempfile.TemporaryDirectory(prefix="church-cap-cuda-", dir=support) as temporary:
        temporary_path = Path(temporary)
        staging = temporary_path / "runtime"
        completed = 0
        for index, (package, url, package_size) in enumerate(resolved, start=1):
            wheel = temporary_path / package.filename
            last_percent = -1
            last_console_percent = -5

            def report(downloaded: int) -> None:
                nonlocal last_console_percent, last_percent
                item_percent = min(100, round(100 * downloaded / max(1, package_size)))
                if item_percent == last_percent:
                    return
                last_percent = item_percent
                if item_percent >= last_console_percent + 5 or item_percent == 100:
                    print(
                        f"CUDA package {index}/{len(resolved)} ({package.project}): {item_percent}% downloaded",
                        flush=True,
                    )
                    last_console_percent = item_percent
                items[index - 1].update(state="downloading", percent=item_percent)
                overall = 5 + round(73 * ((completed + downloaded) / max(1, total_bytes)))
                write_install_progress(
                    overall,
                    "downloading",
                    f"Downloading {package.project} {package.version} from PyPI.",
                    downloaded_bytes=completed + downloaded,
                    total_bytes=total_bytes,
                    item_index=index,
                    item_count=len(resolved),
                    items=items,
                )

            print(f"Downloading {package.filename} from PyPI...", flush=True)
            _download(url, wheel, expected_size=package_size, on_progress=report)
            items[index - 1].update(state="verifying", percent=100)
            write_install_progress(
                79,
                "verifying",
                f"Verifying {package.project} with its pinned SHA-256 hash.",
                downloaded_bytes=completed + package_size,
                total_bytes=total_bytes,
                item_index=index,
                item_count=len(resolved),
                items=items,
            )
            if _sha256(wheel).casefold() != package.sha256:
                raise RuntimeError(f"CUDA package failed SHA-256 verification: {package.filename}")
            write_install_progress(
                82,
                "extracting",
                f"Extracting verified {package.project} runtime DLLs.",
                downloaded_bytes=completed + package_size,
                total_bytes=total_bytes,
                item_index=index,
                item_count=len(resolved),
                items=items,
            )
            _extract_runtime_wheel(wheel, package, staging)
            items[index - 1].update(state="complete", percent=100)
            completed += package_size

        _verify_staging(staging)
        manifest = {
            "schema_version": 1,
            "installed_at": time.time(),
            "source": "PyPI verified NVIDIA Windows wheels",
            "packages": [asdict(package) for package, _url, _size in resolved],
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        destination = windows_cuda_runtime_dir()
        backup: Path | None = None
        if destination.exists():
            backup = support / f"cuda-runtime.previous-{time.strftime('%Y%m%d-%H%M%S')}"
            os.replace(destination, backup)
        try:
            os.replace(staging, destination)
        except Exception:
            if backup is not None and backup.exists() and not destination.exists():
                os.replace(backup, destination)
            raise

    write_install_progress(
        100,
        "complete",
        "NVIDIA CUDA 12.4 and cuDNN 9 runtime DLLs are installed for Church Cap.",
        downloaded_bytes=total_bytes,
        total_bytes=total_bytes,
        item_index=len(items),
        item_count=len(items),
        items=items,
    )
    print(f"Church Cap CUDA runtime is ready at {windows_cuda_runtime_dir()}", flush=True)
    return windows_cuda_runtime_dir()
