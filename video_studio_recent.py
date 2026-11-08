# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Recent projects list (`video_studio_recent.py`)

Pure Python (no Qt) so it is fully unit-testable on any platform.
The list lives in `recent_projects.json` inside the user's app-data folder. Each entry keeps just enough
metadata to draw a card on the Home screen WITHOUT opening the project file again (fast startup):
name, aspect ratio, duration, clip count, last-opened time. Missing files are filtered out at read time.
"""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RECENT_FILE_NAME = "recent_projects.json"
MAX_RECENT_ITEMS = 24


def _norm_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def summarize_project(project: Any) -> Dict[str, Any]:
    """Cheap metadata of an in-memory VideoStudioProject (duck-typed: name, aspect_ratio, fps, tracks[].clips[])."""
    duration = 0.0
    clips = 0
    tracks = list(getattr(project, "tracks", []) or [])
    for trk in tracks:
        for clip in getattr(trk, "clips", []) or []:
            clips += 1
            try:
                duration = max(duration, float(clip.timeline_start) + float(clip.duration))
            except (TypeError, ValueError, AttributeError):
                continue
    return {
        "name": str(getattr(project, "name", "") or "Untitled"),
        "aspect": str(getattr(project, "aspect_ratio", "16:9") or "16:9"),
        "fps": int(getattr(project, "fps", 30) or 30),
        "duration": round(duration, 2),
        "clips": clips,
        "tracks": len(tracks),
    }


def format_duration(seconds: float) -> str:
    """`m:ss` or `h:mm:ss` (always LTR digits)."""
    total = max(0, int(round(float(seconds or 0))))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def age_parts(delta_seconds: float) -> Tuple[str, int]:
    """Coarse age of a timestamp as (unit, n): unit in now|min|hour|day|week|month|year."""
    d = max(0.0, float(delta_seconds))
    if d < 60:
        return "now", 0
    if d < 3600:
        return "min", int(d // 60)
    if d < 86400:
        return "hour", int(d // 3600)
    if d < 86400 * 7:
        return "day", int(d // 86400)
    if d < 86400 * 30:
        return "week", int(d // (86400 * 7))
    if d < 86400 * 365:
        return "month", int(d // (86400 * 30))
    return "year", int(d // (86400 * 365))


class RecentProjects:
    """Persistent most-recently-used project list (pinned items first, then newest)."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / RECENT_FILE_NAME
        self.items: List[Dict[str, Any]] = []
        self.load()

    # ---- persistence ----------------------------------------------------------------
    def load(self) -> None:
        self.items = []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except Exception:
            # Corrupt file: never crash the app because of a cosmetic list.
            try:
                os.replace(self.path, self.path.with_suffix(".corrupt"))
            except Exception:
                pass
            return
        entries = raw.get("items", []) if isinstance(raw, dict) else []
        for e in entries:
            if isinstance(e, dict) and isinstance(e.get("path"), str) and e["path"]:
                self.items.append(e)

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"items": self.items}, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)  # atomic
        except Exception:
            pass

    # ---- mutation -------------------------------------------------------------------
    def _find(self, path: str) -> Optional[Dict[str, Any]]:
        key = _norm_key(path)
        for e in self.items:
            if _norm_key(e["path"]) == key:
                return e
        return None

    def record(self, path: str, project: Any = None, now: Optional[float] = None) -> None:
        """Add/refresh an entry after a save or an open (moves it to the top, keeps its pin)."""
        if not path:
            return
        abs_path = os.path.abspath(str(path))
        existing = self._find(abs_path)
        entry: Dict[str, Any] = dict(existing) if existing else {"path": abs_path, "pinned": False}
        entry["path"] = abs_path
        if project is not None:
            entry.update(summarize_project(project))
        else:
            entry.setdefault("name", Path(abs_path).stem)
        entry["opened"] = float(time.time() if now is None else now)
        if existing is not None:
            self.items.remove(existing)
        self.items.insert(0, entry)
        # Trim: never drop pinned items, drop the oldest unpinned ones.
        while len(self.items) > MAX_RECENT_ITEMS:
            for i in range(len(self.items) - 1, -1, -1):
                if not self.items[i].get("pinned"):
                    del self.items[i]
                    break
            else:
                break
        self.save()

    def remove(self, path: str) -> bool:
        e = self._find(path)
        if e is None:
            return False
        self.items.remove(e)
        self.save()
        return True

    def toggle_pin(self, path: str) -> bool:
        e = self._find(path)
        if e is None:
            return False
        e["pinned"] = not bool(e.get("pinned"))
        self.save()
        return bool(e["pinned"])

    def clear(self, keep_pinned: bool = True) -> None:
        self.items = [e for e in self.items if keep_pinned and e.get("pinned")]
        self.save()

    # ---- query ----------------------------------------------------------------------
    def entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Existing projects only, pinned first then most recently opened. Adds `mtime` (file modified time)."""
        out: List[Dict[str, Any]] = []
        for e in self.items:
            try:
                st = os.stat(e["path"])
            except OSError:
                continue  # hidden, not deleted: a USB drive or network share may come back
            item = dict(e)
            item["mtime"] = st.st_mtime
            out.append(item)
        out.sort(key=lambda x: (not x.get("pinned", False), -float(x.get("opened", 0.0))))
        return out[:limit] if limit else out
