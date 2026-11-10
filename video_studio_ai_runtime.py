# -*- coding: utf-8 -*-
"""On-demand, per-user AI runtime installer for HMZ Video Studio Pro.

The main EXE stays small. Optional native Python wheels are downloaded as a
separate ZIP from the latest GitHub Release and activated from the user data
folder; no system Python or pip installation is required on customer PCs.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Optional

APP_NAME = "HMZVideoStudioPro"
ASSET_NAME = "HMZ_AI_Runtime_Windows_Py312.zip"
USER_AGENT = "HMZ-VideoStudio-Pro-AI-Runtime"
_DLL_HANDLES = []


def _repository() -> str:
    repo = os.environ.get("HMZ_AI_REPOSITORY", "").strip()
    cfg = Path(__file__).with_name("hmz_ai_config.json")
    try:
        if cfg.is_file():
            repo = str(json.loads(cfg.read_text(encoding="utf-8")).get("repository") or repo).strip()
    except Exception:
        pass
    return repo


def runtime_dir() -> Path:
    root = Path(os.environ.get("APPDATA") or (Path.home() / ".config"))
    return root / APP_NAME / "ai_runtime"


def activate_runtime() -> bool:
    """Add an already downloaded runtime to sys.path and register native DLL dirs."""
    root = runtime_dir()
    marker = root / ".hmz_ai_runtime_ready"
    if not marker.is_file():
        return False
    # A marker alone is not proof of a usable runtime (old/incomplete ZIPs
    # could leave the marker behind). Validate the mandatory Whisper stack.
    required_packages = ("faster_whisper", "ctranslate2")
    if any(not (root / package / "__init__.py").is_file() for package in required_packages):
        return False
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if os.name == "nt" and hasattr(os, "add_dll_directory"):
        for dll in root.rglob("*.dll"):
            folder = str(dll.parent)
            try:
                _DLL_HANDLES.append(os.add_dll_directory(folder))
            except OSError:
                continue
    return True


def install_runtime(progress: Optional[Callable[[int], None]] = None,
                    cancel: Optional[Callable[[], bool]] = None) -> Path:
    """Download/extract the optional runtime atomically into the current user's profile."""
    if activate_runtime():
        return runtime_dir()
    repo = _repository()
    if not repo or "/" not in repo or repo.startswith("http"):
        raise RuntimeError("AI runtime release is not configured for this build")
    api = f"https://api.github.com/repos/{repo}/releases/tags/ai-runtime"
    req = urllib.request.Request(api, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        release = json.loads(response.read().decode("utf-8"))
    asset = next((a for a in release.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if not asset:
        raise RuntimeError("AI runtime package was not found in the latest release")
    url = str(asset.get("browser_download_url") or "")
    if not url.startswith("https://"):
        raise RuntimeError("Invalid AI runtime download URL")

    target = runtime_dir()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="hmz_ai_", dir=str(target.parent)))
    archive = temp_root / "runtime.zip"
    staging = temp_root / "runtime"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        total = int(asset.get("size") or 0)
        done = 0
        with urllib.request.urlopen(request, timeout=60) as response, archive.open("wb") as out:
            while True:
                if cancel and cancel():
                    raise RuntimeError("cancelled")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(85, int(done * 85 / total)))
        expected_hash = ""
        sidecar = next((a for a in release.get("assets", [])
                        if a.get("name") == ASSET_NAME + ".sha256"), None)
        if sidecar and str(sidecar.get("browser_download_url", "")).startswith("https://"):
            side_req = urllib.request.Request(sidecar["browser_download_url"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(side_req, timeout=30) as response:
                import re
                match = re.search(r"\b([0-9a-fA-F]{64})\b", response.read(4096).decode("ascii", errors="ignore"))
                expected_hash = match.group(1).lower() if match else ""
        digest = str(asset.get("digest") or "")
        if digest.startswith("sha256:"):
            expected_hash = digest.split(":", 1)[1].lower()
        if not expected_hash:
            raise RuntimeError("AI runtime checksum is missing; refusing an unverified package")
        hasher = hashlib.sha256()
        with archive.open("rb") as downloaded:
            for block in iter(lambda: downloaded.read(1024 * 1024), b""):
                hasher.update(block)
        if hasher.hexdigest().lower() != expected_hash:
            raise RuntimeError("AI runtime package checksum mismatch")
        staging.mkdir()
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                name = info.filename.replace("\\", "/")
                member = PurePosixPath(name)
                if member.is_absolute() or ".." in member.parts:
                    raise RuntimeError("Unsafe path in AI runtime package")
            zf.extractall(staging)
        # Support either a flat pip --target archive or one enclosing folder.
        entries = list(staging.iterdir())
        source = entries[0] if len(entries) == 1 and entries[0].is_dir() else staging
        marker = source / ".hmz_ai_runtime_ready"
        marker.write_text(str(release.get("tag_name") or "latest"), encoding="utf-8")
        backup = target.with_name(target.name + ".old")
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if target.exists():
            target.rename(backup)
        try:
            shutil.copytree(source, target)
        except Exception:
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise
        shutil.rmtree(backup, ignore_errors=True)
        if progress:
            progress(100)
        activate_runtime()
        return target
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
