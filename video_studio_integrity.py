# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Release file integrity check (signed manifest).

`integrity.json` ships next to the EXE (release ZIP / installer) and contains
{"version", "files": {relative_path: {"sha256", "size"}}, "sig"}. The signature (Ed25519, domain MANIFEST1)
covers canonical JSON of {"version","files"}; the manifest never hashes itself. The check runs only in
compiled builds and never blocks the app: on mismatch the sensitive actions (export / activation) are
disabled and the user is told to reinstall from the official source.

Limit (stated honestly): code that runs inside the client can be patched by a determined attacker to skip
this check; it detects casual tampering and corrupted downloads.
"""

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from video_studio_license import _verify_sig, canonical_json

MANIFEST_PUBLIC_KEY_B64 = ""  # written by `tools/issue_serial.py keygen`
MANIFEST_NAME = "integrity.json"


def is_compiled() -> bool:
    return "__compiled__" in globals() or bool(getattr(sys, "frozen", False))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def launcher_path() -> Optional[Path]:
    """Path of the distributed EXE. In Nuitka onefile the running binary lives in a temp dir, so prefer the launcher."""
    try:
        parent_pid = os.environ.get("NUITKA_ONEFILE_PARENT")
        if parent_pid and sys.platform.startswith("win"):
            import ctypes

            k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            h = k32.OpenProcess(0x1000, False, int(parent_pid))  # PROCESS_QUERY_LIMITED_INFORMATION
            if h:
                buf = ctypes.create_unicode_buffer(2048)
                size = ctypes.c_ulong(2048)
                ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
                k32.CloseHandle(h)
                if ok and buf.value:
                    return Path(buf.value)
        compiled = globals().get("__compiled__")
        orig = getattr(compiled, "original_argv0", None)
        if orig:
            return Path(os.path.abspath(orig))
        return Path(os.path.abspath(sys.argv[0]))
    except Exception:
        return None


def verify_manifest_signature(manifest: Dict[str, Any], pub_b64: Optional[str] = None) -> bool:
    try:
        signed = {"version": manifest["version"], "files": manifest["files"]}
        return _verify_sig(pub_b64 if pub_b64 is not None else MANIFEST_PUBLIC_KEY_B64, "MANIFEST1", canonical_json(signed), manifest.get("sig", ""))
    except Exception:
        return False


def check_integrity(app_dir: Path, pub_b64: Optional[str] = None, manifest_path: Optional[Path] = None) -> Tuple[str, List[str]]:
    """Return (status, problems). status: ok | no_manifest | bad_signature | mismatch."""
    mpath = manifest_path or (Path(app_dir) / MANIFEST_NAME)
    if not mpath.exists():
        return "no_manifest", []
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
    except Exception:
        return "bad_signature", ["unreadable manifest"]
    if not isinstance(manifest, dict) or not verify_manifest_signature(manifest, pub_b64):
        return "bad_signature", ["signature"]
    problems: List[str] = []
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        return "bad_signature", ["files"]
    base = Path(app_dir).resolve()
    for rel, info in files.items():
        target = (base / rel).resolve()
        if base not in target.parents and target != base:  # path traversal guard
            problems.append(f"{rel}: bad path")
            continue
        if not target.exists():
            problems.append(f"{rel}: missing")
            continue
        try:
            if target.stat().st_size != int(info.get("size", -1)) or sha256_file(target) != str(info.get("sha256", "")).lower():
                problems.append(f"{rel}: modified")
        except Exception:
            problems.append(f"{rel}: unreadable")
    return ("mismatch", problems) if problems else ("ok", [])
