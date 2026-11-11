# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Update checking (signed, cached, downgrade-safe).

update.json is public (GitHub raw). Release fields (version/url/sha256/notes) are trusted ONLY when
`update_sig` verifies; revocation list and payment info have their own signatures (see license module).
The app never downloads or runs an installer itself: it shows the version, notes and SHA-256 and opens
the signed https URL in the browser, so the user can verify the file hash before running it.
"""

import base64
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


_HMZ_REPO_RAW_PREFIX = "https://raw.githubusercontent.com/HMZ67993/Video-Studio-Pro/"
_HMZ_GITHUB_API_URL = "https://api.github.com/repos/HMZ67993/Video-Studio-Pro/contents/Update.json?ref=main"


def _update_url_candidates(url: str) -> List[str]:
    """Return the configured endpoint plus trusted mirrors for this project's public Update.json."""
    candidates = [str(url or "").strip()]
    lowered = candidates[0].lower()
    if lowered.startswith(_HMZ_REPO_RAW_PREFIX.lower()):
        candidates.extend((
            "https://raw.githubusercontent.com/HMZ67993/Video-Studio-Pro/main/Update.json",
            "https://cdn.jsdelivr.net/gh/HMZ67993/Video-Studio-Pro@main/Update.json",
            _HMZ_GITHUB_API_URL,
        ))
    # Preserve order while removing empty and duplicate endpoints.
    return list(dict.fromkeys(item for item in candidates if item))


def _parse_update_response(raw: bytes, source_url: str) -> Optional[Dict[str, Any]]:
    """Parse either raw Update.json or GitHub's base64-encoded Contents API response."""
    if len(raw) > MAX_UPDATE_BYTES * 2:
        return None
    try:
        payload = json.loads(raw.decode("utf-8-sig"), parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)))
        if "api.github.com/repos/" in source_url.lower():
            if not isinstance(payload, dict) or payload.get("encoding") != "base64":
                return None
            encoded = payload.get("content")
            if not isinstance(encoded, str):
                return None
            document_bytes = base64.b64decode(encoded, validate=False)
            if len(document_bytes) > MAX_UPDATE_BYTES:
                return None
            payload = json.loads(
                document_bytes.decode("utf-8-sig"),
                parse_constant=lambda c: (_ for _ in ()).throw(ValueError(c)),
            )
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def fetch_update_json(url: str, timeout: float = 8.0, allow_http: bool = False) -> Optional[Dict[str, Any]]:
    """Fetch Update.json with GitHub/CDN fallbacks; unsigned content is still rejected downstream."""
    for candidate in _update_url_candidates(url):
        if not (candidate.lower().startswith("https://") or (allow_http and candidate.lower().startswith("http://"))):
            continue
        headers = {
            "User-Agent": "HMZVideoStudioPro/1.1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        if "api.github.com/repos/" in candidate.lower():
            headers["Accept"] = "application/vnd.github+json"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        try:
            req = urllib.request.Request(candidate, headers=headers)
            with urllib.request.urlopen(req, timeout=max(1.0, float(timeout))) as resp:
                raw = resp.read(MAX_UPDATE_BYTES * 2 + 1)
            data = _parse_update_response(raw, candidate)
            if data is not None:
                return data
        except Exception:
            # Keep trying the known mirrors. The caller will use a previously
            # verified cache (if present) and never trust unsigned data.
            continue
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
