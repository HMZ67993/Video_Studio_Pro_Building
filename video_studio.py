#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Main Desktop Application Entry Point (`video_studio.py`)
Implements the 5-Zone CapCut Pro Desktop Interface + Full HMZ-Bytes-App Standard:
  - Immediate Arabic (RTL) / English (LTR) switching while keeping timecodes, paths, numbers, and timeline LTR
  - Dark (Cinema Default) / Light / System themes + 5 Accent Colors
  - Multi-track interactive timeline (QPainter) with waveforms, keyframes, transitions, and magnetic snapping
  - Live interactive preview canvas with mouse transform gizmos
  - 5-tab Inspector (Video/Blend/Masks/Chroma, Color Grading/LUT, Speed Ramping, Audio/EQ, Keyframes/Text)
  - 7-section Browser (Media Bin, Audio, Text/SRT, Effects, Transitions, Local AI Hub, Stickers)
  - Dual Licensing Dialogs (Gumroad + Ed25519 Manual Serial + Signed Manual Payment with WhatsApp)
  - Built-in F1 Interactive Guide, "More of Our Apps" Store, About Dialog, Background Update Check
  - Rotating crash.log (~200KB max) via sys.excepthook & threading.excepthook + settings.json in %APPDATA%
"""

import datetime
import hashlib
import json
import platform
import re
import uuid
import os
import sys
import threading
import time
import traceback
import weakref
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from video_studio_core import (
    probe_media_duration,
    ASPECT_RATIOS,
    EQUALIZER_PRESETS,
    RESOLUTION_PRESETS,
    SPEED_CURVE_PRESETS,
    TextStyleSettings,
    TimelineClip,
    TimelineMarker,
    VideoStudioProject,
    track_accepts,
    export_clips_to_srt,
    parse_srt_content,
)
from video_studio_guide import get_guide_sections
from video_studio_i18n import APP_VERSION, tr
from video_studio_license import (
    DEFAULT_UPDATE_URL,
    FREE_OPERATIONS,
    GUMROAD_BUY_URL,
    LicenseManager,
    REVERIFY_DAYS,
)
from video_studio_ffmpeg import FFMPEG_DOWNLOAD_PAGE, detect_nvenc, download_ffmpeg, find_ffmpeg, project_has_audio, validate_ffmpeg
from video_studio_integrity import check_integrity, is_compiled, launcher_path
from video_studio_update import is_newer_version, refresh_update_data
from video_studio_plugins import AIPluginRegistry
from video_studio_recent import RecentProjects
from video_studio_store import (
    DEFAULT_PRODUCTS_JSON_URL, load_cached_products_catalog, load_products_catalog,
)
from video_studio_theme import ACCENT_COLORS, apply_theme_to_app, get_effective_palette

MAX_CRASH_LOG_BYTES = 200 * 1024  # ~200 KB

try:
    from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
    from PyQt6.QtGui import (
        QColor,
        QGuiApplication,
        QIcon,
        QAction,
        QActionGroup,
        QImage,
        QKeySequence,
        QPainter,
        QPainterPath,
        QPen,
        QPixmap,
        QShortcut,
    )
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
    from PyQt6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMenu,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QSlider,
        QSplashScreen,
        QSplitter,
        QStackedWidget,
        QTabWidget,
        QTextBrowser,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )

    from video_studio_home import HomeScreen

    HAS_PYQT6 = True
except ImportError:
    HAS_PYQT6 = False

# Kept here as lightweight constants so Home-screen drag/drop validation does not
# need to import the entire editor panels/timeline stack during startup.
MEDIA_EXTS = (
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a",
    ".aac", ".ogg", ".flac", ".png", ".jpg", ".jpeg", ".webp", ".bmp",
    ".gif", ".srt", ".hvsp",
)
STICKER_MIME = "application/x-hmz-sticker"


def get_app_data_dir(custom_dir: Optional[Path] = None) -> Path:
    if custom_dir is not None:
        base = Path(custom_dir)
    else:
        appdata = os.environ.get("APPDATA") or str(Path.home() / ".config")
        base = Path(appdata) / "HMZVideoStudioPro"
    base.mkdir(parents=True, exist_ok=True)
    return base


_REDACT_PATTERNS = [
    re.compile(r"VSP\d+-[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),                 # manual serials
    re.compile(r"(?i)(license[_ ]?key|access[_ ]?token|token|secret|password|api[_-]?key)\s*[=:]\s*\S+"),
    re.compile(r"[A-Fa-f0-9]{8}-[A-Fa-f0-9]{8}-[A-Fa-f0-9]{8}-[A-Fa-f0-9]{8}"),  # Gumroad-style keys
    re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/])"),  # long base64 blobs (keys)
]


def redact_sensitive(text: str) -> str:
    """Remove serials, license keys, tokens and key-like blobs before anything is written to crash.log."""
    for pat in _REDACT_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def write_crash_log(exc_type: Any, exc_value: Any, exc_tb: Any, custom_dir: Optional[Path] = None) -> Path:
    """Append formatted traceback to crash.log and trim file to the last ~200KB."""
    log_path = get_app_data_dir(custom_dir) / "crash.log"
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    tb_text = redact_sensitive("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    ref_id = uuid.uuid4().hex[:8].upper()
    env = f"OS: {platform.platform()} | Python: {platform.python_version()} | compiled: {is_compiled()}"
    entry = f"\n=== [{ts}] HMZ Video Studio Pro v{APP_VERSION} Crash Report | ref {ref_id} ===\n{env}\n{tb_text}\n"
    write_crash_log.last_ref = ref_id  # type: ignore[attr-defined]
    existing = b""
    if log_path.exists():
        try:
            existing = log_path.read_bytes()
        except Exception:
            existing = b""
    combined = existing + entry.encode("utf-8", errors="replace")
    if len(combined) > MAX_CRASH_LOG_BYTES:
        combined = combined[-MAX_CRASH_LOG_BYTES:]
    try:
        log_path.write_bytes(combined)
    except Exception:
        pass
    return log_path


def install_exception_hooks(custom_dir: Optional[Path] = None) -> None:
    """Install sys.excepthook and threading.excepthook with friendly message instead of silent crash."""

    def _sys_hook(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        log_file = write_crash_log(exc_type, exc_value, exc_tb, custom_dir)
        if HAS_PYQT6 and QApplication.instance() is not None:
            try:
                QMessageBox.critical(
                    None,
                    "HMZ Video Studio Pro — خطأ غير متوقع / Unexpected Error",
                    f"حدث خطأ غير متوقع وتم حفظ التفاصيل في سجل الأعطال:\n{log_file}\n"
                    f"رقم المرجع: {getattr(write_crash_log, 'last_ref', '-')}\n\n"
                    f"An unexpected error occurred and was logged to:\n{log_file}\n"
                    f"Reference ID: {getattr(write_crash_log, 'last_ref', '-')}",
                )
            except Exception:
                pass

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        write_crash_log(args.exc_type, args.exc_value, args.exc_traceback, custom_dir)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook


_LICENSE_MSG_KEYS = {
    "ok": "lic_msg_ok", "invalid": "lic_msg_invalid", "product": "lic_msg_product", "device": "lic_msg_device",
    "expired": "lic_msg_expired", "disabled": "lic_msg_disabled", "network_error": "lic_msg_network",
    "network": "lic_msg_network", "not_yet_valid": "lic_msg_not_yet_valid", "not_configured": "lic_msg_not_configured",
    "integrity": "lic_msg_integrity",
}


def license_message_key(status: str) -> str:
    return _LICENSE_MSG_KEYS.get(status, "lic_msg_invalid")


def _resource_path(name: str) -> Path:
    """Locate a bundled resource (PyInstaller `_MEIPASS` or next to the script)."""
    base = Path(getattr(sys, "_MEIPASS", Path(os.path.abspath(__file__)).parent))
    return base / name


SINGLE_INSTANCE_KEY = "HMZVideoStudioPro_single_instance"


class SettingsManager:
    """Manage user settings in `%APPDATA%/HMZVideoStudioPro/settings.json`."""

    def __init__(self, custom_dir: Optional[Path] = None):
        self.path = get_app_data_dir(custom_dir) / "settings.json"
        self.data: Dict[str, Any] = {
            "lang": "ar",
            "theme": "dark",
            "accent": "cyan",
            "window_width": 1440,
            "window_height": 880,
            "update_url": DEFAULT_UPDATE_URL,
            "products_url": DEFAULT_PRODUCTS_JSON_URL,
            "last_project_path": "",
            "update_check_hours": 6,
        }
        self.load()

    def load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
                else:
                    raise ValueError("settings root is not an object")
            except Exception:
                # Corrupt file: keep a copy for diagnosis and continue with defaults.
                try:
                    os.replace(self.path, self.path.with_name(f"settings.corrupt-{int(datetime.datetime.now().timestamp())}.json"))
                except Exception:
                    pass
        return self.data

    def save(self) -> None:
        try:
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)  # atomic: never leaves a half-written settings.json
        except Exception:
            pass


def format_timecode_ltr(seconds: float, fps: int = 30) -> str:
    """Format seconds into SMPTE timecode `HH:MM:SS:FF` (always LTR)."""
    sec = max(0.0, float(seconds))
    total_int = int(sec)
    hrs = total_int // 3600
    mins = (total_int % 3600) // 60
    secs = total_int % 60
    frames = int(round((sec - total_int) * fps)) % max(1, fps)
    return f"{hrs:02d}:{mins:02d}:{secs:02d}:{frames:02d}"


def handle_remove_integrations(custom_dir: Optional[Path] = None) -> int:
    """Called by Inno Setup uninstaller (`--remove-integrations`) to clean temporary cache files."""
    app_dir = get_app_data_dir(custom_dir)
    for temp_name in ("products_cache.json", "single_instance.lock"):
        try:
            (app_dir / temp_name).unlink(missing_ok=True)
        except Exception:
            pass
    return 0


class StudioAppController:
    """Core UI state controller binding Project, Licensing, AI Plugins, Settings, Theme, and Localization."""

    def __init__(self, custom_data_dir: Optional[Path] = None):
        self.custom_data_dir = custom_data_dir
        self.settings = SettingsManager(custom_data_dir)
        self.recents = RecentProjects(get_app_data_dir(custom_data_dir))
        self.current_project_path = ""  # file the open project was loaded from / last saved to ("" = never saved)
        self.license_mgr = LicenseManager(custom_storage_dir=custom_data_dir)
        self.integrity_status = "skipped"  # set by the startup integrity worker (compiled builds only)
        self.ai_registry = AIPluginRegistry(models_dir=custom_data_dir)  # ffmpeg path is passed per run
        self.project = VideoStudioProject(name="HMZ Project 1", aspect_ratio="16:9", fps=30)
        self.project.stabilization_cache_dir = get_app_data_dir(custom_data_dir) / "stabilization"
        self.selected_clip_id: Optional[str] = None
        self.selected_ids: List[str] = []
        self.clipboard: List[TimelineClip] = []
        self.preview_quality_scale: float = 0.5
        self.media_bin: List[str] = []
        self._seed_demo_timeline()
        self._saved_digest = self.project_digest()

    def _seed_demo_timeline(self) -> None:
        v_track = next(t for t in self.project.tracks if t.track_type == "video")
        t_track = next(t for t in self.project.tracks if t.track_type == "text")
        intro_clip = TimelineClip(
            name="Intro Scene",
            clip_type="video",
            timeline_start=0.0,
            duration=5.0,
            transition_in="crossfade",
            transition_duration=0.6,
        )
        title_clip = TimelineClip(
            name="Welcome Title",
            clip_type="text",
            timeline_start=0.5,
            duration=4.0,
            text_style=TextStyleSettings(
                text="HMZ Video Studio Pro — استوديو المونتاج الاحترافي",
                font_size=46,
                text_color_hex="#FFFFFF",
                stroke_color_hex="#000000",
                stroke_width=3,
                bg_enabled=True,
                bg_color_hex="#0D3B42",
            ),
        )
        v_track.clips.append(intro_clip)
        t_track.clips.append(title_clip)
        self.select_clip(intro_clip.id)
        self.project._undo_stack.clear()

    @property
    def lang(self) -> str:
        return self.settings.data.get("lang", "ar")

    # ---- autosave / recovery ------------------------------------------------------
    def project_digest(self) -> str:
        d = self.project.to_dict()
        d.pop("playhead_sec", None)  # moving the playhead is not an edit
        return hashlib.sha1(json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def is_dirty(self) -> bool:
        return self.project_digest() != self._saved_digest

    def autosave_path(self) -> Path:
        return get_app_data_dir(self.custom_data_dir) / "autosave.hvsp"

    def autosave_if_dirty(self) -> bool:
        """Write the recovery copy atomically when there are unsaved edits. Never raises."""
        try:
            if not self.is_dirty():
                return False
            target = self.autosave_path()
            tmp = target.with_suffix(".hvsp.tmp")
            tmp.write_text(self.project.to_json_string(), encoding="utf-8")
            os.replace(tmp, target)
            return True
        except Exception:
            return False

    def mark_saved(self) -> None:
        """Call after an explicit save/open/new: the project now matches disk, so the recovery copy is obsolete."""
        self._saved_digest = self.project_digest()
        try:
            self.autosave_path().unlink(missing_ok=True)
        except Exception:
            pass

    def has_recovery(self) -> bool:
        p = self.autosave_path()
        try:
            if not p.exists():
                return False
            json.loads(p.read_text(encoding="utf-8"))
            return True
        except Exception:
            try:
                p.rename(p.with_suffix(".corrupt"))  # keep it for diagnosis, don't offer a broken file again
            except Exception:
                pass
            return False

    def recover_project(self) -> bool:
        try:
            self.project.load_project_file(str(self.autosave_path()))
            self.project.stabilization_cache_dir = get_app_data_dir(self.custom_data_dir) / "stabilization"
            self._saved_digest = ""  # recovered work is unsaved by definition
            return True
        except Exception:
            return False

    def ffmpeg_path(self) -> Optional[str]:
        """Usable ffmpeg executable (user-chosen, downloaded into app data, next to the EXE, or on PATH) or None."""
        return find_ffmpeg(get_app_data_dir(self.custom_data_dir), str(self.settings.data.get("ffmpeg_path", "")))

    def toggle_language(self) -> str:
        new_lang = "en" if self.lang == "ar" else "ar"
        self.settings.data["lang"] = new_lang
        self.settings.save()
        return new_lang

    def set_theme_and_accent(self, theme_mode: str, accent_key: str) -> Dict[str, str]:
        self.settings.data["theme"] = theme_mode
        self.settings.data["accent"] = accent_key
        self.settings.save()
        return get_effective_palette(theme_mode, accent_key)

    def select_clip(self, clip_id: Optional[str], additive: bool = False, toggle: bool = False) -> None:
        """Single / additive (Shift) / toggle (Ctrl) selection; `selected_clip_id` is the primary clip."""
        if clip_id is None:
            self.selected_ids, self.selected_clip_id = [], None
            return
        if toggle and clip_id in self.selected_ids:
            self.selected_ids.remove(clip_id)
            self.selected_clip_id = self.selected_ids[-1] if self.selected_ids else None
            return
        if additive or toggle:
            if clip_id not in self.selected_ids:
                self.selected_ids.append(clip_id)
        else:
            self.selected_ids = [clip_id]
        self.selected_clip_id = clip_id

    def selected_clips(self) -> List[TimelineClip]:
        out: List[TimelineClip] = []
        for cid in list(self.selected_ids):
            f = self.project.find_clip(cid)
            if f:
                out.append(f[1])
            else:
                self.selected_ids.remove(cid)
        return out

    def get_selected_clip(self) -> Optional[TimelineClip]:
        if not self.selected_clip_id:
            return None
        found = self.project.find_clip(self.selected_clip_id)
        return found[1] if found else None

    def open_cli_file(self, path_str: str) -> bool:
        path = Path(path_str)
        if not path.exists():
            return False
        if path.suffix.lower() == ".hvsp":
            self.open_project_file(str(path))
            return True
        if path.suffix.lower() == ".srt":
            clips = parse_srt_content(path.read_text(encoding="utf-8", errors="ignore"))
            t_track = next((t for t in self.project.tracks if t.track_type == "text"), self.project.tracks[0])
            for c in clips:
                self.project.add_clip_to_track(t_track.id, c)
            return True
        return self.add_media_to_timeline(str(path), at=None)

    def open_project_file(self, path_str: str) -> None:
        """Load a .hvsp into a fresh project object; the current project is replaced only if loading succeeds.
        Raises on a corrupt/unreadable file (callers show the message). Records it in the recent list."""
        fresh = VideoStudioProject(name="tmp")
        fresh.load_project_file(path_str)
        fresh.stabilization_cache_dir = get_app_data_dir(self.custom_data_dir) / "stabilization"
        self.project = fresh
        self.select_clip(None)
        self.current_project_path = str(Path(path_str).resolve())
        self.settings.data["last_project_path"] = self.current_project_path
        self.settings.save()
        self.recents.record(self.current_project_path, self.project)

    def add_media_to_timeline(self, path_str: str, at: Optional[float] = None) -> bool:
        """Register media in the bin and place it on the matching track (at playhead, or after the last clip)."""
        path = Path(path_str)
        ext = path.suffix.lower()
        if ext == ".gif":
            return self.add_sticker_to_timeline(str(path), at)
        ctype = "audio" if ext in (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac") else ("image" if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp") else "video")
        if str(path) not in self.media_bin:
            self.media_bin.append(str(path))
        target_track = next((t for t in self.project.tracks if t.track_type == ("audio" if ctype == "audio" else "video") and not t.locked), self.project.tracks[0])
        start = at if at is not None else max((c.timeline_end for c in target_track.clips), default=0.0)
        dur = round(probe_media_duration(str(path), self.ffmpeg_path()), 3) if ctype != "image" else 5.0
        new_clip = TimelineClip(name=path.stem, clip_type=ctype, source_path=str(path), timeline_start=round(start, 3), duration=dur, source_in=0.0, source_out=dur)
        ok = self.project.add_clip_to_track(target_track.id, new_clip)
        if ok:
            self.select_clip(new_clip.id)
        return ok

    def stickers_dir(self) -> Path:
        d = get_app_data_dir(self.custom_data_dir) / "stickers"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def my_stickers_dir(self) -> Path:
        d = get_app_data_dir(self.custom_data_dir) / "my_stickers"
        d.mkdir(parents=True, exist_ok=True)
        return d

    STICKER_EXTS = (".png", ".gif", ".webp")

    def add_sticker_to_timeline(self, path_str: str, at: Optional[float] = None, duration: Optional[float] = None,
                                track_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> bool:
        """Place a PNG/WebP/GIF sticker on a sticker track that is free at that time (or a new sticker track).
        `meta` ({"sticker_id", "sticker_color"}) lets the timeline show the built-in sticker's name in the UI language."""
        path = Path(path_str)
        if not path.exists():
            return False
        if str(path) not in self.media_bin:
            self.media_bin.append(str(path))
        start = round(max(0.0, self.project.playhead_sec if at is None else at), 3)
        if duration is None:
            duration = 3.0
            if (meta or {}).get("sticker_id") is None and path.suffix.lower() in (".gif", ".webp"):
                real = probe_media_duration(str(path), None, default=3.0)
                if real >= 2.0:  # a user GIF keeps its own length; short loops play for 3 s
                    duration = round(min(30.0, real), 3)
        end = start + duration
        if (meta or {}).get("sticker_id"):
            name = path.stem.replace("_", " ").strip() or path.stem
        else:
            name = self.sticker_label(path.name, self.lang)
        clip = TimelineClip(name=name, clip_type="sticker", source_path=str(path), timeline_start=start, duration=duration, source_in=0.0, source_out=duration)
        if meta:
            clip.ai_metadata = dict(meta)
        with self.project.undo_group():  # one undo step even if a new sticker track has to be created
            track = self.project.find_track(track_id) if track_id else None
            if track is None or track.locked or not track_accepts(track.track_type, "sticker") or any(c.timeline_start < end and c.timeline_end > start for c in track.clips):
                track = self.project.find_sticker_track(start, end)
            ok = self.project.add_clip_to_track(track.id, clip)
        if ok:
            self.select_clip(clip.id)
        return ok

    def _sticker_names_path(self) -> Path:
        return self.my_stickers_dir() / "names.json"

    def sticker_names(self) -> Dict[str, Dict[str, str]]:
        try:
            data = json.loads(self._sticker_names_path().read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def set_sticker_name(self, file_name: str, ar: str, en: str) -> None:
        """Persist separate Arabic and English names for a user-imported sticker."""
        data = self.sticker_names()
        ar, en = ar.strip(), en.strip()
        data[Path(file_name).name] = {"ar": ar or en or Path(file_name).stem,
                                      "en": en or ar or Path(file_name).stem}
        target = self._sticker_names_path()
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)

    def sticker_label(self, file_name: str, lang: str = "ar") -> str:
        names = self.sticker_names().get(Path(file_name).name, {})
        return (names.get(lang) or names.get("en" if lang == "ar" else "ar")
                or Path(file_name).stem.replace("_", " "))

    def import_stickers(self, paths: List[str]) -> List[str]:
        """Import PNG/GIF/WebP files and folders recursively; validates images and never overwrites different files.
        Returns absolute paths of the imported or already-existing identical files.
        """
        import shutil
        from PIL import Image

        sources: List[Path] = []
        for raw in paths:
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                try:
                    sources.extend(x for x in sorted(candidate.rglob("*"))
                                   if x.is_file() and x.suffix.lower() in self.STICKER_EXTS)
                except OSError:
                    continue
            elif candidate.is_file() and candidate.suffix.lower() in self.STICKER_EXTS:
                sources.append(candidate)

        out: List[str] = []
        folder = self.my_stickers_dir()
        seen = set()
        for src in sources:
            try:
                src = src.resolve()
                if src in seen:
                    continue
                seen.add(src)
                with Image.open(src) as image:
                    image.verify()
                # A file already in the destination folder is already imported.
                if src.parent == folder.resolve():
                    out.append(str(src))
                    continue
                dest = folder / src.name
                n = 1
                while dest.exists():
                    try:
                        same = dest.stat().st_size == src.stat().st_size and hashlib.sha256(dest.read_bytes()).digest() == hashlib.sha256(src.read_bytes()).digest()
                    except OSError:
                        same = False
                    if same:
                        break
                    dest = folder / f"{src.stem}_{n}{src.suffix.lower()}"
                    n += 1
                if not dest.exists():
                    shutil.copy2(src, dest)
                out.append(str(dest))
            except Exception:
                continue
        return out

    # Backward-compatible alias for projects/scripts built against the first implementation.
    def import_sticker_files(self, paths: List[str]) -> List[str]:
        return [Path(p).name for p in self.import_stickers(paths)]

if HAS_PYQT6:
    _LIVE_QT_WORKERS: set[Any] = set()

    def _track_qt_worker(worker: Any) -> Any:
        """Keep a QThread wrapper alive until Qt confirms that its native thread stopped."""
        _LIVE_QT_WORKERS.add(worker)
        worker_ref = weakref.ref(worker)
        worker.finished.connect(
            lambda ref=worker_ref: _LIVE_QT_WORKERS.discard(ref()) if ref() is not None else None
        )
        return worker

    class ExportWorkerThread(QThread):
        progress_changed = pyqtSignal(int)
        export_finished = pyqtSignal(bool, str)

        def __init__(self, project: VideoStudioProject, output_path: str, resolution_label: str, fps: int,
                     quality: str = "balanced", use_gpu: bool = False, ffmpeg: Optional[str] = None):
            super().__init__()
            self.project = project.clone_for_export()  # the UI may keep editing while we render
            self.output_path = output_path
            self.resolution_label = resolution_label
            self.fps = fps
            self.quality = quality
            self.use_gpu = use_gpu
            self.ffmpeg = ffmpeg
            self._cancelled = False
            self.info: Dict[str, Any] = {}

        def request_cancel(self) -> None:
            self._cancelled = True

        def run(self) -> None:
            try:
                ok = self.project.export_project(
                    output_path=self.output_path,
                    resolution_label=self.resolution_label,
                    fps=self.fps,
                    progress_callback=lambda p: self.progress_changed.emit(p),
                    cancel_check=lambda: self._cancelled,
                    quality=self.quality,
                    use_gpu=self.use_gpu,
                    ffmpeg_path=self.ffmpeg,
                )
            except Exception as exc:  # report instead of dying silently inside the thread
                ok = False
                self.project.last_export_info = {"audio": "none", "encoder": "", "error": f"{type(exc).__name__}: {exc}"}
                write_crash_log(type(exc), exc, exc.__traceback__)
            self.info = dict(self.project.last_export_info)
            self.export_finished.emit(ok and not self._cancelled, self.output_path)

    class ProxyWorkerThread(QThread):
        finished_result = pyqtSignal(str, str, str)  # clip id, proxy path, error

        def __init__(self, project: VideoStudioProject, clip_id: str, output_dir: Path, ffmpeg: Optional[str]):
            super().__init__()
            self.project = project.clone_for_export()
            self.clip_id = clip_id
            self.output_dir = output_dir
            self.ffmpeg = ffmpeg

        def run(self) -> None:
            try:
                result = self.project.generate_proxy_for_clip(
                    self.clip_id, self.output_dir, ffmpeg_path=self.ffmpeg,
                    cancel_check=self.isInterruptionRequested,
                )
                found = self.project.find_clip(self.clip_id)
                error = str(getattr(self.project, "last_proxy_error", "") or "")
                self.finished_result.emit(self.clip_id, str(result or ""), error)
            except Exception as exc:
                self.finished_result.emit(self.clip_id, "", f"{type(exc).__name__}: {exc}")


    class StabilizationWorkerThread(QThread):
        progress_changed = pyqtSignal(str, int)
        finished_result = pyqtSignal(str, bool, str)

        def __init__(self, clip_id: str, source_path: str, cache_path: Path):
            super().__init__()
            self.clip_id = clip_id
            self.source_path = source_path
            self.cache_path = cache_path

        def run(self) -> None:
            try:
                from video_studio_stabilization import analyze_video_stabilization

                result = analyze_video_stabilization(
                    self.source_path, self.cache_path,
                    progress_callback=lambda value: self.progress_changed.emit(self.clip_id, int(value)),
                    cancel_check=self.isInterruptionRequested,
                )
                self.finished_result.emit(self.clip_id, bool(result), str(result or ""))
            except Exception as exc:
                self.finished_result.emit(self.clip_id, False, f"{type(exc).__name__}: {exc}")


    class ProductCatalogWorkerThread(QThread):
        finished_catalog = pyqtSignal(object, bool, str)

        def __init__(self, products_url: str, cache_dir: Optional[Path], force: bool):
            super().__init__()
            self.products_url = products_url
            self.cache_dir = cache_dir
            self.force = force

        def run(self) -> None:
            try:
                products, is_live = load_products_catalog(
                    products_url=self.products_url, force_refresh=self.force,
                    custom_cache_dir=self.cache_dir, timeout=4.0,
                )
                self.finished_catalog.emit(products, bool(is_live), "")
            except Exception as exc:
                self.finished_catalog.emit([], False, f"{type(exc).__name__}: {exc}")


    class FfmpegDownloadThread(QThread):
        progress_changed = pyqtSignal(int)
        finished_ok = pyqtSignal(bool, str)

        def __init__(self, data_dir: Path):
            super().__init__()
            self.data_dir = data_dir
            self._cancel = False

        def cancel(self) -> None:
            self._cancel = True

        def run(self) -> None:
            ok, msg = download_ffmpeg(self.data_dir, progress=self.progress_changed.emit, cancel=lambda: self._cancel)
            self.finished_ok.emit(ok, msg)

    class NetworkCheckWorkerThread(QThread):
        update_fetched = pyqtSignal(dict)

        def __init__(self, update_url: str, cache_dir: Path, license_mgr: LicenseManager):
            super().__init__()
            self.update_url = update_url
            self.cache_dir = cache_dir
            self.license_mgr = license_mgr

        def run(self) -> None:
            try:
                data, _fresh = refresh_update_data(self.update_url, self.cache_dir, self.license_mgr, timeout=4.0)
            except Exception:
                data = None
            if isinstance(data, dict):
                self.update_fetched.emit(data)

    class IntegrityWorkerThread(QThread):
        done = pyqtSignal(str, list)

        def run(self) -> None:
            try:
                exe = launcher_path()
                if exe is None:
                    self.done.emit("skipped", [])
                    return
                status, problems = check_integrity(exe.parent)
                self.done.emit(status, list(problems))
            except Exception:
                self.done.emit("skipped", [])

    class ReverifyWorkerThread(QThread):
        done = pyqtSignal(str)

        def __init__(self, mgr: LicenseManager):
            super().__init__()
            self.mgr = mgr

        def run(self) -> None:
            self.done.emit(self.mgr.reverify_current_license())

    class GuideDialog(QDialog):
        def __init__(self, controller: StudioAppController, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.controller = controller
            lang = controller.lang
            self.setWindowTitle(tr("btn_guide", lang))
            self.resize(860, 580)
            layout = QHBoxLayout(self)
            self.nav_list = QListWidget()
            self.nav_list.setMaximumWidth(260)
            self.browser = QTextBrowser()
            self.browser.setOpenExternalLinks(True)
            self.sections = get_guide_sections()
            for sec in self.sections:
                self.nav_list.addItem(sec["title_ar"] if lang == "ar" else sec["title_en"])
            self.nav_list.currentRowChanged.connect(self._on_section_changed)
            layout.addWidget(self.nav_list)
            layout.addWidget(self.browser, 1)
            if self.sections:
                self.nav_list.setCurrentRow(0)

        def _on_section_changed(self, row: int) -> None:
            if 0 <= row < len(self.sections):
                sec = self.sections[row]
                self.browser.setHtml(sec["html_ar"] if self.controller.lang == "ar" else sec["html_en"])

    class ManualPaymentDialog(QDialog):
        def __init__(self, controller: StudioAppController, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.controller = controller
            lang = controller.lang
            self.setWindowTitle(tr("pay_dialog_title", lang))
            self.resize(520, 380)
            layout = QVBoxLayout(self)
            payment = controller.license_mgr.get_verified_payment_info()
            if not payment:
                warn = QLabel(tr("pay_unverified_warning", lang))
                warn.setWordWrap(True)
                layout.addWidget(warn)
            else:
                form = QFormLayout()
                for field_key, label_key in (
                    ("price", "pay_price"),
                    ("bank_name", "pay_bank_name"),
                    ("bank_account", "pay_bank_account"),
                    ("instapay", "pay_instapay"),
                    ("wallet", "pay_wallet"),
                ):
                    val_lbl = QLineEdit(payment.get(field_key, "-"))
                    val_lbl.setReadOnly(True)
                    val_lbl.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                    form.addRow(tr(label_key, lang), val_lbl)
                layout.addLayout(form)
                wa_number = payment.get("whatsapp", "").strip()
                if wa_number:
                    btn_wa = QPushButton(tr("pay_whatsapp_btn", lang))
                    btn_wa.setObjectName("AccentButton")
                    btn_wa.clicked.connect(lambda: self._open_whatsapp(wa_number))
                    layout.addWidget(btn_wa)
            btn_close = QPushButton(tr("btn_close", lang))
            btn_close.clicked.connect(self.accept)
            layout.addWidget(btn_close)

        def _open_whatsapp(self, phone: str) -> None:
            clean_phone = "".join(ch for ch in phone if ch.isdigit())
            msg = (
                f"مرحباً، أرغب في شراء سيريال تفعيل لتطبيق HMZ Video Studio Pro (VSP).\n"
                f"رقم جهازي (Machine ID): {self.controller.license_mgr.dev_id}"
            )
            webbrowser.open(f"https://wa.me/{clean_phone}?text={urllib.parse.quote(msg)}")

    class LicenseDialog(QDialog):
        def __init__(self, controller: StudioAppController, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.controller = controller
            lang = controller.lang
            self.setWindowTitle(tr("lic_dialog_title", lang))
            self.resize(560, 360)
            layout = QVBoxLayout(self)
            self.lbl_status = QLabel()
            layout.addWidget(self.lbl_status)

            mach_row = QHBoxLayout()
            mach_row.addWidget(QLabel(tr("lic_machine_id", lang)))
            self.txt_machine = QLineEdit(controller.license_mgr.dev_id)
            self.txt_machine.setReadOnly(True)
            self.txt_machine.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            btn_copy = QPushButton(tr("btn_copy_machine_id", lang))
            btn_copy.clicked.connect(self._copy_machine_id)
            mach_row.addWidget(self.txt_machine, 1)
            mach_row.addWidget(btn_copy)
            layout.addLayout(mach_row)

            self.txt_key = QLineEdit(controller.license_mgr.state.get("license_key", ""))
            self.txt_key.setPlaceholderText(tr("lic_input_placeholder", lang))
            self.txt_key.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            layout.addWidget(self.txt_key)

            btn_row1 = QHBoxLayout()
            btn_activate = QPushButton(tr("btn_activate", lang))
            btn_activate.setObjectName("AccentButton")
            btn_activate.clicked.connect(self._on_activate)
            btn_reverify = QPushButton(tr("btn_reverify", lang))
            btn_reverify.clicked.connect(self._on_reverify)
            btn_row1.addWidget(btn_activate)
            btn_row1.addWidget(btn_reverify)
            layout.addLayout(btn_row1)

            btn_row2 = QHBoxLayout()
            btn_gumroad = QPushButton(tr("btn_buy_gumroad", lang))
            btn_gumroad.clicked.connect(lambda: webbrowser.open(GUMROAD_BUY_URL))
            btn_manual_pay = QPushButton(tr("btn_manual_payment", lang))
            btn_manual_pay.clicked.connect(lambda: ManualPaymentDialog(self.controller, self).exec())
            btn_row2.addWidget(btn_gumroad)
            btn_row2.addWidget(btn_manual_pay)
            layout.addLayout(btn_row2)
            self._refresh_status_label()

        def _refresh_status_label(self) -> None:
            lang = self.controller.lang
            if self.controller.license_mgr.is_activated():
                self.lbl_status.setText(f"✅ {tr('pro_status_badge', lang)}")
            else:
                rem = self.controller.license_mgr.remaining_free_operations()
                self.lbl_status.setText(f"⏳ {tr('trial_status_badge', lang, n=rem)}")

        def _copy_machine_id(self) -> None:
            cb = QApplication.clipboard()
            if cb is not None:
                cb.setText(self.controller.license_mgr.dev_id)
            QMessageBox.information(self, "HMZ", tr("copied_toast", self.controller.lang))

        def _on_activate(self) -> None:
            lang = self.controller.lang
            res = self.controller.license_mgr.activate_key(self.txt_key.text())
            msg_key = license_message_key(res)
            self._refresh_status_label()
            if res == "ok":
                QMessageBox.information(self, "HMZ", tr(msg_key, lang))
            else:
                QMessageBox.warning(self, "HMZ", tr(msg_key, lang))

        def _on_reverify(self) -> None:
            lang = self.controller.lang
            res = self.controller.license_mgr.reverify_current_license()
            self._refresh_status_label()
            QMessageBox.information(self, "HMZ", tr(license_message_key(res), lang))

    class StoreDialog(QDialog):
        def __init__(self, controller: StudioAppController, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.controller = controller
            lang = controller.lang
            self.setWindowTitle(tr("store_dialog_title", lang))
            self.resize(640, 440)
            layout = QVBoxLayout(self)
            top_row = QHBoxLayout()
            self.lbl_note = QLabel("")
            btn_refresh = QPushButton(tr("store_refresh_btn", lang))
            btn_refresh.clicked.connect(lambda: self._populate(force=True))
            top_row.addWidget(self.lbl_note, 1)
            top_row.addWidget(btn_refresh)
            layout.addLayout(top_row)

            self.list_widget = QListWidget()
            layout.addWidget(self.list_widget, 1)

            btn_open = QPushButton(tr("store_open_btn", lang))
            btn_open.setObjectName("AccentButton")
            btn_open.clicked.connect(self._open_selected)
            layout.addWidget(btn_open)
            self.products: List[Dict[str, str]] = []
            self._catalog_worker: Optional[ProductCatalogWorkerThread] = None
            self._populate(force=False)

        def _render_products(self, products: List[Dict[str, str]]) -> None:
            lang = self.controller.lang
            self.products = list(products or [])
            current = self.list_widget.currentRow()
            self.list_widget.clear()
            for item in self.products:
                name = item.get("name_ar" if lang == "ar" else "name_en", item.get("id", "App"))
                desc = item.get("desc_ar" if lang == "ar" else "desc_en", "")
                price = item.get("price", "")
                price_str = f"  [{price}]" if price else ""
                self.list_widget.addItem(QListWidgetItem(f"{name}{price_str}\n{desc}"))
            if self.products:
                self.list_widget.setCurrentRow(min(max(0, current), len(self.products) - 1))

        def _populate(self, force: bool = False) -> None:
            """Paint the disk cache immediately; fetch/update the catalog off the GUI thread."""
            lang = self.controller.lang
            cached, _ = load_cached_products_catalog(self.controller.custom_data_dir)
            if cached:
                self._render_products(cached)
            if self._catalog_worker is not None and self._catalog_worker.isRunning():
                return
            self.lbl_note.setText("جارٍ تحديث قائمة المنتجات…" if lang == "ar" else "Updating product catalog…")
            self._catalog_worker = ProductCatalogWorkerThread(
                self.controller.settings.data.get("products_url", DEFAULT_PRODUCTS_JSON_URL),
                self.controller.custom_data_dir, force,
            )
            self._catalog_worker.finished_catalog.connect(self._on_catalog_loaded)
            self._catalog_worker.finished.connect(self._on_catalog_thread_finished)
            _track_qt_worker(self._catalog_worker)
            self._catalog_worker.start()

        def _on_catalog_loaded(self, products: Any, is_live: bool, error: str) -> None:
            if products:
                self._render_products(list(products))
            if error:
                self.lbl_note.setText(tr("store_offline_note", self.controller.lang))
            else:
                self.lbl_note.setText("" if is_live else tr("store_offline_note", self.controller.lang))

        def _on_catalog_thread_finished(self) -> None:
            worker = self._catalog_worker
            self._catalog_worker = None
            if worker is not None:
                worker.deleteLater()

        def closeEvent(self, event: Any) -> None:
            worker = self._catalog_worker
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                # The worker was registered when it started; it remains alive until
                # its finished signal even after this dialog is destroyed.
            super().closeEvent(event)

        def _open_selected(self) -> None:
            row = self.list_widget.currentRow()
            if 0 <= row < len(self.products):
                url = self.products[row].get("url", GUMROAD_BUY_URL)
                if url:
                    webbrowser.open(url)

    class AboutDialog(QDialog):
        def __init__(self, controller: StudioAppController, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.controller = controller
            lang = controller.lang
            self.setWindowTitle(tr("about_dialog_title", lang))
            self.resize(460, 280)
            layout = QVBoxLayout(self)
            layout.addWidget(QLabel(f"<h2>HMZ Video Studio Pro v{APP_VERSION}</h2>"))
            status_txt = (
                tr("pro_status_badge", lang)
                if controller.license_mgr.is_activated()
                else tr("trial_status_badge", lang, n=controller.license_mgr.remaining_free_operations())
            )
            layout.addWidget(QLabel(f"{tr('lic_status_label', lang)} {status_txt}"))

            mach_row = QHBoxLayout()
            mach_edit = QLineEdit(controller.license_mgr.dev_id)
            mach_edit.setReadOnly(True)
            mach_edit.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            btn_copy = QPushButton(tr("btn_copy_machine_id", lang))
            btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(controller.license_mgr.dev_id))
            mach_row.addWidget(QLabel(tr("lic_machine_id", lang)))
            mach_row.addWidget(mach_edit, 1)
            mach_row.addWidget(btn_copy)
            layout.addLayout(mach_row)

            layout.addWidget(QLabel(tr("about_integrity", lang, status=controller.integrity_status)))
            layout.addWidget(QLabel(tr("about_copyright", lang)))
            btn_support = QPushButton(tr("about_support_btn", lang))
            btn_support.clicked.connect(lambda: webbrowser.open("https://hmzbytes.gumroad.com"))
            layout.addWidget(btn_support)

    class FfmpegDialog(QDialog):
        """Explains why FFmpeg is needed and lets the user download it, pick it manually, or continue without it.
        `mode`: startup | export (project has sound; offers 'export without sound') | audio_only (wav/mp3)."""

        def __init__(self, controller: StudioAppController, mode: str = "startup", parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.controller = controller
            self.mode = mode
            self.action = "later"  # installed | silent | later | cancel
            self._thread: Optional[Any] = None
            lang = controller.lang
            self.setWindowTitle(tr("ff_title", lang))
            self.resize(520, 300)
            lay = QVBoxLayout(self)
            body = QLabel(tr({"startup": "ff_body_startup", "export": "ff_body_export", "audio_only": "ff_body_audio_only"}[mode], lang))
            body.setWordWrap(True)
            lay.addWidget(body)
            self.progress = QProgressBar()
            self.progress.setVisible(False)
            lay.addWidget(self.progress)
            self.lbl = QLabel("")
            self.lbl.setWordWrap(True)
            lay.addWidget(self.lbl)
            self.btn_dl = QPushButton(tr("ff_btn_download", lang))
            self.btn_dl.setObjectName("AccentButton")
            self.btn_dl.clicked.connect(self._start_download)
            btn_browse = QPushButton(tr("ff_btn_browse", lang))
            btn_browse.clicked.connect(self._browse)
            btn_page = QPushButton(tr("ff_btn_page", lang))
            btn_page.clicked.connect(lambda: webbrowser.open(FFMPEG_DOWNLOAD_PAGE))
            for b in (self.btn_dl, btn_browse, btn_page):
                lay.addWidget(b)
            self.chk_never = QCheckBox(tr("ff_chk_never", lang))
            self.chk_never.setVisible(mode == "startup")
            lay.addWidget(self.chk_never)
            row = QHBoxLayout()
            if mode == "export":
                b_silent = QPushButton(tr("ff_btn_silent", lang))
                b_silent.clicked.connect(lambda: self._finish("silent"))
                row.addWidget(b_silent)
            b_later = QPushButton(tr("ff_btn_later" if mode == "startup" else "ff_btn_cancel", lang))
            b_later.clicked.connect(lambda: self._finish("later" if mode == "startup" else "cancel"))
            row.addWidget(b_later)
            lay.addLayout(row)

        def _finish(self, action: str) -> None:
            if self._thread is not None and self._thread.isRunning():
                self._thread.cancel()
                self._thread.requestInterruption()
            if action == "later" and self.mode == "startup" and self.chk_never.isChecked():
                self.controller.settings.data["ffmpeg_never_ask_startup"] = True
                self.controller.settings.save()
            self.action = action
            self.accept()

        def _set_busy(self, busy: bool) -> None:
            self.btn_dl.setEnabled(not busy)
            self.progress.setVisible(busy)

        def _start_download(self) -> None:
            self._set_busy(True)
            self.progress.setValue(0)
            self.lbl.setText(tr("ff_downloading", self.controller.lang))
            self._thread = FfmpegDownloadThread(get_app_data_dir(self.controller.custom_data_dir))
            _track_qt_worker(self._thread)
            self._thread.progress_changed.connect(self.progress.setValue)
            self._thread.finished_ok.connect(self._on_downloaded)
            self._thread.start()

        def closeEvent(self, event: Any) -> None:
            if self._thread is not None and self._thread.isRunning():
                self._thread.cancel()
            super().closeEvent(event)

        def _on_downloaded(self, ok: bool, msg: str) -> None:
            lang = self.controller.lang
            self._set_busy(False)
            if ok:
                self.controller.settings.data["ffmpeg_path"] = msg
                self.controller.settings.save()
                QMessageBox.information(self, "HMZ", tr("ff_ok", lang))
                self._finish("installed")
            else:
                self.lbl.setText(tr("ff_fail", lang, err=msg))

        def _browse(self) -> None:
            lang = self.controller.lang
            path, _ = QFileDialog.getOpenFileName(self, tr("ff_btn_browse", lang), "", "ffmpeg (ffmpeg.exe ffmpeg);;All (*)")
            if not path:
                return
            if not validate_ffmpeg(path):
                self.lbl.setText(tr("ff_invalid", lang))
                return
            self.controller.settings.data["ffmpeg_path"] = path
            self.controller.settings.save()
            QMessageBox.information(self, "HMZ", tr("ff_ok", lang))
            self._finish("installed")

    class ExportDialog(QDialog):
        def __init__(self, controller: StudioAppController, parent: Optional[QWidget] = None):
            super().__init__(parent)
            self.controller = controller
            lang = controller.lang
            self.setWindowTitle(tr("export_dialog_title", lang))
            self.resize(500, 300)
            layout = QVBoxLayout(self)
            form = QFormLayout()
            path_row = QHBoxLayout()
            default_out = str(Path.home() / "hmz_exported_video.mp4")
            self.txt_path = QLineEdit(default_out)
            self.txt_path.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            btn_browse = QPushButton(tr("btn_browse", lang))
            btn_browse.clicked.connect(self._browse_output)
            path_row.addWidget(self.txt_path, 1)
            path_row.addWidget(btn_browse)
            form.addRow(tr("export_output_path", lang), path_row)

            self.cmb_res = QComboBox()
            for r_label in RESOLUTION_PRESETS:
                self.cmb_res.addItem(r_label)
            self.cmb_res.setCurrentIndex(1)
            form.addRow(tr("export_resolution", lang), self.cmb_res)

            self.cmb_fps = QComboBox()
            for fps_val in ("24", "30", "60"):
                self.cmb_fps.addItem(fps_val)
            self.cmb_fps.setCurrentIndex(1)
            form.addRow(tr("export_fps", lang), self.cmb_fps)

            self.cmb_quality = QComboBox()
            for key, label_key in (("high", "quality_high"), ("balanced", "quality_medium"), ("compact", "quality_compact")):
                self.cmb_quality.addItem(tr(label_key, lang), key)
            saved_q = str(controller.settings.data.get("export_quality", "balanced"))
            self.cmb_quality.setCurrentIndex(max(0, self.cmb_quality.findData(saved_q)))
            form.addRow(tr("export_quality", lang), self.cmb_quality)

            self.chk_gpu = QCheckBox(tr("export_use_gpu", lang))
            ff = controller.ffmpeg_path()
            self.chk_gpu.setVisible(bool(ff) and detect_nvenc(ff))  # shown only if an NVIDIA encoder really works
            self.chk_gpu.setChecked(bool(controller.settings.data.get("export_use_gpu", False)))
            form.addRow("", self.chk_gpu)
            layout.addLayout(form)

            btn_start = QPushButton(tr("btn_start_export", lang))
            btn_start.setObjectName("AccentButton")
            btn_start.clicked.connect(self.accept)
            layout.addWidget(btn_start)

        def _browse_output(self) -> None:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                tr("export_output_path", self.controller.lang),
                self.txt_path.text(),
                "Video / Audio (*.mp4 *.mov *.gif *.wav *.mp3)",
            )
            if file_path:
                self.txt_path.setText(file_path)

    class VideoStudioMainWindow(QMainWindow):
        """Main Window implementing the 5-Zone CapCut Pro Desktop Layout."""

        def __init__(self, controller: Optional[StudioAppController] = None, start_home: bool = False):
            super().__init__()
            self.controller = controller or StudioAppController()
            self._export_worker: Optional[ExportWorkerThread] = None
            self._session_started = False       # becomes True once the editor page has been shown
            self._pending_recovery = False      # unsaved work from a crashed session is waiting (offered on Home)
            self._palette: Dict[str, str] = {}
            self._editor_built = False
            self._closing = False
            self._proxy_workers: Dict[str, ProxyWorkerThread] = {}
            self._stabilization_workers: Dict[str, StabilizationWorkerThread] = {}
            self.preview_canvas = None
            self.preview_audio = None
            self._play_timer = QTimer(self)
            self._play_timer.setInterval(33)
            self._play_timer.setTimerType(Qt.TimerType.PreciseTimer)
            self._play_timer.timeout.connect(self._on_playback_tick)
            self._tick_count = 0
            self._ticking = False
            self._autosave_timer = QTimer(self)
            self._autosave_timer.setInterval(60 * 1000)
            self._autosave_timer.timeout.connect(self.controller.autosave_if_dirty)
            self._autosave_timer.start()
            self.resize(
                int(self.controller.settings.data.get("window_width", 1440)),
                int(self.controller.settings.data.get("window_height", 880)),
            )
            self.setAcceptDrops(True)
            icon_path = _resource_path("icon.ico")
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
            self._build_ui()
            geo = self.controller.settings.data.get("geometry", "")
            if geo:
                try:
                    self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
                except Exception:
                    pass
            self.apply_language_and_theme()
            if start_home:
                self._pending_recovery = self.controller.has_recovery()
                self.show_home()
            else:
                self.show_editor()
            hints = QGuiApplication.styleHints()
            if hints is not None and hasattr(hints, "colorSchemeChanged"):
                hints.colorSchemeChanged.connect(lambda *_: self.apply_language_and_theme() if self.controller.settings.data.get("theme") == "system" else None)
            if is_compiled():  # integrity check only makes sense for the distributed build
                self._integrity_worker = IntegrityWorkerThread()
                _track_qt_worker(self._integrity_worker)
                self._integrity_worker.done.connect(self._on_integrity_done)
                self._integrity_worker.start()
            QTimer.singleShot(900, self._start_background_update_check)
            if not start_home:  # on the Home screen the recovery offer is a banner instead of a popup
                QTimer.singleShot(600, self._maybe_offer_recovery)
            QTimer.singleShot(2500, self._maybe_prompt_ffmpeg)
            QTimer.singleShot(4000, self._maybe_reverify_license)
            self._hourly_timer = QTimer(self)
            try:
                hours = max(1.0, float(self.controller.settings.data.get("update_check_hours", 6)))
            except (TypeError, ValueError):
                hours = 6.0
            self._hourly_timer.setInterval(int(hours * 3600 * 1000))
            self._hourly_timer.timeout.connect(self._start_background_update_check)
            self._hourly_timer.start()

        def _build_ui(self) -> None:
            """Build only the lightweight Home shell; the editing workspace is lazy."""
            self._stack = QStackedWidget()
            self.home = HomeScreen(self.controller, self)
            self.home.new_project.connect(self._home_new)
            self.home.open_project_dialog.connect(self._home_open_dialog)
            self.home.import_media.connect(self._home_import)
            self.home.resume_editor.connect(self.show_editor)
            self.home.open_recent.connect(self._open_recent)
            self.home.recover_requested.connect(self._on_recover)
            self.home.discard_recovery_requested.connect(self._on_discard_recovery)
            self.home.open_guide.connect(self._open_guide)
            self.home.open_store.connect(self._open_store)
            self.home.open_about.connect(self._open_about)
            self.home.open_license.connect(self._open_license_dialog)
            self.home.toggle_language.connect(self._on_toggle_language)
            self.home.update_clicked.connect(self._open_update_url)
            self.editor_page = QWidget()  # empty placeholder until the user enters the editor
            self._stack.addWidget(self.home)
            self._stack.addWidget(self.editor_page)
            self.setCentralWidget(self._stack)
            self.main_menu = self._build_main_menu()
            self.home.set_menu(self.main_menu)

        def _build_editor_ui(self) -> None:
            """Import/build the full editor only on first entry; preserve it thereafter."""
            if self._editor_built:
                return
            self._build_editor_ui_body()
            try:
                from video_studio_audio import PreviewAudio
            except Exception:
                PreviewAudio = None
            if PreviewAudio is not None and self.controller.settings.data.get("preview_audio", True):
                try:
                    self.preview_audio = PreviewAudio(lambda: self.controller.project, self.controller.ffmpeg_path, self)
                    self.preview_audio.status.connect(self._on_audio_status)
                except Exception:
                    self.preview_audio = None
            self.apply_language_and_theme()

        def _build_editor_ui_body(self) -> None:
            from video_studio_panels import BrowserPanel, InspectorPanel
            from video_studio_timeline import MultiTrackTimelineWidget, PreviewCanvasWidget

            central = self.editor_page
            root_layout = QVBoxLayout(central)
            root_layout.setContentsMargins(4, 4, 4, 2)
            root_layout.setSpacing(3)

            header = QFrame()
            header.setObjectName("HeaderBar")
            h_layout = QHBoxLayout(header)
            h_layout.setContentsMargins(6, 3, 6, 3)
            h_layout.setSpacing(3)

            self.btn_home = QPushButton()
            self.btn_home.setObjectName("GhostButton")
            self.btn_home.clicked.connect(self.show_home)
            self.btn_new = QPushButton()
            self.btn_new.clicked.connect(self._on_new_project)
            self.btn_open = QPushButton()
            self.btn_open.clicked.connect(self._on_open_project)
            self.btn_save = QPushButton()
            self.btn_save.clicked.connect(lambda: self._on_save_project())
            self.btn_import = QPushButton()
            self.btn_import.clicked.connect(self._on_import_media)
            for gb in (self.btn_new, self.btn_open, self.btn_save, self.btn_import):
                gb.setObjectName("GhostButton")

            self.btn_menu = QToolButton()
            self.btn_menu.setObjectName("GhostButton")
            self.btn_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            self.btn_menu.setMenu(self.main_menu)

            self.btn_export = QPushButton()
            self.btn_export.setObjectName("AccentButton")
            self.btn_export.setMinimumWidth(90)
            self.btn_export.clicked.connect(self._on_export_clicked)

            h_layout.addWidget(self.btn_home)
            sep = QFrame()
            sep.setObjectName("VSep")
            sep.setFixedSize(1, 20)
            h_layout.addWidget(sep)
            for w in (self.btn_new, self.btn_open, self.btn_save, self.btn_import):
                h_layout.addWidget(w)
            h_layout.addStretch(1)
            h_layout.addWidget(self.btn_menu)
            h_layout.addSpacing(4)
            h_layout.addWidget(self.btn_export)
            root_layout.addWidget(header)

            main_vsplit = QSplitter(Qt.Orientation.Vertical)
            upper_hsplit = QSplitter(Qt.Orientation.Horizontal)

            self.browser_tabs = BrowserPanel(self)
            upper_hsplit.addWidget(self.browser_tabs)

            center_panel = QFrame()
            center_panel.setObjectName("PanelFrame")
            c_layout = QVBoxLayout(center_panel)
            c_layout.setContentsMargins(4, 4, 4, 4)
            c_layout.setSpacing(3)
            self.preview_canvas = PreviewCanvasWidget(self.controller, self, self)
            c_layout.addWidget(self.preview_canvas, 1)

            transport_row = QHBoxLayout()
            transport_row.setSpacing(4)
            self.btn_play = QPushButton()
            self.btn_play.setObjectName("IconButton")
            self.btn_play.clicked.connect(self._toggle_playback)
            self.btn_stop = QPushButton()
            self.btn_stop.setObjectName("IconButton")
            self.btn_stop.clicked.connect(self._stop_playback)
            self.btn_snapshot = QPushButton()
            self.btn_snapshot.clicked.connect(self._on_snapshot)
            self.lbl_timecode = QLabel("00:00:00:00 / 00:00:05:00")
            self.lbl_timecode.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

            self.cmb_aspect = QComboBox()
            self.cmb_aspect.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            for ar in ASPECT_RATIOS:
                self.cmb_aspect.addItem(ar)
            self.cmb_aspect.currentTextChanged.connect(self._on_aspect_changed)

            self.cmb_prev_quality = QComboBox()
            self.cmb_prev_quality.addItems(["100%", "50%", "25%"])
            self.cmb_prev_quality.setCurrentIndex(1)
            self.cmb_prev_quality.currentIndexChanged.connect(self._on_preview_quality_changed)

            transport_row.addWidget(self.btn_play)
            transport_row.addWidget(self.btn_stop)
            transport_row.addWidget(self.lbl_timecode)
            transport_row.addStretch(1)
            transport_row.addWidget(self.btn_snapshot)
            transport_row.addWidget(self.cmb_aspect)
            transport_row.addWidget(self.cmb_prev_quality)
            c_layout.addLayout(transport_row)
            upper_hsplit.addWidget(center_panel)

            self.inspector_tabs = InspectorPanel(self)
            upper_hsplit.addWidget(self.inspector_tabs)
            upper_hsplit.setSizes([340, 640, 400])
            upper_hsplit.setStretchFactor(0, 0)
            upper_hsplit.setStretchFactor(1, 1)
            upper_hsplit.setStretchFactor(2, 0)
            upper_hsplit.setChildrenCollapsible(False)
            main_vsplit.setChildrenCollapsible(False)
            main_vsplit.addWidget(upper_hsplit)

            timeline_container = QFrame()
            timeline_container.setObjectName("PanelFrame")
            tl_layout = QVBoxLayout(timeline_container)
            tl_layout.setContentsMargins(4, 3, 4, 3)
            tl_layout.setSpacing(3)

            tl_bar = QHBoxLayout()
            tl_bar.setSpacing(3)
            self.btn_split = QPushButton()
            self.btn_split.clicked.connect(self._on_split_clip)
            self.btn_del_clip = QPushButton()
            self.btn_del_clip.clicked.connect(self._on_delete_clip)
            self.btn_undo = QPushButton()
            self.btn_undo.clicked.connect(self._on_undo)
            self.btn_redo = QPushButton()
            self.btn_redo.clicked.connect(self._on_redo)
            self.btn_marker = QPushButton()
            self.btn_marker.clicked.connect(self._on_add_marker)
            self.chk_snap = QCheckBox()
            self.chk_snap.setChecked(True)
            self.chk_snap.toggled.connect(lambda v: setattr(self.controller.project, "snapping_enabled", v))
            self.btn_magnet = QPushButton()
            self.btn_magnet.clicked.connect(lambda: self.close_track_gaps(None))
            self.lbl_tracks = QLabel()
            self.lbl_tracks.setObjectName("HintLabel")
            self.btn_add_vtrack = QPushButton()
            self.btn_add_vtrack.clicked.connect(lambda: self._on_add_track("video"))
            self.btn_add_stracks = QPushButton()
            self.btn_add_stracks.clicked.connect(lambda: self._on_add_track("sticker"))
            self.btn_add_ttrack = QPushButton()
            self.btn_add_ttrack.clicked.connect(lambda: self._on_add_track("text"))
            self.btn_add_atrack = QPushButton()
            self.btn_add_atrack.clicked.connect(lambda: self._on_add_track("audio"))
            self.btn_fit = QPushButton()
            self.btn_fit.clicked.connect(lambda: self.timeline_widget.fit_to_view())

            self.sld_zoom = QSlider(Qt.Orientation.Horizontal)
            self.sld_zoom.setRange(4, 300)
            self.sld_zoom.setValue(65)
            self.sld_zoom.setFixedWidth(110)

            for w in (self.btn_split, self.btn_del_clip, self.btn_undo, self.btn_redo, self.btn_marker, self.chk_snap, self.btn_magnet):
                tl_bar.addWidget(w)
            tl_bar.addSpacing(8)
            tl_bar.addWidget(self.lbl_tracks)
            for w in (self.btn_add_vtrack, self.btn_add_stracks, self.btn_add_ttrack, self.btn_add_atrack):
                tl_bar.addWidget(w)
            tl_bar.addStretch(1)
            tl_bar.addWidget(self.btn_fit)
            tl_bar.addWidget(self.sld_zoom)
            tl_layout.addLayout(tl_bar)

            self.timeline_widget = MultiTrackTimelineWidget(self.controller, self, self)
            self.sld_zoom.valueChanged.connect(lambda v: self.timeline_widget.set_zoom(float(v)))
            self.timeline_widget.playhead_changed.connect(self._on_playhead_changed)
            self.timeline_widget.clip_selected.connect(self._on_clip_selected)
            self.preview_canvas.clip_selected.connect(self._on_clip_selected)
            self.timeline_widget.clip_edit_requested.connect(lambda cid: self.open_inspector_for(cid, focus_text=True))
            self.preview_canvas.edit_requested.connect(lambda cid: self.open_inspector_for(cid, focus_text=True))
            self.preview_canvas.clip_moved.connect(lambda *_: self.inspector_tabs.load_clip())
            self.preview_canvas.clip_changed.connect(lambda: (self.inspector_tabs.load_clip(), self.timeline_widget.update()))
            self.timeline_widget.zoom_changed.connect(lambda v: (self.sld_zoom.blockSignals(True), self.sld_zoom.setValue(int(v)), self.sld_zoom.blockSignals(False)))
            self.timeline_widget.timeline_modified.connect(self.preview_canvas.refresh_frame)
            tl_layout.addWidget(self.timeline_widget, 1)

            main_vsplit.addWidget(timeline_container)
            main_vsplit.setSizes([480, 300])
            main_vsplit.setStretchFactor(0, 1)
            main_vsplit.setStretchFactor(1, 0)
            root_layout.addWidget(main_vsplit, 1)

            status_row = QHBoxLayout()
            status_row.setContentsMargins(4, 0, 4, 0)
            self.lbl_status = QLabel()
            self.lbl_lic_badge = QLabel()
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setVisible(False)
            self.btn_cancel_task = QPushButton()
            self.btn_cancel_task.setObjectName("DangerButton")
            self.btn_cancel_task.setVisible(False)
            self.btn_cancel_task.clicked.connect(self._cancel_running_task)

            status_row.addWidget(self.lbl_status)
            status_row.addStretch(1)
            status_row.addWidget(self.progress_bar)
            status_row.addWidget(self.btn_cancel_task)
            status_row.addWidget(self.lbl_lic_badge)
            root_layout.addLayout(status_row)

            QShortcut(QKeySequence("F1"), self, activated=self._open_guide)
            QShortcut(QKeySequence("Ctrl+H"), self, activated=self.show_home)
            QShortcut(QKeySequence("Space"), central, activated=self._toggle_playback)
            QShortcut(QKeySequence("Ctrl+B"), central, activated=self._on_split_clip)
            QShortcut(QKeySequence("Delete"), central, activated=self.delete_selected)
            QShortcut(QKeySequence("Shift+Delete"), central, activated=self.ripple_delete_selected)
            QShortcut(QKeySequence("Ctrl+Z"), central, activated=self._on_undo)
            QShortcut(QKeySequence("Ctrl+Y"), central, activated=self._on_redo)
            QShortcut(QKeySequence("Ctrl+C"), central, activated=self.copy_selected)
            QShortcut(QKeySequence("Ctrl+X"), central, activated=self.cut_selected)
            QShortcut(QKeySequence("Ctrl+V"), central, activated=lambda: self.paste_clipboard(None, self.controller.project.playhead_sec))
            QShortcut(QKeySequence("Ctrl+D"), central, activated=self.duplicate_selected)
            QShortcut(QKeySequence("Ctrl+A"), central, activated=self.select_all)
            QShortcut(QKeySequence("M"), central, activated=self._on_add_marker)
            QShortcut(QKeySequence("Return"), central, activated=lambda: self.controller.selected_clip_id and self.open_inspector_for(self.controller.selected_clip_id, focus_text=True))
            QShortcut(QKeySequence("Left"), central, activated=lambda: self._step_playhead(-1.0 / self.controller.project.fps))
            QShortcut(QKeySequence("Right"), central, activated=lambda: self._step_playhead(1.0 / self.controller.project.fps))
            QShortcut(QKeySequence("Shift+Left"), central, activated=lambda: self._step_playhead(-1.0))
            QShortcut(QKeySequence("Shift+Right"), central, activated=lambda: self._step_playhead(1.0))
            QShortcut(QKeySequence("Home"), central, activated=lambda: self._step_playhead(-1e9))
            QShortcut(QKeySequence("End"), central, activated=lambda: self._step_playhead(1e9))
            QShortcut(QKeySequence("Ctrl+S"), central, activated=lambda: self._on_save_project())
            QShortcut(QKeySequence("Ctrl+Shift+S"), central, activated=lambda: self._on_save_project(save_as=True))
            QShortcut(QKeySequence("Ctrl+O"), central, activated=self._on_open_project)
            QShortcut(QKeySequence("Ctrl+N"), central, activated=self._on_new_project)

            self._editor_built = True
        def _build_browser_tabs(self) -> None:
            pass  # BrowserPanel is created in _build_ui

        def _build_inspector_tabs(self) -> None:
            pass  # InspectorPanel is created in _build_ui

        # ---- shared refresh helpers used by the panels ----
        def register_background_worker(self, worker: Any) -> Any:
            """Register panel-owned QThreads so application shutdown can cancel and join them."""
            return _track_qt_worker(worker)

        def refresh_preview_only(self) -> None:
            self.timeline_widget.update()
            self.preview_canvas.refresh_frame()

        def refresh_all(self) -> None:
            if not self._editor_built:
                return
            if self.preview_audio is not None:
                self.preview_audio.project_changed()
            # One cache invalidation + one preview request (the old sequence requested the same frame twice).
            self.timeline_widget.invalidate()
            self.browser_tabs.refresh_media()
            self.browser_tabs.refresh_audio()
            self.inspector_tabs.load_clip()
            self.cmb_aspect.blockSignals(True)
            self.cmb_aspect.setCurrentText(self.controller.project.aspect_ratio)
            self.cmb_aspect.blockSignals(False)
            self._on_playhead_changed(self.controller.project.playhead_sec)

        # ---- background media jobs -----------------------------------------------
        def generate_proxy_for_clip(self, clip_id: str) -> None:
            if not self._editor_built or clip_id in self._proxy_workers:
                return
            found = self.controller.project.find_clip(clip_id)
            if not found:
                return
            _track, clip = found
            if clip.clip_type != "video" or not Path(clip.source_path).is_file():
                return
            ffmpeg = self.controller.ffmpeg_path()
            if not ffmpeg:
                self.lbl_status.setText("FFmpeg is required to generate a proxy")
                return
            out_dir = get_app_data_dir(self.controller.custom_data_dir) / "proxies"
            worker = ProxyWorkerThread(self.controller.project, clip_id, out_dir, ffmpeg)
            worker.finished_result.connect(self._on_proxy_finished)
            worker.finished.connect(lambda cid=clip_id: self._release_proxy_worker(cid))
            self._proxy_workers[clip_id] = worker
            _track_qt_worker(worker)
            self.lbl_status.setText("Generating proxy in background…")
            worker.start()

        def _on_proxy_finished(self, clip_id: str, proxy_path: str, error: str) -> None:
            if self._closing:
                return
            found = self.controller.project.find_clip(clip_id)
            if proxy_path and found:
                found[1].proxy_path = proxy_path
                self.lbl_status.setText("Proxy ready — preview accelerated; export uses the original media")
                self.preview_canvas.refresh_frame()
            else:
                self.lbl_status.setText("Proxy generation failed" + (f": {error[-180:]}" if error else ""))

        def _release_proxy_worker(self, clip_id: str) -> None:
            worker = self._proxy_workers.pop(clip_id, None)
            if worker is not None:
                worker.deleteLater()

        def prepare_stabilization(self, clip_id: str) -> None:
            if not self._editor_built or clip_id in self._stabilization_workers:
                return
            found = self.controller.project.find_clip(clip_id)
            if not found:
                return
            _track, clip = found
            if not clip.source_path or not Path(clip.source_path).is_file():
                self.lbl_status.setText("Cannot stabilize: source media is missing")
                return
            from video_studio_stabilization import is_stabilization_ready, stabilization_cache_path

            cache_dir = get_app_data_dir(self.controller.custom_data_dir) / "stabilization"
            self.controller.project.stabilization_cache_dir = cache_dir
            cache_path = stabilization_cache_path(clip.source_path, cache_dir)
            if is_stabilization_ready(clip.source_path, cache_dir):
                self.lbl_status.setText("Stabilization cache ready")
                self.preview_canvas.refresh_frame()
                return
            worker = StabilizationWorkerThread(clip_id, clip.source_path, cache_path)
            worker.progress_changed.connect(self._on_stabilization_progress)
            worker.finished_result.connect(self._on_stabilization_finished)
            worker.finished.connect(lambda cid=clip_id: self._release_stabilization_worker(cid))
            self._stabilization_workers[clip_id] = worker
            _track_qt_worker(worker)
            self.lbl_status.setText("Analyzing camera movement for stabilization…")
            worker.start()

        def _on_stabilization_progress(self, clip_id: str, value: int) -> None:
            if self._closing or not hasattr(self, "lbl_status"):
                return
            self.lbl_status.setText(f"Stabilizing clip… {value}%")

        def _on_stabilization_finished(self, clip_id: str, ok: bool, detail: str) -> None:
            if self._closing:
                return
            found = self.controller.project.find_clip(clip_id)
            if ok and found and found[1].stabilize:
                self.lbl_status.setText("Video stabilization ready")
                self.preview_canvas.refresh_frame()
                self.timeline_widget.update()
            elif not ok and found and found[1].stabilize:
                self.lbl_status.setText("Stabilization analysis failed" + (f": {detail[-150:]}" if detail else ""))

        def _release_stabilization_worker(self, clip_id: str) -> None:
            worker = self._stabilization_workers.pop(clip_id, None)
            if worker is not None:
                worker.deleteLater()

        def cancel_stabilization(self, clip_id: str) -> None:
            worker = self._stabilization_workers.get(clip_id)
            if worker is not None and worker.isRunning():
                worker.requestInterruption()

        def handle_dropped_paths(self, paths: List[str]) -> None:
            lang = self.controller.lang
            if paths and not self._confirm_drop_recovery():
                return
            added, rejected = 0, []
            for p in paths:
                pp = Path(p)
                if pp.is_dir() or pp.suffix.lower() not in MEDIA_EXTS or not pp.exists():
                    rejected.append(pp.name or str(p))
                    continue
                try:
                    if self.controller.open_cli_file(p):
                        added += 1
                    else:
                        rejected.append(pp.name)
                except Exception:
                    rejected.append(pp.name)
            if added:
                self.show_editor()
                self.lbl_status.setText(tr("status_dropped", lang))
                self.refresh_all()
            if rejected:
                shown = "\n".join(rejected[:8]) + ("\n..." if len(rejected) > 8 else "")
                QMessageBox.warning(self, "HMZ", tr("drop_invalid_msg", lang, files=shown))

        def dragEnterEvent(self, event: Any) -> None:
            if event.mimeData().hasUrls() or event.mimeData().hasFormat(STICKER_MIME):
                event.acceptProposedAction()

        def dropEvent(self, event: Any) -> None:
            md = event.mimeData()
            if md.hasFormat(STICKER_MIME):
                try:
                    meta = json.loads(bytes(md.data(STICKER_MIME)).decode("utf-8"))
                except Exception:
                    meta = {}
                self.handle_timeline_drop([u.toLocalFile() for u in md.urls() if u.isLocalFile()], self.controller.project.playhead_sec, None, meta)
                event.acceptProposedAction()
                return
            self.handle_dropped_paths([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
            event.acceptProposedAction()

        def apply_language_and_theme(self) -> None:
            lang = self.controller.lang
            direction = Qt.LayoutDirection.RightToLeft if lang == "ar" else Qt.LayoutDirection.LeftToRight
            app = QApplication.instance()
            if app is not None:
                app.setLayoutDirection(direction)
                self._palette = apply_theme_to_app(
                    app, mode=self.controller.settings.data.get("theme", "dark"),
                    accent_key=self.controller.settings.data.get("accent", "cyan"),
                )
            self.setLayoutDirection(direction)
            self.setWindowTitle(tr("app_title", lang))
            self._retranslate_main_menu()
            self.home.apply_palette(self._palette)
            self.home.retranslate()
            if not self._editor_built:
                return
            self.timeline_widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.lbl_timecode.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            self.btn_home.setText(tr("btn_home", lang))
            self.btn_home.setToolTip(tr("btn_home_tip", lang))
            self.btn_new.setText(tr("new_project", lang))
            self.btn_open.setText(tr("open_project", lang))
            self.btn_save.setText(tr("save_project", lang))
            self.btn_import.setText(tr("import_media", lang))
            self.btn_menu.setText(tr("btn_menu", lang))
            self.btn_menu.setToolTip(tr("btn_menu_tip", lang))
            self.btn_export.setText(tr("btn_export", lang))
            self.browser_tabs.retranslate()
            self.inspector_tabs.retranslate()
            self._update_play_button()
            self.btn_stop.setText("⏹")
            self.btn_stop.setToolTip(tr("btn_stop", lang))
            self.btn_snapshot.setText(tr("btn_snapshot", lang))
            self.btn_snapshot.setToolTip(tr("snapshot_tip", lang))
            for btn, short, full in ((self.btn_split, "tb_split", "tool_split"), (self.btn_del_clip, "tb_delete", "tool_delete"),
                                     (self.btn_undo, "tb_undo", "tool_undo"), (self.btn_redo, "tb_redo", "tool_redo"),
                                     (self.btn_marker, "tb_marker", "tool_marker"), (self.btn_magnet, "tb_magnet", "tb_magnet_tip"),
                                     (self.btn_fit, "tb_fit", "tb_fit_tip"), (self.btn_add_vtrack, "tb_add_video", "tool_add_vtrack"),
                                     (self.btn_add_stracks, "tb_add_sticker", "tool_add_stickertrack"), (self.btn_add_ttrack, "tb_add_text", "tool_add_ttrack"),
                                     (self.btn_add_atrack, "tb_add_audio", "tool_add_atrack")):
                btn.setText(tr(short, lang))
                btn.setToolTip(tr(full, lang))
            self.chk_snap.setText(tr("tb_snap", lang))
            self.chk_snap.setToolTip(tr("tool_snap", lang))
            self.lbl_tracks.setText(tr("tb_tracks_label", lang))
            self.lbl_status.setText(tr("status_ready", lang))
            self.btn_cancel_task.setText(tr("btn_cancel_task", lang))
            self._refresh_license_badge()
            self.preview_canvas.refresh_frame()
            self.timeline_widget.invalidate()

        # ---- main menu (theme / accent / language / help) -------------------------------
        def _build_main_menu(self) -> QMenu:
            menu = QMenu(self)
            self.menu_theme = menu.addMenu("")
            self._theme_actions: Dict[str, QAction] = {}
            theme_group = QActionGroup(self)
            theme_group.setExclusive(True)
            for mode in ("dark", "light", "system"):
                act = QAction(self)
                act.setCheckable(True)
                theme_group.addAction(act)
                self.menu_theme.addAction(act)
                act.triggered.connect(lambda _checked=False, m=mode: self._set_theme(m))
                self._theme_actions[mode] = act
            self.menu_accent = menu.addMenu("")
            self._accent_actions: Dict[str, QAction] = {}
            accent_group = QActionGroup(self)
            accent_group.setExclusive(True)
            for key, meta in ACCENT_COLORS.items():
                act = QAction(self)
                act.setCheckable(True)
                swatch = QPixmap(14, 14)
                swatch.fill(QColor(meta["primary"]))
                act.setIcon(QIcon(swatch))
                accent_group.addAction(act)
                self.menu_accent.addAction(act)
                act.triggered.connect(lambda _checked=False, k=key: self._set_accent(k))
                self._accent_actions[key] = act
            self.act_lang = menu.addAction("")
            self.act_lang.triggered.connect(lambda _checked=False: self._on_toggle_language())
            menu.addSeparator()
            self.act_guide = menu.addAction("")
            self.act_guide.triggered.connect(lambda _checked=False: self._open_guide())
            self.act_license = menu.addAction("")
            self.act_license.triggered.connect(lambda _checked=False: self._open_license_dialog())
            self.act_store = menu.addAction("")
            self.act_store.triggered.connect(lambda _checked=False: self._open_store())
            self.act_about = menu.addAction("")
            self.act_about.triggered.connect(lambda _checked=False: self._open_about())
            return menu

        def _retranslate_main_menu(self) -> None:
            lang = self.controller.lang
            self.menu_theme.setTitle(tr("menu_theme", lang))
            self.menu_accent.setTitle(tr("menu_accent", lang))
            cur_theme = self.controller.settings.data.get("theme", "dark")
            for mode, key in (("dark", "theme_dark"), ("light", "theme_light"), ("system", "theme_system")):
                self._theme_actions[mode].setText(tr(key, lang))
                self._theme_actions[mode].setChecked(mode == cur_theme)
            cur_accent = self.controller.settings.data.get("accent", "cyan")
            for key, act in self._accent_actions.items():
                act.setText(tr(ACCENT_COLORS[key]["name_key"], lang))
                act.setChecked(key == cur_accent)
            self.act_lang.setText(f"{tr('menu_language', lang)}:  {tr('lang_toggle', lang)}")
            self.act_guide.setText(tr("btn_guide", lang))
            self.act_license.setText(tr("btn_license", lang))
            self.act_store.setText(tr("btn_more_apps", lang))
            self.act_about.setText(tr("btn_about", lang))

        def _set_theme(self, mode: str) -> None:
            self.controller.set_theme_and_accent(mode, str(self.controller.settings.data.get("accent", "cyan")))
            self.apply_language_and_theme()

        def _set_accent(self, key: str) -> None:
            self.controller.set_theme_and_accent(str(self.controller.settings.data.get("theme", "dark")), key)
            self.apply_language_and_theme()

        def _open_guide(self) -> None:
            GuideDialog(self.controller, self).exec()

        def _open_store(self) -> None:
            StoreDialog(self.controller, self).exec()

        def _open_about(self) -> None:
            AboutDialog(self.controller, self).exec()

        def _open_update_url(self, url: str) -> None:
            if url.lower().startswith("https://"):
                webbrowser.open(url)

        # ---- Home <-> Editor navigation ---------------------------------------------------
        def show_home(self) -> None:
            if self._editor_built and self._play_timer.isActive():
                self._toggle_playback()  # pause (keeps the playhead) before leaving the editor
            self._pending_recovery = self._pending_recovery and self.controller.autosave_path().exists()
            self.home.set_recovery(self._pending_recovery)
            self.home.set_session(self.controller.project.name if self._session_started else None)
            self.home.refresh()
            self._stack.setCurrentWidget(self.home)

        def show_editor(self) -> None:
            self._build_editor_ui()
            self._session_started = True
            self._stack.setCurrentWidget(self.editor_page)
            self.refresh_all()
            self.preview_canvas.refresh_frame()
            self.timeline_widget.update()

        def _confirm_drop_recovery(self) -> bool:
            """Starting something else would overwrite the crash-recovery copy: ask first. True = OK to go on."""
            if not self._pending_recovery:
                return True
            ans = QMessageBox.question(self, "HMZ", tr("home_recovery_overwrite", self.controller.lang))
            if ans != QMessageBox.StandardButton.Yes:
                return False
            self._pending_recovery = False
            self.home.set_recovery(False)
            return True

        def _home_new(self, aspect: str) -> None:
            if not self._confirm_drop_recovery() or not self._confirm_discard_changes():
                return
            self._new_project(aspect if aspect in ASPECT_RATIOS else "16:9")
            self.show_editor()

        def _home_open_dialog(self) -> None:
            if not self._confirm_drop_recovery():
                return
            if self._on_open_project():
                self.show_editor()

        def _home_import(self) -> None:
            if not self._confirm_drop_recovery():
                return
            if self._on_import_media():
                self.show_editor()

        def _open_recent(self, path: str) -> None:
            if not self._confirm_drop_recovery() or not self._confirm_discard_changes():
                return
            try:
                self.controller.open_project_file(path)
            except Exception as exc:  # corrupt / missing file: tell the user, drop it from the list, stay on Home
                QMessageBox.warning(self, "HMZ", tr("home_open_failed", self.controller.lang, err=str(exc)))
                self.controller.recents.remove(path)
                self.home.refresh()
                return
            self.controller.mark_saved()
            self.refresh_all()
            self.show_editor()

        def _on_recover(self) -> None:
            if self.controller.recover_project():
                self.controller.current_project_path = ""
                self._pending_recovery = False
                self.refresh_all()
                self.show_editor()
            else:
                self._pending_recovery = False
                self.home.set_recovery(False)

        def _on_discard_recovery(self) -> None:
            try:
                self.controller.autosave_path().unlink(missing_ok=True)
            except Exception:
                pass
            self._pending_recovery = False
            self.home.set_recovery(False)

        def _refresh_license_badge(self) -> None:
            if not self._editor_built:
                return
            lang = self.controller.lang
            if self.controller.license_mgr.is_activated():
                self.lbl_lic_badge.setText(f"★ {tr('pro_status_badge', lang)}")
            else:
                rem = self.controller.license_mgr.remaining_free_operations()
                self.lbl_lic_badge.setText(tr("trial_status_badge", lang, n=rem))

        def _on_toggle_language(self) -> None:
            self.controller.toggle_language()
            self.apply_language_and_theme()

        def _on_aspect_changed(self, ratio_str: str) -> None:
            if ratio_str in ASPECT_RATIOS:
                self.controller.project.aspect_ratio = ratio_str
                self.preview_canvas.refresh_frame()

        def _on_preview_quality_changed(self, idx: int) -> None:
            scales = [1.0, 0.5, 0.25]
            self.controller.preview_quality_scale = scales[idx] if 0 <= idx < len(scales) else 0.5
            self.preview_canvas.refresh_frame()

        def _on_audio_status(self, status: str) -> None:
            lang = self.controller.lang
            key = {"preparing": "audio_preparing", "unavailable": "audio_unavailable_hint", "none": "status_ready", "ready": "status_ready"}.get(status, "status_ready")
            if status == "unavailable":
                if self.controller.ffmpeg_path() is not None or self._audio_hint_shown:
                    return  # multimedia backend problem or hint already shown once per session
                self._audio_hint_shown = True
            self.lbl_status.setText(tr(key, lang))

        _audio_hint_shown = False

        def _update_play_button(self) -> None:
            lang = self.controller.lang
            playing = self._play_timer.isActive()
            self.btn_play.setText("⏸" if playing else "▶")
            self.btn_play.setToolTip(tr("btn_pause" if playing else "btn_play", lang))

        def _toggle_playback(self) -> None:
            if self._play_timer.isActive():
                self._play_timer.stop()
                if self.preview_audio is not None:
                    self.preview_audio.pause()
            else:
                self._play_start_sec = self.controller.project.playhead_sec
                self._play_t0 = time.perf_counter()
                self._play_timer.start()
                if self.preview_audio is not None:
                    self.preview_audio.play(self.controller.project.playhead_sec)
            self._update_play_button()

        _play_start_sec = 0.0
        _play_t0 = 0.0

        def _stop_playback(self) -> None:
            self._play_timer.stop()
            if self.preview_audio is not None:
                self.preview_audio.pause()
            self.controller.project.playhead_sec = 0.0
            self._update_play_button()
            self._on_playhead_changed(0.0)
            self.timeline_widget.update()

        def _on_playback_tick(self) -> None:
            """Playhead follows the wall clock, so playback speed is correct even when the machine cannot keep up
            (frames are skipped instead of the video running slow)."""
            p = self.controller.project
            elapsed = time.perf_counter() - self._play_t0
            p.playhead_sec = round(round((self._play_start_sec + elapsed) * p.fps) / p.fps, 3)
            if p.playhead_sec >= p.total_duration():
                p.playhead_sec = 0.0
                self._play_timer.stop()
                if self.preview_audio is not None:
                    self.preview_audio.pause()
                self._update_play_button()
            self._ticking = True
            try:
                self._on_playhead_changed(p.playhead_sec)
            finally:
                self._ticking = False
            self._tick_count += 1
            if self.preview_audio is not None and self._tick_count % 30 == 0 and self._play_timer.isActive():
                self.preview_audio.resync(p.playhead_sec)
            self.timeline_widget.ensure_visible(p.playhead_sec)
            self.timeline_widget.update()

        def _on_playhead_changed(self, sec: float) -> None:
            if not self._ticking and self._play_timer.isActive():
                self._play_start_sec, self._play_t0 = sec, time.perf_counter()  # user seeked while playing: continue from there
                if self.preview_audio is not None:
                    self.preview_audio.seek(sec)
            tc_cur = format_timecode_ltr(sec, self.controller.project.fps)
            tc_tot = format_timecode_ltr(self.controller.project.total_duration(), self.controller.project.fps)
            self.lbl_timecode.setText(f"{tc_cur} / {tc_tot}")
            self.preview_canvas.refresh_frame()

        def _on_snapshot(self) -> None:
            """Save the frame under the playhead as a full-resolution PNG next to the project (or in Pictures)."""
            import cv2

            lang = self.controller.lang
            proj = self.controller.project
            base = Path(self.controller.current_project_path).parent if self.controller.current_project_path else Path.home()
            default = str(base / f"frame_{proj.playhead_sec:.2f}s.png")
            path, _ = QFileDialog.getSaveFileName(self, tr("btn_snapshot", lang), default, "PNG (*.png)")
            if not path:
                return
            if not path.lower().endswith(".png"):
                path += ".png"
            try:
                w, h = proj.canvas_size
                frame = proj.render_composite_frame(proj.playhead_sec, preview_scale=1.0)
                ok, buf = cv2.imencode(".png", frame)
                if not ok:
                    raise ValueError("encode")
                Path(path).write_bytes(buf.tobytes())  # imwrite fails on non-ASCII Windows paths; this does not
            except Exception:
                QMessageBox.warning(self, "HMZ", tr("snapshot_failed", lang))
                return
            self.lbl_status.setText(tr("snapshot_saved", lang, path=path).replace("\n", " "))

        def close_track_gaps(self, track_id: Optional[str]) -> None:
            c = self.controller
            tid = track_id or self.timeline_widget.selected_track_id
            if not tid and c.selected_clip_id:
                found = c.project.find_clip(c.selected_clip_id)
                tid = found[0].id if found else ""
            if tid and c.project.close_gaps(tid):
                self.refresh_all()

        def handle_timeline_drop(self, paths: List[str], at: float, track_id: Optional[str], meta: Optional[Dict[str, Any]]) -> None:
            """Files / stickers dropped on the timeline or preview. Stickers (internal drag, GIFs, or PNG/WebP dropped on a
            sticker track) go to a sticker track at the drop time; other media is placed where it was dropped."""
            c = self.controller
            if not self._confirm_drop_recovery():
                return
            trk = c.project.find_track(track_id) if track_id else None
            on_sticker_lane = trk is not None and trk.track_type == "sticker"
            added = False
            cursor = at
            for p in paths:
                ext = Path(p).suffix.lower()
                try:
                    if meta is not None or ext == ".gif" or (ext in (".png", ".webp") and on_sticker_lane):
                        use = p
                        if meta is None or not meta.get("sticker_id"):
                            if Path(p).parent != c.my_stickers_dir():
                                imported = c.import_stickers([p])  # keep external stickers in "my stickers" too
                                use = imported[0] if imported else p
                        added |= c.add_sticker_to_timeline(use, at=at, track_id=track_id, meta=(meta or None) if meta and meta.get("sticker_id") else None)
                    elif ext in (".srt", ".hvsp"):
                        added |= c.open_cli_file(p)
                    elif Path(p).suffix.lower() in MEDIA_EXTS:
                        added |= c.add_media_to_timeline(p, at=cursor)
                        found = c.get_selected_clip()
                        if found is not None:
                            cursor = found.timeline_end
                except Exception:
                    continue
            if added:
                self.refresh_all()
                found = c.project.find_clip(c.selected_clip_id)
                if found is not None:
                    self.timeline_widget.ensure_track_visible(found[0].id)
                self.show_editor()

        # ------------------------------------------------------------------
        # Selection / clipboard / quick actions (shared by buttons, shortcuts and context menus)
        # ------------------------------------------------------------------
        def _on_clip_selected(self, cid: str) -> None:
            self.inspector_tabs.show_for_clip(cid) if cid else self.inspector_tabs.load_clip()
            self.browser_tabs.refresh_audio()
            self.timeline_widget.update()
            self.preview_canvas.update()

        def open_inspector_for(self, clip_id: str, focus_text: bool = False) -> None:
            self.controller.select_clip(clip_id)
            self.inspector_tabs.show_for_clip(clip_id, focus_text=focus_text)
            self.timeline_widget.update()
            self.preview_canvas.update()

        def _step_playhead(self, delta: float) -> None:
            p = self.controller.project
            p.playhead_sec = round(max(0.0, min(p.total_duration(), p.playhead_sec + delta)), 3)
            self._on_playhead_changed(p.playhead_sec)
            self.timeline_widget.ensure_visible(p.playhead_sec)
            self.timeline_widget.update()

        def select_all(self) -> None:
            ids = [c.id for t in self.controller.project.tracks for c in t.clips]
            self.controller.selected_ids = ids
            self.controller.selected_clip_id = ids[-1] if ids else None
            self.refresh_all()

        def select_track_clips(self, track_id: str) -> None:
            trk = self.controller.project.find_track(track_id)
            if trk is not None:
                ids = [c.id for c in trk.clips]
                self.controller.selected_ids = ids
                self.controller.selected_clip_id = ids[-1] if ids else None
                self.refresh_all()

        def _selected_or_none(self) -> List[TimelineClip]:
            return self.controller.selected_clips()

        def split_at_playhead(self) -> None:
            c = self.controller
            targets = self._selected_or_none()
            with c.project.undo_group():
                for clip in targets:
                    c.project.split_clip_at(clip.id)
            self.refresh_all()

        def _on_split_clip(self) -> None:
            self.split_at_playhead()

        def trim_to_playhead(self, clip_id: str, side: str) -> None:
            p = self.controller.project
            p.push_undo_snapshot()
            p.trim_clip(clip_id, new_start=p.playhead_sec) if side == "start" else p.trim_clip(clip_id, new_end=p.playhead_sec)
            self.refresh_all()

        def copy_selected(self) -> None:
            import copy as _copy

            self.controller.clipboard = [_copy.deepcopy(cl) for cl in self._selected_or_none()]

        def cut_selected(self) -> None:
            self.copy_selected()
            self.delete_selected()

        def paste_clipboard(self, track_id: Optional[str], at: float) -> None:
            c = self.controller
            if not c.clipboard:
                return
            first = min(cl.timeline_start for cl in c.clipboard)
            new_ids: List[str] = []
            with c.project.undo_group():
                for cl in c.clipboard:
                    new = c.project.paste_clip(cl, track_id if len(c.clipboard) == 1 else None, at + (cl.timeline_start - first))
                    if new is not None:
                        new_ids.append(new.id)
            if new_ids:
                c.selected_ids = new_ids
                c.selected_clip_id = new_ids[-1]
            self.refresh_all()

        def duplicate_selected(self) -> None:
            c = self.controller
            new_ids: List[str] = []
            with c.project.undo_group():
                for clip in self._selected_or_none():
                    d = c.project.duplicate_clip(clip.id)
                    if d is not None:
                        new_ids.append(d.id)
            if new_ids:
                c.selected_ids = new_ids
                c.selected_clip_id = new_ids[-1]
            self.refresh_all()

        def delete_selected(self) -> None:
            c = self.controller
            with c.project.undo_group():
                for clip in self._selected_or_none():
                    c.project.delete_clip(clip.id)
            c.select_clip(None)
            self.refresh_all()

        def ripple_delete_selected(self) -> None:
            c = self.controller
            with c.project.undo_group():
                for clip in sorted(self._selected_or_none(), key=lambda x: -x.timeline_start):
                    c.project.ripple_delete_clip(clip.id)
            c.select_clip(None)
            self.refresh_all()

        def _on_delete_clip(self) -> None:
            self.delete_selected()

        def set_speed_selected(self, speed: float) -> None:
            c = self.controller
            with c.project.undo_group():
                for clip in self._selected_or_none():
                    c.project.set_clip_speed(clip.id, speed)
            self.refresh_all()

        def toggle_clip_flag(self, attr: str) -> None:
            c = self.controller
            with c.project.undo_group():
                for clip in self._selected_or_none():
                    setattr(clip, attr, not getattr(clip, attr))
            self.refresh_all()

        def set_clip_value(self, attr: str, value: Any) -> None:
            c = self.controller
            with c.project.undo_group():
                for clip in self._selected_or_none():
                    setattr(clip, attr, value)
            self.refresh_all()

        def reset_transform_selected(self) -> None:
            c = self.controller
            with c.project.undo_group():
                for clip in self._selected_or_none():
                    clip.pos_x = clip.pos_y = clip.rotation = 0.0
                    clip.scale = clip.opacity = 100.0
            self.refresh_all()

        def freeze_selected(self) -> None:
            clip = self.controller.get_selected_clip()
            if clip is not None:
                self.controller.project.freeze_frame_at(clip.id)
                self.refresh_all()

        def detach_selected(self) -> None:
            clip = self.controller.get_selected_clip()
            if clip is not None:
                self.controller.project.detach_audio_from_clip(clip.id)
                self.refresh_all()

        def set_track_flag(self, track_id: str, flag: str, value: bool) -> None:
            self.controller.project.set_track_flag(track_id, flag, value)
            self.refresh_all()

        def add_marker_at(self, t: float) -> None:
            p = self.controller.project
            p.markers.append(TimelineMarker(time_sec=round(t, 3), label=f"M {len(p.markers) + 1}"))
            self.timeline_widget.update()

        def remove_marker(self, marker_id: str) -> None:
            p = self.controller.project
            p.markers = [m for m in p.markers if m.id != marker_id]
            self.timeline_widget.update()

        def clear_markers(self) -> None:
            self.controller.project.clear_markers()
            self.timeline_widget.update()

        def add_text_at(self, t: float) -> None:
            self.browser_tabs._add_text("default", start=t)

        def _on_undo(self) -> None:
            if self.controller.project.undo():
                self.refresh_all()

        def _on_redo(self) -> None:
            if self.controller.project.redo():
                self.refresh_all()

        def _on_add_marker(self) -> None:
            t = self.controller.project.playhead_sec
            self.add_marker_at(t)

        def _on_add_track(self, track_type: str) -> None:
            trk = self.controller.project.add_track(track_type)
            self.timeline_widget.selected_track_id = trk.id
            self.timeline_widget.invalidate()

        def _new_project(self, aspect: str = "16:9") -> None:
            lang = self.controller.lang
            self.controller.project = VideoStudioProject(name=tr("new_project_default_name", lang), aspect_ratio=aspect)
            self.controller.project.stabilization_cache_dir = get_app_data_dir(self.controller.custom_data_dir) / "stabilization"
            self.controller.media_bin = []
            self.controller._seed_demo_timeline()
            self.controller.current_project_path = ""
            self.controller.mark_saved()
            self.refresh_all()

        def _on_new_project(self) -> None:
            if not self._confirm_discard_changes():
                return
            self._new_project("16:9")

        def _on_open_project(self) -> bool:
            path, _ = QFileDialog.getOpenFileName(self, tr("open_project", self.controller.lang), "", "HMZ Project (*.hvsp)")
            if not path or not self._confirm_discard_changes():
                return False
            try:
                self.controller.open_project_file(path)
            except Exception as exc:
                QMessageBox.warning(self, "HMZ", tr("home_open_failed", self.controller.lang, err=str(exc)))
                self.controller.recents.remove(path)
                return False
            self.controller.mark_saved()
            self.refresh_all()
            return True

        def _on_save_project(self, save_as: bool = False) -> bool:
            """Ctrl+S saves straight to the project's file once it has one; Save As (or the first save) asks for a name."""
            path = self.controller.current_project_path
            if save_as or not path or not Path(path).parent.exists():
                last = path or str(self.controller.settings.data.get("last_project_path", "")) or "project.hvsp"
                path, _ = QFileDialog.getSaveFileName(self, tr("save_project", self.controller.lang), last, "HMZ Project (*.hvsp)")
                if not path:
                    return False
                if not path.lower().endswith(".hvsp"):
                    path += ".hvsp"
            try:
                self.controller.project.save_project_file(path)
            except OSError as exc:
                QMessageBox.warning(self, tr("save_failed_title", self.controller.lang), tr("save_failed_msg", self.controller.lang, err=str(exc)))
                return False
            self.controller.current_project_path = str(Path(path).resolve())
            self.controller.settings.data["last_project_path"] = self.controller.current_project_path
            self.controller.settings.save()
            self.controller.recents.record(self.controller.current_project_path, self.controller.project)
            self.controller.mark_saved()
            self.lbl_status.setText(tr("status_saved", self.controller.lang))
            return True

        def _confirm_discard_changes(self) -> bool:
            """True if it is OK to replace/close the current project (saved, or the user chose to discard)."""
            if not self.controller.is_dirty():
                return True
            lang = self.controller.lang
            box = QMessageBox(self)
            box.setWindowTitle("HMZ")
            box.setText(tr("unsaved_changes_msg", lang))
            b_save = box.addButton(tr("save_project", lang), QMessageBox.ButtonRole.AcceptRole)
            b_discard = box.addButton(tr("btn_discard", lang), QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(tr("ff_btn_cancel", lang), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is b_save:
                return self._on_save_project()
            return clicked is b_discard

        def _maybe_offer_recovery(self) -> None:
            if not self.controller.has_recovery():
                return
            lang = self.controller.lang
            ans = QMessageBox.question(self, "HMZ", tr("recover_msg", lang))
            if ans == QMessageBox.StandardButton.Yes and self.controller.recover_project():
                self.refresh_all()
            else:
                try:
                    self.controller.autosave_path().unlink(missing_ok=True)
                except Exception:
                    pass

        def _on_import_media(self) -> bool:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                tr("import_media", self.controller.lang),
                "",
                "Media Files (*.mp4 *.mov *.mkv *.avi *.webm *.mp3 *.wav *.m4a *.aac *.ogg *.flac *.png *.jpg *.jpeg *.webp *.bmp *.gif *.srt)",
            )
            for p in paths:
                self.controller.open_cli_file(p)
            self.refresh_all()
            return bool(paths)

        def _on_export_clicked(self) -> None:
            lang = self.controller.lang
            if self.controller.integrity_status in ("mismatch", "bad_signature"):
                QMessageBox.warning(self, "HMZ", tr("lic_msg_integrity", lang))
                return
            if not self.controller.license_mgr.can_perform_paid_operation():
                QMessageBox.warning(
                    self,
                    tr("lic_exhausted_title", lang),
                    tr("lic_exhausted_body", lang, max=FREE_OPERATIONS),
                )
                self._open_license_dialog()
                return

            # Do not silently export an unstabilized result while a selected clip
            # still has pending analysis. Kick off missing analyses and ask for retry.
            try:
                from video_studio_stabilization import is_stabilization_ready
                pending_stabilization = []
                for track in self.controller.project.tracks:
                    for clip in track.clips:
                        if clip.clip_type == "video" and clip.stabilize and clip.source_path and Path(clip.source_path).is_file():
                            cache_dir = self.controller.project.stabilization_cache_dir or (get_app_data_dir(self.controller.custom_data_dir) / "stabilization")
                            if not is_stabilization_ready(clip.source_path, cache_dir):
                                pending_stabilization.append(clip.id)
                if pending_stabilization:
                    for clip_id in pending_stabilization:
                        self.prepare_stabilization(clip_id)
                    QMessageBox.information(
                        self, "HMZ",
                        "يتم الآن تحليل اهتزاز المقاطع المحددة في الخلفية. أعد التصدير بعد ظهور رسالة اكتمال التثبيت.\n\n"
                        "Stabilization analysis is running in the background. Retry export when it completes.",
                    )
                    return
            except Exception as exc:
                write_crash_log(type(exc), exc, exc.__traceback__)
                QMessageBox.warning(self, "HMZ", "تعذر التحقق من حالة تثبيت الفيديو. راجع سجل الأخطاء.")
                return

            dlg = ExportDialog(self.controller, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            out_path = dlg.txt_path.text().strip()
            if not out_path:
                return
            ext = Path(out_path).suffix.lower()
            res_label = dlg.cmb_res.currentText()
            fps_val = int(dlg.cmb_fps.currentText())
            quality = str(dlg.cmb_quality.currentData() or "balanced")
            use_gpu = dlg.chk_gpu.isChecked()
            st = self.controller.settings.data
            st["export_quality"], st["export_use_gpu"] = quality, use_gpu
            self.controller.settings.save()

            ffmpeg = self.controller.ffmpeg_path()
            if ffmpeg is None and ext != ".gif":
                needs_ffmpeg = ext in (".wav", ".mp3") or project_has_audio(self.controller.project, None)
                if needs_ffmpeg:
                    fd = FfmpegDialog(self.controller, "audio_only" if ext in (".wav", ".mp3") else "export", self)
                    fd.exec()
                    if fd.action == "cancel":
                        return
                    if fd.action == "installed":
                        ffmpeg = self.controller.ffmpeg_path()
                    elif ext in (".wav", ".mp3"):
                        return
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            self.btn_cancel_task.setVisible(True)
            self.lbl_status.setText(tr("status_rendering", lang))
            self._export_worker = ExportWorkerThread(self.controller.project, out_path, res_label, fps_val, quality, use_gpu, ffmpeg)
            _track_qt_worker(self._export_worker)
            self._export_worker.progress_changed.connect(self.progress_bar.setValue)
            self._export_worker.export_finished.connect(self._on_export_finished)
            self._export_worker.start()

        def _cancel_running_task(self) -> None:
            if self._export_worker is not None and self._export_worker.isRunning():
                self._export_worker.request_cancel()

        def _on_export_finished(self, ok: bool, path: str) -> None:
            lang = self.controller.lang
            self.progress_bar.setVisible(False)
            self.btn_cancel_task.setVisible(False)
            self.lbl_status.setText(tr("status_ready", lang))
            worker = self._export_worker
            info = dict(getattr(worker, "info", {}) or {})
            cancelled = bool(worker is not None and worker._cancelled)
            if ok:
                self.controller.license_mgr.consume_operation()
                self._refresh_license_badge()
                msg = tr("export_success_msg", lang, path=path)
                msg += "\n\n" + tr({"mixed": "export_audio_mixed", "skipped_no_ffmpeg": "export_audio_skipped"}.get(info.get("audio", "none"), "export_audio_none"), lang)
                QMessageBox.information(self, "HMZ", msg)
            elif cancelled:
                QMessageBox.information(self, "HMZ", tr("export_cancelled_msg", lang))
            else:
                err = str(info.get("error", "")) or "unknown"
                if err == "ffmpeg_required":
                    QMessageBox.warning(self, "HMZ", tr("ff_body_audio_only", lang))
                elif err == "no_audio":
                    QMessageBox.warning(self, "HMZ", tr("export_no_audio_msg", lang))
                else:
                    QMessageBox.warning(self, "HMZ", tr("export_fail_msg", lang, err=err[-600:]))

        def _maybe_prompt_ffmpeg(self) -> None:
            """Once at startup: tell the user FFmpeg is needed to mix audio into exported videos."""
            if self.controller.ffmpeg_path() is not None or self.controller.settings.data.get("ffmpeg_never_ask_startup"):
                return
            FfmpegDialog(self.controller, "startup", self).exec()

        def _open_license_dialog(self) -> None:
            if self.controller.integrity_status in ("mismatch", "bad_signature"):
                QMessageBox.warning(self, "HMZ", tr("lic_msg_integrity", self.controller.lang))
                return
            LicenseDialog(self.controller, self).exec()
            self._refresh_license_badge()

        def _on_integrity_done(self, status: str, problems: list) -> None:
            self.controller.integrity_status = status
            if status in ("mismatch", "bad_signature"):
                self.lbl_status.setText("⚠ " + tr("lic_msg_integrity", self.controller.lang))

        def _start_background_update_check(self) -> None:
            url = self.controller.settings.data.get("update_url", DEFAULT_UPDATE_URL)
            if getattr(self, "_net_worker", None) is not None and self._net_worker.isRunning():
                return
            self._net_worker = NetworkCheckWorkerThread(url, get_app_data_dir(self.controller.custom_data_dir), self.controller.license_mgr)
            _track_qt_worker(self._net_worker)
            self._net_worker.update_fetched.connect(self._on_update_json_received)
            self._net_worker.start()

        def _maybe_reverify_license(self) -> None:
            """Re-verify the stored license every REVERIFY_DAYS (network call runs off the UI thread)."""
            mgr = self.controller.license_mgr
            if not mgr.state.get("activated") or not mgr.state.get("license_key"):
                return
            try:
                last = datetime.date.fromisoformat(mgr.state.get("last_verified_iso") or "1970-01-01")
            except ValueError:
                last = datetime.date(1970, 1, 1)
            if (datetime.date.today() - last).days < REVERIFY_DAYS:
                return
            if getattr(self, "_reverify_worker", None) is not None and self._reverify_worker.isRunning():
                return
            self._reverify_worker = ReverifyWorkerThread(mgr)
            _track_qt_worker(self._reverify_worker)
            self._reverify_worker.done.connect(self._on_reverify_done)
            self._reverify_worker.start()

        def _on_reverify_done(self, status: str) -> None:
            self._refresh_license_badge()
            if status in ("invalid", "disabled", "expired", "device"):
                QMessageBox.warning(self, "HMZ", tr(license_message_key(status), self.controller.lang))

        def _on_update_json_received(self, data: Dict[str, Any]) -> None:
            mgr = self.controller.license_mgr
            was_active = mgr.state.get("activated", False)
            mgr.apply_update_json(data)
            if was_active and not mgr.state.get("activated", False):
                QMessageBox.warning(self, "HMZ", tr("lic_revoked_notice", self.controller.lang))
            self._refresh_license_badge()
            release = mgr.get_verified_release()  # None unless update_sig verifies -> unsigned data never shows a prompt
            if not release:
                return
            remote_ver = str(release.get("version", ""))
            if not remote_ver or not is_newer_version(remote_ver, APP_VERSION):
                return
            if self.controller.settings.data.get("skipped_update") == remote_ver:
                return
            lang = self.controller.lang
            dl_url = str(release.get("url", ""))
            if not dl_url.lower().startswith("https://"):
                return
            self.home.set_update(remote_ver, dl_url)
            if self._stack.currentWidget() is self.home:
                return  # the Home banner is enough; don't pop a dialog over the start screen
            sha = str(release.get("sha256", ""))
            notes = str(release.get("notes", ""))
            if sha:
                notes += f"\nSHA-256: {sha}"
            box = QMessageBox(self)
            box.setWindowTitle(tr("update_available_title", lang))
            box.setText(tr("update_available_body", lang, ver=remote_ver, notes=notes))
            btn_open = box.addButton(tr("update_open_btn", lang), QMessageBox.ButtonRole.AcceptRole)
            btn_skip = box.addButton(tr("update_skip_btn", lang), QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is btn_open:
                webbrowser.open(dl_url)
            elif box.clickedButton() is btn_skip:
                self.controller.settings.data["skipped_update"] = remote_ver
                self.controller.settings.save()

        def closeEvent(self, event: Any) -> None:
            if not self._confirm_discard_changes():
                event.ignore()
                return
            self._closing = True
            active_workers = list({worker for worker in _LIVE_QT_WORKERS if worker.isRunning()})
            if self._export_worker is not None and self._export_worker.isRunning():
                self._export_worker.request_cancel()
                active_workers.append(self._export_worker)
            for worker in active_workers:
                if not worker.isRunning():
                    continue
                cancel = getattr(worker, "request_cancel", None) or getattr(worker, "cancel", None)
                if callable(cancel):
                    try:
                        cancel()
                    except Exception:
                        pass
                if hasattr(worker, "requestInterruption"):
                    worker.requestInterruption()
            deadline = time.monotonic() + 7.0
            still_running = []
            for worker in active_workers:
                if not worker.isRunning():
                    continue
                remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                if remaining_ms <= 0 or not worker.wait(remaining_ms):
                    still_running.append(worker)
            # All workers in this list have either stopped or will be kept in the
            # global registry; release completed wrappers before destroying the UI.
            for worker in active_workers:
                if not worker.isRunning():
                    _LIVE_QT_WORKERS.discard(worker)
            if still_running:
                self._closing = False
                QMessageBox.warning(
                    self, "HMZ",
                    "ما زالت هناك مهمة وسائط تعمل في الخلفية. أُرسل إليها طلب إيقاف آمن؛ أغلق البرنامج مرة أخرى بعد انتهائها.\n\n"
                    "A background media task is still stopping. The app will remain open to avoid destroying a running worker.",
                )
                event.ignore()
                return
            self.controller.mark_saved()  # clean exit: no stale recovery copy
            if self.preview_audio is not None:
                self.preview_audio.shutdown()
            if self._editor_built and self.preview_canvas is not None:
                self.preview_canvas.shutdown()
            self.controller.settings.data["window_width"] = self.width()
            self.controller.settings.data["window_height"] = self.height()
            self.controller.settings.data["geometry"] = bytes(self.saveGeometry().toBase64()).decode("ascii")
            self.controller.settings.save()
            super().closeEvent(event)


def run_selftest(out_path: Optional[str]) -> int:
    """Build-time smoke test (run against the compiled EXE). Writes PASS/FAIL lines to a file because
    the GUI build has no console. Exit code 0 only if every check passes."""
    lines: List[str] = []
    ok_all = True

    def check(name: str, fn: Any) -> None:
        nonlocal ok_all
        try:
            fn()
            lines.append(f"PASS {name}")
        except Exception as exc:  # report every failure, not just the first
            ok_all = False
            lines.append(f"FAIL {name}: {type(exc).__name__}: {exc}")

    def t_modules() -> None:
        import importlib
        # asyncio is imported lazily by huggingface_hub/faster-whisper; keep it in Nuitka builds.
        import asyncio  # noqa: F401
        for m in ("cv2", "numpy", "PIL", "cryptography.hazmat.primitives.asymmetric.ed25519", "arabic_reshaper", "bidi", "video_studio_core", "video_studio_text",
                  "video_studio_timeline", "video_studio_textpanel", "video_studio_panels", "video_studio_license",
                  "video_studio_update", "video_studio_integrity", "video_studio_store", "video_studio_guide", "video_studio_guide_more", "video_studio_ffmpeg", "video_studio_plugins", "video_studio_stickers", "video_studio_audio", "video_studio_record", "video_studio_recent", "video_studio_home", "video_studio_stabilization"):
            importlib.import_module(m)

    def t_ai_dependencies() -> None:
        # Only required for the dedicated AI build; normal builds intentionally omit these.
        if "--require-ai" not in sys.argv:
            return
        import faster_whisper  # noqa: F401
        import ctranslate2  # noqa: F401
        import onnxruntime  # noqa: F401

    def t_render() -> None:
        import numpy as np
        proj = VideoStudioProject(name="selftest", aspect_ratio="16:9", fps=30)
        frame = proj.render_composite_frame(0.0, 0.25)
        assert isinstance(frame, np.ndarray) and frame.ndim == 3

    def t_text() -> None:
        from video_studio_text import render_text_layer
        ts = TextStyleSettings(text="اختبار Test", shadow_enabled=True, stroke_width=2, reflection_enabled=True)
        bgr, alpha = render_text_layer(ts, 320, 180)
        assert alpha.max() > 0

    def t_stickers() -> None:
        from video_studio_stickers import STICKERS, render_frame
        im = render_frame(next(iter(STICKERS)), 0.3, "#FFD60A")
        assert im.size[0] > 8

    def t_dsp() -> None:
        import numpy as np
        from video_studio_plugins import denoise_audio, detect_beats
        x = (np.random.default_rng(0).normal(0, 0.02, 44100 * 2)).astype("float32")
        assert len(denoise_audio(x, 44100)) == len(x)
        detect_beats(x[:22050], 22050)

    def t_multimedia() -> None:
        # WARN-only: playback/recording will not work without it, but editing and export still do
        try:
            from PyQt6.QtMultimedia import QAudioSource, QMediaPlayer  # noqa: F401
        except Exception as exc:
            lines.append(f"WARN multimedia: {type(exc).__name__}: {exc}")

    def t_i18n() -> None:
        assert tr("app_title", "ar") and tr("app_title", "en")

    def t_guide() -> None:
        assert len(get_guide_sections()) >= 10

    def t_license() -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            mgr = LicenseManager(custom_storage_dir=Path(d))
            assert mgr.remaining_free_operations() >= 0

    def t_data_dir() -> None:
        d = get_app_data_dir()
        probe = d / ".selftest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()

    def t_qt() -> None:
        if not HAS_PYQT6:
            raise RuntimeError("PyQt6 missing in build")
        if not sys.platform.startswith("win"):  # on Windows use the real platform plugin that the EXE ships
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = QApplication.instance() or QApplication(sys.argv[:1])
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            controller = StudioAppController(custom_data_dir=Path(d))
            apply_theme_to_app(app, "dark", "cyan")
            win = VideoStudioMainWindow(controller)
            win.refresh_all()
            win.close()

    for name, fn in (("modules", t_modules), ("ai-dependencies", t_ai_dependencies), ("render", t_render), ("text", t_text), ("i18n", t_i18n), ("stickers", t_stickers), ("dsp", t_dsp), ("multimedia", t_multimedia), ("guide", t_guide),
                     ("license", t_license), ("appdata", t_data_dir), ("qt-window", t_qt)):
        check(name, fn)
    lines.append("RESULT " + ("PASS" if ok_all else "FAIL"))
    text = "\n".join(lines) + "\n"
    if out_path:
        try:
            Path(out_path).write_text(text, encoding="utf-8")
        except Exception:
            ok_all = False
    else:
        print(text)
    return 0 if ok_all else 1


def make_splash(pal: Dict[str, str], lang: str) -> Any:
    """Tiny painted splash shown while the editor window is being built (perceived start-up speed). Never raises."""
    try:
        from PyQt6.QtGui import QFont, QLinearGradient

        w, h = 460, 250
        pm = QPixmap(w, h)
        pm.fill(QColor(pal["window_bg"]))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(pal["border_focus"]), 1))
        p.drawRoundedRect(0, 0, w - 1, h - 1, 14, 14)
        grad = QLinearGradient(0, 0, 80, 80)
        grad.setColorAt(0.0, QColor(pal["accent"]))
        grad.setColorAt(1.0, QColor(pal["accent_pressed"]))
        path = QPainterPath()
        path.addRoundedRect(QRectF(w / 2 - 36, 46, 72, 72), 20, 20)
        p.fillPath(path, grad)
        tri = QPainterPath()
        tri.moveTo(w / 2 - 10, 66)
        tri.lineTo(w / 2 + 20, 82)
        tri.lineTo(w / 2 - 10, 98)
        tri.closeSubpath()
        p.fillPath(tri, QColor(pal["text_on_accent"]))
        p.setPen(QColor(pal["text_main"]))
        f = QFont("Segoe UI", 15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 134, w, 30), Qt.AlignmentFlag.AlignCenter, "HMZ Video Studio Pro")
        p.setPen(QColor(pal["text_muted"]))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRectF(0, 172, w, 24), Qt.AlignmentFlag.AlignCenter, tr("splash_loading", lang))
        p.drawText(QRectF(0, 208, w, 20), Qt.AlignmentFlag.AlignCenter, f"v{APP_VERSION}")
        p.end()
        splash = QSplashScreen(pm, Qt.WindowType.WindowStaysOnTopHint)
        splash.show()
        QApplication.processEvents()
        return splash
    except Exception:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--selftest" in args:
        out = None
        if "--selftest-out" in args:
            i = args.index("--selftest-out")
            out = args[i + 1] if i + 1 < len(args) else None
        return run_selftest(out)
    if "--remove-integrations" in args:
        return handle_remove_integrations()

    install_exception_hooks()
    files = [a for a in args if not a.startswith("-")]

    if not HAS_PYQT6:
        controller = StudioAppController()
        for arg in files:
            controller.open_cli_file(arg)
        return 0

    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # one consistent, fully style-sheet-able look on every Windows version

    # Single instance: forward file arguments to the running instance and exit.
    sock = QLocalSocket()
    sock.connectToServer(SINGLE_INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write("\n".join(os.path.abspath(f) for f in files).encode("utf-8") or b"\n")
        sock.flush()
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        return 0

    controller = StudioAppController()
    opened_files = False
    for arg in files:
        try:
            opened_files = controller.open_cli_file(arg) or opened_files
        except Exception:
            pass  # a broken file passed on the command line must not stop the app from starting
    pal = apply_theme_to_app(app, controller.settings.data.get("theme", "dark"), controller.settings.data.get("accent", "cyan"))
    splash = make_splash(pal, controller.lang)
    win = VideoStudioMainWindow(controller, start_home=not opened_files)

    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
    server = QLocalServer()
    server.listen(SINGLE_INSTANCE_KEY)

    def _on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        conn.waitForReadyRead(500)
        paths = [p for p in bytes(conn.readAll()).decode("utf-8", errors="ignore").splitlines() if p.strip()]
        win.handle_dropped_paths(paths)
        win.showNormal()
        win.raise_()
        win.activateWindow()

    server.newConnection.connect(_on_new_connection)
    win.show()
    win.refresh_all()
    if splash is not None:
        splash.finish(win)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
