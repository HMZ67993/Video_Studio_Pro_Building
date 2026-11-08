# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Update checking (signed, cached, downgrade-safe).

update.json is public (GitHub raw). Release fields (version/url/sha256/notes) are trusted ONLY when
`update_sig` verifies; revocation list and payment info have their own signatures (see license module).
The app never downloads or runs an installer itself: it shows the version, notes and SHA-256 and opens
the signed https URL in the browser, so the user can verify the file hash before running it.
"""

import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MAX_UPDATE_BYTES = 256 * 1024
CACHE_NAME = "update_cache.json"
DEFAULT_CHECK_HOURS = 6


def parse_version(ver_str: str) -> Tuple[int, ...]:
    parts: List[int] = []
    for token in str(ver_str).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts or [0])


def is_newer_version(remote_ver: str, current_ver: str) -> bool:
    a, b = parse_version(remote_ver), parse_version(current_ver)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def fetch_update_json(url: str, timeout: float = 4.0, allow_http: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch and parse update.json. Returns None on any failure (the app must keep working offline)."""
    try:
        if not (url.lower().startswith("https://") or (allow_http and url.lower().startswith("http://"))):
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "HMZVideoStudioPro/1.0", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(MAX_UPDATE_BYTES + 1)
        if len(raw) > MAX_UPDATE_BYTES:
            return None
        data = json.loads(raw.decode("utf-8"), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def load_cached_update(cache_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads((Path(cache_dir) / CACHE_NAME).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_cached_update(cache_dir: Path, data: Dict[str, Any]) -> None:
    try:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        tmp = Path(cache_dir) / (CACHE_NAME + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, Path(cache_dir) / CACHE_NAME)
    except Exception:
        pass


def has_any_valid_signature(data: Dict[str, Any], license_mgr: Any) -> bool:
    """A document is cache-worthy only if at least one signed section verifies."""
    from video_studio_license import verify_signed_payment_info, verify_signed_release, verify_signed_revoked_list_or_none

    k = license_mgr.keys
    return (
        verify_signed_release(data, k["update"]) is not None
        or verify_signed_payment_info(data, k["payment"]) is not None
        or verify_signed_revoked_list_or_none(data, k["revoke"]) is not None
    )


def refresh_update_data(url: str, cache_dir: Path, license_mgr: Any, timeout: float = 4.0) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Return (data, is_fresh). Falls back to the last good cached document when offline; never caches unsigned data."""
    data = fetch_update_json(url, timeout=timeout)
    if data is not None and has_any_valid_signature(data, license_mgr):
        save_cached_update(cache_dir, data)
        return data, True
    cached = load_cached_update(cache_dir)
    if cached is not None and has_any_valid_signature(cached, license_mgr):
        return cached, False
    return None, False
