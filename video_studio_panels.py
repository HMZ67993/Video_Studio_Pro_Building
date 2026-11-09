# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Browser (7 sections) and Inspector (6 tabs) panels.
Every visible string comes from video_studio_i18n (no hardcoded UI text).
Requires PyQt6; imported lazily by video_studio.py only when PyQt6 is available.
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import datetime

import json

from PyQt6.QtCore import QMimeData, QSize, Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QIcon, QImage, QPixmap, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QStackedWidget,
    QToolButton,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QDoubleSpinBox,
    QFileDialog,
    QDialog,
    QDialogButtonBox,
    QMenu,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QInputDialog,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from video_studio_core import (
    ANIM_IN_KEYS,
    ANIM_LOOP_KEYS,
    ANIM_OUT_KEYS,
    EQUALIZER_PRESETS,
    SPEED_CURVE_PRESETS,
    Keyframe,
    TextStyleSettings,
    TimelineClip,
    interpolate_keyframes,
    export_clips_to_srt,
    export_clips_to_vtt,
    parse_srt_content,
)
from video_studio_i18n import tr
from video_studio_stickers import COLORS as STICKER_COLORS, STICKERS, render_frame, sticker_display_name, sticker_file
from video_studio_timeline import STICKER_MIME
from video_studio_textpanel import TextEditorPanel

MEDIA_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".srt", ".hvsp")

EFFECTS: List[Tuple[str, str]] = [
    ("none", "effect_none"),
    ("warm_film", "effect_warm_film"),
    ("cyber_teal", "effect_cyber_teal"),
    ("vintage_bw", "effect_vintage_bw"),
    ("vhs_glitch", "effect_vhs_glitch"),
    ("motion_blur", "effect_motion_blur"),
    ("camera_shake", "effect_camera_shake"),
    ("vignette", "effect_vignette"), ("gaussian_blur", "effect_gaussian_blur"), ("pixelate", "effect_pixelate"),
    ("invert", "effect_invert"), ("sepia", "effect_sepia"), ("negative_film", "effect_negative_film"),
]
TRANSITIONS: List[Tuple[str, str]] = [
    ("none", "trans_none"),
    ("crossfade", "trans_crossfade"),
    ("fade_black", "trans_fade_black"),
    ("wipe_left", "trans_wipe_left"),
    ("slide", "trans_slide"),
    ("zoom_in", "trans_zoom_in"), ("wipe_right", "trans_wipe_right"), ("wipe_up", "trans_wipe_up"),
    ("wipe_down", "trans_wipe_down"), ("circle_reveal", "trans_circle"), ("diamond", "trans_diamond"),
    ("blinds", "trans_blinds"), ("checkerboard", "trans_checkerboard"), ("push_left", "trans_push_left"),
    ("push_right", "trans_push_right"), ("push_up", "trans_push_up"), ("push_down", "trans_push_down"),
    ("rotate_in", "trans_rotate"), ("blur_in", "trans_blur"), ("flash", "trans_flash"),
]
MASKS: List[Tuple[str, str]] = [("none", "mask_none"), ("rect", "mask_rect"), ("circle", "mask_circle"), ("linear", "mask_linear")]
CURVES: List[Tuple[str, str]] = [(k, f"curve_{k}") for k in SPEED_CURVE_PRESETS]
EQS: List[Tuple[str, str]] = [(k, f"eq_{k}") for k in EQUALIZER_PRESETS]
BLENDS: List[Tuple[str, str]] = [("normal", "blend_normal"), ("multiply", "blend_multiply"), ("screen", "blend_screen"), ("overlay", "blend_overlay")]
EASINGS: List[Tuple[str, str]] = [("linear", "ease_linear"), ("ease_in", "ease_in"), ("ease_out", "ease_out"), ("ease_in_out", "ease_in_out")]
KF_PROPS: List[Tuple[str, str]] = [
    ("pos_x", "lbl_pos_x"), ("pos_y", "lbl_pos_y"), ("scale", "lbl_scale"), ("rotation", "lbl_rotation"), ("opacity", "lbl_opacity"),
    ("volume_db", "lbl_volume"), ("color.brightness", "lbl_brightness"), ("color.contrast", "lbl_contrast"),
    ("color.saturation", "lbl_saturation"), ("color.temperature", "lbl_temperature"), ("color.tint", "lbl_tint"),
    ("color.sharpness", "lbl_sharpness"), ("effect_intensity", "lbl_effect_intensity"),
]


def _fill_combo(combo: QComboBox, items: List[Tuple[str, str]], lang: str) -> None:
    """(Re)fill a combo with translated labels, keeping the selected data key."""
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    for data_key, tr_key in items:
        combo.addItem(tr(tr_key, lang), data_key)
    idx = combo.findData(current) if current is not None else 0
    combo.setCurrentIndex(max(0, idx))
    combo.blockSignals(False)


class _MediaList(QListWidget):
    """List that accepts file drops and forwards them to a callback."""

    def __init__(self, on_paths: Callable[[List[str]], None]):
        super().__init__()
        self._on_paths = on_paths
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._on_paths(paths)
            event.acceptProposedAction()


class AIJobThread(QThread):
    """Runs the heavy part of an AI tool (or a model download) off the UI thread."""

    progress = pyqtSignal(int)
    finished_result = pyqtSignal(str, str, dict)

    def __init__(self, plugin: Any, mode: str, clip: Any, params: Dict[str, Any]):
        super().__init__()
        self.plugin = plugin
        self.mode = mode
        self.clip = clip
        self.params = params
        self.cancel_flag = False

    def cancel(self) -> None:
        self.cancel_flag = True
        self.requestInterruption()

    def run(self) -> None:
        from video_studio_plugins import AIError

        pid = self.plugin.descriptor.plugin_id
        cancel = lambda: self.cancel_flag  # noqa: E731
        try:
            if self.mode in ("install", "install_run", "run"):
                ensure_runtime = getattr(self.plugin, "ensure_runtime", None)
                if callable(ensure_runtime):
                    ensure_runtime(lambda v: self.progress.emit(int(v * (0.35 if self.mode == "install_run" else 0.5))), cancel)
            if self.mode in ("install", "install_run"):
                self.plugin.install_model(lambda v: self.progress.emit(int((35 + v * 0.65) if self.mode == "install_run" else v)), cancel)
                if self.mode == "install":
                    self.finished_result.emit(pid, "install", {"ok": True})
                    return
            base = 50 if self.mode == "install_run" else 0
            res = self.plugin.analyze(self.clip, self.params, lambda v: self.progress.emit(base + int(v * (100 - base) / 100)), cancel)
            self.finished_result.emit(pid, "run", res)
        except AIError as exc:
            self.finished_result.emit(pid, self.mode, {"ok": False, "reason": exc.reason, "detail": exc.detail})
        except Exception as exc:  # never let a worker crash the app
            self.finished_result.emit(pid, self.mode, {"ok": False, "reason": "error", "detail": str(exc)})


class KeyframeCurveWidget(QWidget):
    """Compact editable keyframe curve: drag diamonds to retime/change values,
    double-click to add a point, right-click a point to remove it."""

    def __init__(self, host: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.host = host
        self.clip: Optional[TimelineClip] = None
        self.prop = "opacity"
        self.duration = 1.0
        self._drag_key: Optional[Keyframe] = None
        self._drag_bounds: Optional[Tuple[float, float]] = None
        self.setMinimumHeight(112)
        self.setMaximumHeight(150)
        self.setMouseTracking(True)
        self.setToolTip(tr("kf_curve_tooltip", self.host.controller.lang))

    def set_curve(self, clip: Optional[TimelineClip], prop: str) -> None:
        self.clip = clip
        self.prop = prop
        self.duration = max(0.1, float(clip.duration)) if clip else 1.0
        self.update()

    def _frames(self) -> List[Keyframe]:
        if not self.clip:
            return []
        return sorted(self.clip.keyframes.get(self.prop, []), key=lambda k: k.time_offset)

    def _bounds(self) -> Tuple[float, float]:
        if self._drag_bounds is not None:
            return self._drag_bounds
        values = [k.value for k in self._frames()]
        if not values:
            values = [0.0, 100.0]
        lo, hi = min(values), max(values)
        pad = max(5.0, (hi - lo) * 0.18)
        if hi - lo < 1e-6:
            pad = max(10.0, abs(hi) * 0.15)
        return lo - pad, hi + pad

    def _point(self, k: Keyframe) -> Tuple[float, float]:
        r = self.rect().adjusted(12, 10, -12, -20)
        lo, hi = self._bounds()
        x = r.left() + max(0.0, min(1.0, k.time_offset / self.duration)) * r.width()
        y = r.bottom() - (k.value - lo) / max(1e-6, hi - lo) * r.height()
        return x, y

    def _value_at(self, y: float) -> float:
        r = self.rect().adjusted(12, 10, -12, -20)
        lo, hi = self._bounds()
        ratio = max(0.0, min(1.0, (r.bottom() - y) / max(1.0, r.height())))
        return lo + ratio * (hi - lo)

    def paintEvent(self, _event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(25, 31, 42))
        r = self.rect().adjusted(12, 10, -12, -20)
        p.setPen(QPen(QColor(65, 76, 94), 1))
        for i in range(1, 4):
            y = r.top() + r.height() * i / 4
            p.drawLine(int(r.left()), int(y), int(r.right()), int(y))
        p.drawLine(int(r.left()), int(r.bottom()), int(r.right()), int(r.bottom()))
        frames = self._frames()
        if frames:
            pts = [self._point(k) for k in frames]
            p.setPen(QPen(QColor(60, 190, 220), 2))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
            for x, y in pts:
                p.setPen(QPen(QColor(230, 245, 250), 1))
                p.setBrush(QBrush(QColor(35, 175, 215)))
                p.drawEllipse(int(x - 5), int(y - 5), 10, 10)
        else:
            p.setPen(QColor(170, 180, 195))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, tr("kf_curve_empty", self.host.controller.lang))
        p.setPen(QColor(155, 166, 182))
        p.drawText(8, self.height() - 4, "0s")
        p.drawText(self.width() - 42, self.height() - 4, f"{self.duration:.1f}s")
        p.end()

    def mousePressEvent(self, event: Any) -> None:
        if not self.clip:
            return
        frames = self._frames()
        pos = event.position()
        if event.button() == Qt.MouseButton.RightButton:
            nearest = min(range(len(frames)), key=lambda i: (self._point(frames[i])[0]-pos.x())**2 + (self._point(frames[i])[1]-pos.y())**2, default=-1)
            if nearest >= 0:
                x, y = self._point(frames[nearest])
                if (x-pos.x())**2 + (y-pos.y())**2 <= 144:
                    self.host.controller.project.push_undo_snapshot()
                    self.clip.keyframes[self.prop].remove(frames[nearest])
                    self.host.refresh_all()
                    self.update()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        nearest = min(range(len(frames)), key=lambda i: (self._point(frames[i])[0]-pos.x())**2 + (self._point(frames[i])[1]-pos.y())**2, default=-1)
        if nearest >= 0:
            x, y = self._point(frames[nearest])
            if (x-pos.x())**2 + (y-pos.y())**2 <= 144:
                self.host.controller.project.push_undo_snapshot()
                self._drag_bounds = self._bounds()
                self._drag_key = frames[nearest]
                return

    def mouseMoveEvent(self, event: Any) -> None:
        if self._drag_key is None or not self.clip:
            return
        frames = self._frames()
        if self._drag_key not in frames:
            return
        r = self.rect().adjusted(12, 10, -12, -20)
        k = self._drag_key
        k.time_offset = max(0.0, min(self.duration, (event.position().x() - r.left()) / max(1.0, r.width()) * self.duration))
        k.value = self._value_at(event.position().y())
        self.clip.keyframes[self.prop] = sorted(frames, key=lambda item: item.time_offset)
        self.update()

    def mouseReleaseEvent(self, event: Any) -> None:
        if self._drag_key is not None:
            self._drag_key = None
            self._drag_bounds = None
            self.host.refresh_all()
            self.update()

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if not self.clip or event.button() != Qt.MouseButton.LeftButton:
            return
        r = self.rect().adjusted(12, 10, -12, -20)
        t = max(0.0, min(self.duration, (event.position().x() - r.left()) / max(1.0, r.width()) * self.duration))
        frames = self._frames()
        default = float(getattr(self.clip, self.prop, 100.0)) if not self.prop.startswith("color.") else float(getattr(self.clip.color, self.prop.split(".", 1)[1]))
        value = interpolate_keyframes(frames, t, default)
        self.host.controller.project.add_keyframe(self.clip.id, self.prop, t, value, "linear")
        self.host.refresh_all()
        self.update()


class SideTabs(QWidget):
    """Tab container with a slim vertical icon rail (CapCut style): every section is one click away, nothing hides
    behind scroll arrows, and the content gets the full panel height. Mimics the QTabWidget calls the code uses."""

    currentChanged = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self._rail = QFrame()
        self._rail.setObjectName("RailFrame")
        self._rail_lay = QVBoxLayout(self._rail)
        self._rail_lay.setContentsMargins(2, 3, 2, 3)
        self._rail_lay.setSpacing(2)
        self._rail_lay.addStretch(1)
        self._stack = QStackedWidget()
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: List[QToolButton] = []
        lay.addWidget(self._rail)
        lay.addWidget(self._stack, 1)

    def addTab(self, widget: QWidget, label: str = "") -> int:
        idx = self._stack.addWidget(widget)
        b = QToolButton()
        b.setObjectName("RailButton")
        b.setCheckable(True)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        b.setFixedSize(54, 44)
        b.setText(label)
        b.clicked.connect(lambda _=False, i=idx: self.setCurrentIndex(i))
        self._group.addButton(b)
        self._buttons.append(b)
        self._rail_lay.insertWidget(idx, b)
        if idx == 0:
            b.setChecked(True)
        return idx

    def setTabText(self, i: int, text: str) -> None:
        if 0 <= i < len(self._buttons):
            self._buttons[i].setText(text)

    def setTabToolTip(self, i: int, text: str) -> None:
        if 0 <= i < len(self._buttons):
            self._buttons[i].setToolTip(text)

    def setCurrentIndex(self, i: int) -> None:
        if 0 <= i < self._stack.count():
            self._stack.setCurrentIndex(i)
            self._buttons[i].setChecked(True)
            self.currentChanged.emit(i)

    def currentIndex(self) -> int:
        return self._stack.currentIndex()


class _StickerList(QListWidget):
    """Compact icon grid. Items can be dragged to the timeline; files dropped from the computer are imported."""

    def __init__(self, panel: Any):
        super().__init__()
        self.panel = panel
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setMovement(QListWidget.Movement.Static)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setWrapping(True)
        self.setSpacing(0)
        self.setIconSize(QSize(40, 40))
        self.setGridSize(QSize(48, 48))
        self.setMouseTracking(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setAcceptDrops(True)  # must come after setDragDropMode, which resets it

    def startDrag(self, supported_actions: Any) -> None:
        it = self.currentItem()
        if it is None:
            return
        resolved = self.panel.resolve_item(it)
        if resolved is None:
            return
        path, meta = resolved
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(str(path))])
        md.setData(STICKER_MIME, json.dumps(meta).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(md)
        drag.setPixmap(it.icon().pixmap(44, 44))
        drag.exec(Qt.DropAction.CopyAction)  # copy only: the list must never lose the item

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls() and not event.mimeData().hasFormat(STICKER_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasUrls() and not event.mimeData().hasFormat(STICKER_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event: Any) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths and not event.mimeData().hasFormat(STICKER_MIME):
            self.panel.import_paths(paths)
            event.acceptProposedAction()

    def leaveEvent(self, event: Any) -> None:
        self.panel.hover_stop()
        super().leaveEvent(event)


class BrowserPanel(SideTabs):
    """7 sections on a side rail: Media, Audio, Text & SRT, Effects & LUTs, Transitions, AI Hub, Stickers."""

    def __init__(self, host: Any):
        super().__init__()
        self.host = host
        self.c = host.controller
        self.setMinimumWidth(240)
        self._i18n: List[Tuple[Any, str, str]] = []  # (widget, key, setter)
        self._build_media()
        self._build_audio()
        self._build_text()
        self._build_effects()
        self._build_transitions()
        self._build_ai()
        self._build_stickers()
        self._mic = None
        self.currentChanged.connect(self._on_tab_changed)

    # ---- helpers -------------------------------------------------------
    def _t(self, widget: Any, key: str, setter: str = "setText") -> Any:
        self._i18n.append((widget, key, setter))
        return widget

    def _btn(self, key: str, slot: Callable[..., Any], accent: bool = False) -> QPushButton:
        b = QPushButton()
        if accent:
            b.setObjectName("AccentButton")
        b.clicked.connect(lambda _=False: slot())
        return self._t(b, key)

    @staticmethod
    def _tight(lay: Any) -> Any:
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        return lay

    def _require_clip(self) -> Optional[TimelineClip]:
        clip = self.c.get_selected_clip()
        if clip is None:
            QMessageBox.information(self, "HMZ", tr("no_clip_selected", self.c.lang))
        return clip

    # ---- tab 1: media --------------------------------------------------
    def _build_media(self) -> None:
        w = QWidget()
        lay = self._tight(QVBoxLayout(w))
        self.lbl_drop = self._t(QLabel(), "drop_media_hint")
        self.lbl_drop.setWordWrap(True)
        self.lbl_drop.setObjectName("HintLabel")
        self.media_list = _MediaList(self.host.handle_dropped_paths)
        self.media_list.itemDoubleClicked.connect(lambda _i: self._add_media_to_timeline())
        lay.addWidget(self.media_list, 1)
        lay.addWidget(self.lbl_drop)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._btn("media_import_short", self.host._on_import_media))
        row.addWidget(self._btn("media_add_short", self._add_media_to_timeline, accent=True), 1)
        row.addWidget(self._btn("media_proxy_short", self._generate_proxy))
        lay.addLayout(row)
        self.addTab(w, "")

    def refresh_media(self) -> None:
        self.media_list.clear()
        for p in self.c.media_bin:
            it = QListWidgetItem(Path(p).name)
            it.setData(Qt.ItemDataRole.UserRole, p)
            it.setToolTip(p)
            self.media_list.addItem(it)

    def _selected_media(self) -> Optional[str]:
        it = self.media_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _add_media_to_timeline(self) -> None:
        p = self._selected_media()
        if p:
            self.c.add_media_to_timeline(p, at=self.c.project.playhead_sec)
            self.host.refresh_all()

    def _generate_proxy(self) -> None:
        clip = self._require_clip()
        if clip is None or clip.clip_type != "video":
            return
        self.host.generate_proxy_for_clip(clip.id)

    # ---- tab 2: audio --------------------------------------------------
    def _build_audio(self) -> None:
        w = QWidget()
        lay = self._tight(QVBoxLayout(w))
        self.audio_list = QListWidget()
        self.audio_list.itemClicked.connect(self._select_audio_clip)
        lay.addWidget(self.audio_list, 1)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._btn("media_import_short", self.host._on_import_media))
        self.btn_mic = self._btn("btn_mic_record", self._toggle_mic)
        row.addWidget(self.btn_mic, 1)
        lay.addLayout(row)
        lay.addWidget(self._btn("btn_detach_audio", self._detach_audio))
        self.addTab(w, "")

    def refresh_audio(self) -> None:
        self.audio_list.clear()
        for trk in self.c.project.tracks:
            if trk.track_type != "audio":
                continue
            for clip in trk.clips:
                it = QListWidgetItem(f"{clip.name}  [{clip.timeline_start:.1f}s]")
                it.setData(Qt.ItemDataRole.UserRole, clip.id)
                self.audio_list.addItem(it)

    def _select_audio_clip(self, item: QListWidgetItem) -> None:
        self.c.selected_clip_id = item.data(Qt.ItemDataRole.UserRole)
        self.host.refresh_all()

    def _detach_audio(self) -> None:
        clip = self._require_clip()
        if clip is not None and self.c.project.detach_audio_from_clip(clip.id):
            self.host.refresh_all()

    # ---- tab 3: text & subtitles ---------------------------------------
    def _build_text(self) -> None:
        w = QWidget()
        lay = self._tight(QVBoxLayout(w))
        lay.addWidget(self._btn("btn_add_text_layer", lambda: self._add_text("default"), accent=True))
        grid = QGridLayout()
        grid.setSpacing(4)
        grid.addWidget(self._btn("text_preset_title", lambda: self._add_text("title")), 0, 0)
        grid.addWidget(self._btn("text_preset_subtitle", lambda: self._add_text("subtitle")), 0, 1)
        grid.addWidget(self._btn("text_preset_badge", lambda: self._add_text("badge")), 1, 0)
        grid.addWidget(self._btn("subtitle_cinematic", lambda: self._add_text("cinematic")), 1, 1)
        grid.addWidget(self._btn("subtitle_social", lambda: self._add_text("social")), 2, 0)
        grid.addWidget(self._btn("subtitle_minimal", lambda: self._add_text("minimal")), 2, 1)
        grid.addWidget(self._btn("btn_import_srt", self._import_srt), 3, 0)
        grid.addWidget(self._btn("btn_export_srt", self._export_srt), 3, 1)
        grid.addWidget(self._btn("export_vtt", self._export_vtt), 4, 0, 1, 2)
        lay.addLayout(grid)
        lay.addStretch(1)
        self.addTab(w, "")

    def _add_text(self, preset: str, start: Optional[float] = None) -> None:
        styles: Dict[str, TextStyleSettings] = {
            "default": TextStyleSettings(),
            "title": TextStyleSettings(text="Title / عنوان", font_size=84, stroke_width=4, shadow_enabled=True),
            "subtitle": TextStyleSettings(text="Subtitle / ترجمة", font_size=42, stroke_width=3),
            "badge": TextStyleSettings(text="NEW / جديد", font_size=38, bg_enabled=True, bg_color_hex="#0D3B42", stroke_width=0, animation_in="slide_up"),
            "cinematic": TextStyleSettings(text="Subtitle / ترجمة", font_size=44, bold=False, stroke_width=3, shadow_enabled=True, shadow_blur=4, align="center"),
            "social": TextStyleSettings(text="SUBTITLE / ترجمة", font_size=60, bold=True, stroke_width=5, glow_enabled=True, glow_radius=7, align="center"),
            "minimal": TextStyleSettings(text="Subtitle / ترجمة", font_size=38, bold=False, stroke_width=0, shadow_enabled=True, shadow_opacity=55, align="center"),
        }
        trk = next((t for t in self.c.project.tracks if t.track_type == "text" and not t.locked), None)
        if trk is None:
            trk = self.c.project.add_track("text")
        at = self.c.project.playhead_sec if start is None else start
        clip = TimelineClip(name=styles[preset].text[:24], clip_type="text", timeline_start=at, duration=4.0, text_style=styles[preset])
        if preset == "title":
            clip.pos_y = -300.0
        if self.c.project.add_clip_to_track(trk.id, clip):
            self.c.select_clip(clip.id)
        self.host.refresh_all()
        self.host.open_inspector_for(clip.id, focus_text=True)

    def _import_srt(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("btn_import_srt", self.c.lang), "", "SRT (*.srt)")
        if path:
            self.c.open_cli_file(path)
            self.host.refresh_all()

    def _export_srt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, tr("btn_export_srt", self.c.lang), "subtitles.srt", "SRT (*.srt)")
        if not path:
            return
        clips = [cl for trk in self.c.project.tracks if trk.track_type == "text" for cl in trk.clips]
        Path(path).write_text(export_clips_to_srt(clips), encoding="utf-8")

    def _export_vtt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export WebVTT", "subtitles.vtt", "WebVTT (*.vtt)")
        if not path:
            return
        clips = [cl for trk in self.c.project.tracks if trk.track_type == "text" for cl in trk.clips]
        Path(path).write_text(export_clips_to_vtt(clips), encoding="utf-8")

    # ---- tab 4: effects & LUT ------------------------------------------
    def _build_effects(self) -> None:
        w = QWidget()
        lay = self._tight(QVBoxLayout(w))
        self.fx_list = QListWidget()
        self.fx_list.itemDoubleClicked.connect(lambda _i: self._apply_effect())
        lay.addWidget(self.fx_list, 1)
        lay.addWidget(self._t(QLabel(), "tab_hint_effects"))
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._btn("btn_apply_effect", self._apply_effect, accent=True), 1)
        row.addWidget(self._btn("btn_load_lut", self._load_lut))
        lay.addLayout(row)
        self.addTab(w, "")

    def _apply_effect(self) -> None:
        clip = self._require_clip()
        row = self.fx_list.currentRow()
        if clip is None or row < 0:
            return
        self.c.project.push_undo_snapshot()
        clip.visual_effect = EFFECTS[row][0]
        self.host.refresh_all()

    def _load_lut(self) -> None:
        clip = self._require_clip()
        if clip is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, tr("btn_load_lut", self.c.lang), "", "LUT (*.cube)")
        if path:
            self.c.project.push_undo_snapshot()
            clip.color.lut_path = path
            self.host.refresh_all()

    # ---- tab 5: transitions --------------------------------------------
    def _build_transitions(self) -> None:
        w = QWidget()
        lay = self._tight(QVBoxLayout(w))
        self.tr_list = QListWidget()
        self.tr_list.itemDoubleClicked.connect(lambda _i: self._apply_transition())
        lay.addWidget(self.tr_list, 1)
        lay.addWidget(self._t(QLabel(), "tab_hint_trans"))
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(self._t(QLabel(), "trans_duration_label"))
        self.spn_trans = QDoubleSpinBox()
        self.spn_trans.setRange(0.1, 3.0)
        self.spn_trans.setSingleStep(0.1)
        self.spn_trans.setValue(0.5)
        self.spn_trans.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        row.addWidget(self.spn_trans)
        lay.addLayout(row)
        lay.addWidget(self._btn("btn_apply_transition", self._apply_transition, accent=True))
        lay.addWidget(self._btn("btn_apply_ab_transition", self._apply_ab_transition))
        self.addTab(w, "")

    def _apply_transition(self) -> None:
        clip = self._require_clip()
        row = self.tr_list.currentRow()
        if clip is None or row < 0:
            return
        self.c.project.push_undo_snapshot()
        clip.transition_in = TRANSITIONS[row][0]
        clip.transition_duration = float(self.spn_trans.value())
        self.host.refresh_all()

    def _apply_ab_transition(self) -> None:
        incoming = self._require_clip()
        row = self.tr_list.currentRow()
        if incoming is None or row < 0:
            return
        found = self.c.project.find_clip(incoming.id)
        if not found:
            return
        track, _ = found
        previous = [cl for cl in track.clips if cl.id != incoming.id and abs(cl.timeline_end-incoming.timeline_start) <= 0.08]
        if not previous:
            QMessageBox.information(self, "HMZ", tr("trans_ab_no_adjacent", self.c.lang))
            return
        outgoing = max(previous, key=lambda cl: cl.timeline_start)
        ok = self.c.project.create_ab_transition(outgoing.id, incoming.id, float(self.spn_trans.value()), TRANSITIONS[row][0])
        if not ok:
            QMessageBox.information(self, "HMZ", tr("trans_ab_no_handles", self.c.lang))
            return
        self.host.refresh_all()

    # ---- tab 6: AI hub --------------------------------------------------
    def _build_ai(self) -> None:
        w = QWidget()
        lay = self._tight(QVBoxLayout(w))
        hdr = self._t(QLabel(), "ai_hub_header")
        hdr.setWordWrap(True)
        lay.addWidget(hdr)
        self.ai_list = QListWidget()
        self.ai_list.currentRowChanged.connect(self._refresh_ai_detail)
        lay.addWidget(self.ai_list, 1)
        self.lbl_ai_desc = QLabel()
        self.lbl_ai_desc.setWordWrap(True)
        lay.addWidget(self.lbl_ai_desc)
        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 100)
        self.ai_progress.setVisible(False)
        lay.addWidget(self.ai_progress)
        self.btn_ai_install = self._btn("btn_ai_install", self._ai_install)
        self.btn_ai_run = self._btn("btn_ai_run", self._ai_run, accent=True)
        self.btn_ai_cancel = self._btn("btn_cancel", self._ai_cancel)
        self.btn_ai_cancel.setVisible(False)
        lay.addWidget(self.btn_ai_install)
        lay.addWidget(self.btn_ai_run)
        lay.addWidget(self.btn_ai_cancel)
        lay.addWidget(self._btn("btn_ai_open_folder", self._ai_open_folder))
        self._ai_job = None
        self._ai_job_clip_id = None
        self.addTab(w, "")

    # ---- microphone ------------------------------------------------------
    def _toggle_mic(self) -> None:
        lang = self.c.lang
        try:
            from video_studio_record import MicRecorder
        except Exception:
            QMessageBox.warning(self, "HMZ", tr("mic_unavailable", lang))
            return
        if self._mic is None:
            self._mic = MicRecorder(self)
            self._mic.failed.connect(self._on_mic_failed)
            self._mic.finished.connect(self._on_mic_finished)
        if self._mic.recording:
            self._mic.stop()
            self.btn_mic.setText(tr("btn_mic_record", lang))
            return
        rec_dir = Path(self.c.custom_data_dir or (Path(os.environ.get("APPDATA") or Path.home() / ".config") / "HMZVideoStudioPro")) / "recordings"
        out = rec_dir / f"rec_{datetime.datetime.now():%Y%m%d_%H%M%S}.wav"
        self._mic_start_sec = self.c.project.playhead_sec
        if self._mic.start(out):
            self.btn_mic.setText(tr("btn_mic_stop", lang))

    def _on_mic_failed(self, reason: str) -> None:
        self.btn_mic.setText(tr("btn_mic_record", self.c.lang))
        key = {"no_device": "mic_no_device", "no_data": "mic_no_data"}.get(reason, "mic_error")
        QMessageBox.warning(self, "HMZ", tr(key, self.c.lang, err=reason))

    def _on_mic_finished(self, path: str) -> None:
        self.btn_mic.setText(tr("btn_mic_record", self.c.lang))
        self.c.add_media_to_timeline(path, at=getattr(self, "_mic_start_sec", 0.0))
        self.host.refresh_all()

    # ---- tab 7: stickers ---------------------------------------------------
    def _build_stickers(self) -> None:
        w = QWidget()
        lay = self._tight(QVBoxLayout(w))
        top = QHBoxLayout()
        top.setSpacing(4)
        self.le_stk_search = QLineEdit()
        self.le_stk_search.setClearButtonEnabled(True)
        self._t(self.le_stk_search, "stk_search", "setPlaceholderText")
        self.le_stk_search.textChanged.connect(self._reload_sticker_icons)
        self.cmb_stk_color = QComboBox()
        self.cmb_stk_color.setMinimumContentsLength(5)
        self.cmb_stk_color.currentIndexChanged.connect(self._reload_sticker_icons)
        top.addWidget(self.le_stk_search, 1)
        top.addWidget(self.cmb_stk_color)
        lay.addLayout(top)

        chips = QHBoxLayout()
        chips.setSpacing(2)
        self._stk_group = QButtonGroup(self)
        self._stk_group.setExclusive(True)
        self._stk_filter = "all"
        for key, tr_key in (("all", "stk_filter_all"), ("anim", "stk_filter_anim"), ("static", "stk_filter_static"), ("mine", "stk_filter_mine")):
            b = QPushButton()
            b.setObjectName("ChipButton")
            b.setCheckable(True)
            b.setChecked(key == "all")
            self._t(b, tr_key)
            b.clicked.connect(lambda _=False, k=key: self._set_sticker_filter(k))
            self._stk_group.addButton(b)
            chips.addWidget(b)
        chips.addStretch(1)
        b_imp = QToolButton()
        b_imp.setObjectName("GhostButton")
        self._t(b_imp, "stk_import_short")
        b_imp.clicked.connect(self._import_sticker)
        b_dir = QToolButton()
        b_dir.setObjectName("GhostButton")
        self._t(b_dir, "stk_folder_short")
        self._t(b_dir, "stk_folder_tip", "setToolTip")
        b_dir.clicked.connect(self._open_my_stickers)
        chips.addWidget(b_imp)
        chips.addWidget(b_dir)
        lay.addLayout(chips)

        self.stk_list = _StickerList(self)
        self.stk_list.itemDoubleClicked.connect(lambda _i: self._add_sticker())
        self.stk_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.stk_list.customContextMenuRequested.connect(self._sticker_menu)
        self.stk_list.itemEntered.connect(self._on_sticker_hover)
        self.stk_list.currentItemChanged.connect(lambda cur, _prev: self.lbl_stk_name.setText(cur.toolTip()) if cur is not None else None)
        lay.addWidget(self.stk_list, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        self.lbl_stk_name = QLabel("")
        self.lbl_stk_name.setObjectName("HintLabel")
        bottom.addWidget(self.lbl_stk_name, 1)
        bottom.addWidget(self._btn("media_add_short", self._add_sticker, accent=True))
        lay.addLayout(bottom)
        hint = self._t(QLabel(), "stk_hint")
        hint.setWordWrap(True)
        hint.setObjectName("HintLabel")
        lay.addWidget(hint)

        self._stk_icons: Dict[Tuple[str, str], QIcon] = {}
        self._stk_anim: Dict[Tuple[str, str], List[QIcon]] = {}
        self._hover_item: Optional[QListWidgetItem] = None
        self._hover_i = 0
        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(70)
        self._hover_timer.timeout.connect(self._hover_tick)
        self._stk_loaded = False
        self.addTab(w, "")

    def _refill_sticker_colors(self) -> None:
        cur = self.cmb_stk_color.currentData()
        self.cmb_stk_color.blockSignals(True)
        self.cmb_stk_color.clear()
        for hex_, (ar, en) in STICKER_COLORS.items():
            sw = QPixmap(14, 14)
            sw.fill(QColor(hex_))
            self.cmb_stk_color.addItem(QIcon(sw), ar if self.c.lang == "ar" else en, hex_)
        self.cmb_stk_color.setCurrentIndex(max(0, self.cmb_stk_color.findData(cur)) if cur else 0)
        self.cmb_stk_color.blockSignals(False)

    def _on_tab_changed(self, idx: int) -> None:
        if idx == 6 and not self._stk_loaded:
            self._reload_sticker_icons()

    @staticmethod
    def _pil_to_icon(im: Any) -> QIcon:
        rgba = im.convert("RGBA")
        w, h = rgba.size
        qimg = QImage(rgba.tobytes("raw", "RGBA"), w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
        return QIcon(QPixmap.fromImage(qimg))

    def _set_sticker_filter(self, key: str) -> None:
        self._stk_filter = key
        self._reload_sticker_icons()

    def _sticker_color(self) -> str:
        return str(self.cmb_stk_color.currentData() or "#FFD60A")

    def _builtin_icon(self, sid: str, color: str) -> QIcon:
        ic = self._stk_icons.get((sid, color))
        if ic is None:
            ic = self._stk_icons[(sid, color)] = self._pil_to_icon(render_frame(sid, 0.3, color, 64, 3))  # small + cheap, not a 256 px render
        return ic

    def _reload_sticker_icons(self, *_: Any) -> None:
        if not hasattr(self, "stk_list"):
            return
        self.hover_stop()
        lang = self.c.lang
        color = self._sticker_color()
        q = self.le_stk_search.text().strip().lower()
        mode = self._stk_filter
        names = self.c.sticker_names()
        self.stk_list.setUpdatesEnabled(False)
        self.stk_list.clear()
        if mode != "mine":
            for sid, (ar, en, anim, _fn) in STICKERS.items():
                if (mode == "anim" and not anim) or (mode == "static" and anim):
                    continue
                if q and q not in ar.lower() and q not in en.lower():
                    continue
                it = QListWidgetItem(self._builtin_icon(sid, color), "")
                it.setToolTip(sticker_display_name(sid, lang))
                it.setData(Qt.ItemDataRole.UserRole, ("builtin", sid))
                self.stk_list.addItem(it)
        if mode in ("all", "mine"):
            try:
                for f in sorted(self.c.my_stickers_dir().iterdir()):
                    if not f.is_file() or f.suffix.lower() not in (".png", ".gif", ".webp"):
                        continue
                    entry = names.get(f.name, {})
                    label = entry.get(lang) or entry.get("en" if lang == "ar" else "ar") or f.stem.replace("_", " ")
                    searchable = " ".join([f.stem, *entry.values()]).lower()
                    if q and q not in searchable:
                        continue
                    ck = (str(f), str(f.stat().st_mtime))
                    icon = self._stk_icons.get(ck)
                    if icon is None:
                        pm = QPixmap(str(f))
                        if not pm.isNull():
                            pm = pm.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                        icon = self._stk_icons[ck] = QIcon(pm) if not pm.isNull() else QIcon()
                    it = QListWidgetItem(icon, "")
                    it.setToolTip(label + ("  ▶" if f.suffix.lower() == ".gif" else "") + "  ★")
                    it.setData(Qt.ItemDataRole.UserRole, ("file", str(f)))
                    self.stk_list.addItem(it)
            except OSError:
                pass
        self.stk_list.setUpdatesEnabled(True)
        self.lbl_stk_name.setText(tr("stk_none_found", lang) if self.stk_list.count() == 0 else "")
        self._stk_loaded = True

    # hover animation: animated built-ins play in the grid while the mouse is over them
    def _on_sticker_hover(self, it: QListWidgetItem) -> None:
        self.lbl_stk_name.setText(it.toolTip())
        if it is self._hover_item:
            return
        self.hover_stop()
        kind, val = it.data(Qt.ItemDataRole.UserRole)
        if kind == "builtin" and STICKERS[val][2]:
            self._hover_item, self._hover_i = it, 0
            self._hover_timer.start()

    def _hover_tick(self) -> None:
        it = self._hover_item
        if it is None:
            self._hover_timer.stop()
            return
        try:
            kind, val = it.data(Qt.ItemDataRole.UserRole)
            color = self._sticker_color()
            frames = self._stk_anim.get((val, color))
            if frames is None:
                frames = self._stk_anim[(val, color)] = [self._pil_to_icon(render_frame(val, i / 12.0, color, 64, 3)) for i in range(12)]
            self._hover_i = (self._hover_i + 1) % len(frames)
            it.setIcon(frames[self._hover_i])
        except RuntimeError:  # the item was deleted by a reload
            self._hover_item = None
            self._hover_timer.stop()

    def hover_stop(self) -> None:
        if hasattr(self, "_hover_timer"):
            self._hover_timer.stop()
        it, self._hover_item = getattr(self, "_hover_item", None), None
        if it is not None:
            try:
                kind, val = it.data(Qt.ItemDataRole.UserRole)
                if kind == "builtin":
                    it.setIcon(self._builtin_icon(val, self._sticker_color()))
            except RuntimeError:
                pass

    def resolve_item(self, it: QListWidgetItem) -> Optional[Tuple[Path, Dict[str, Any]]]:
        """(file path, clip metadata) of a grid item; built-in stickers are rendered to a file on first use."""
        kind, val = it.data(Qt.ItemDataRole.UserRole)
        if kind == "builtin":
            color = self._sticker_color()
            path = sticker_file(val, self.c.stickers_dir(), color)
            return (path, {"sticker_id": val, "sticker_color": color}) if path is not None else None
        return Path(val), {}

    def _sticker_menu(self, pos: Any) -> None:
        it = self.stk_list.itemAt(pos)
        if it is None:
            return
        kind, val = it.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.addAction(tr("btn_add_sticker", self.c.lang), self._add_sticker)
        if kind == "file":
            file_name = Path(val).name
            menu.addAction(tr("stk_rename", self.c.lang), lambda fn=file_name: self._rename_sticker(fn))
            menu.addAction(tr("stk_remove", self.c.lang), lambda path=Path(val): self._remove_sticker(path))
        menu.exec(self.stk_list.viewport().mapToGlobal(pos))

    def _rename_sticker(self, file_name: str) -> None:
        lang = self.c.lang
        current = self.c.sticker_names().get(file_name, {})
        stem = Path(file_name).stem.replace("_", " ")
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("stk_rename", lang))
        form = QFormLayout(dlg)
        ed_ar = QLineEdit(current.get("ar", stem))
        ed_en = QLineEdit(current.get("en", stem))
        ed_en.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        form.addRow(tr("stk_name_ar", lang), ed_ar)
        form.addRow(tr("stk_name_en", lang), ed_en)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.c.set_sticker_name(file_name, ed_ar.text(), ed_en.text())
            self._reload_sticker_icons()

    def _remove_sticker(self, path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            return
        self._reload_sticker_icons()

    def _add_sticker(self) -> None:
        it = self.stk_list.currentItem()
        if it is None:
            QMessageBox.information(self, "HMZ", tr("stk_pick_first", self.c.lang))
            return
        resolved = self.resolve_item(it)
        if resolved is None or not self.c.add_sticker_to_timeline(str(resolved[0]), self.c.project.playhead_sec, meta=resolved[1] or None):
            QMessageBox.warning(self, "HMZ", tr("stk_add_failed", self.c.lang))
            return
        self.host.refresh_all()
        found = self.c.project.find_clip(self.c.selected_clip_id)
        if found is not None:
            self.host.timeline_widget.ensure_track_visible(found[0].id)

    def import_paths(self, paths: List[str]) -> None:
        done = self.c.import_stickers(paths)
        if not done:
            QMessageBox.information(self, "HMZ", tr("stk_import_none", self.c.lang))
            return
        self._stk_filter = "mine"
        for b in self._stk_group.buttons():
            b.setChecked(b is self._stk_group.buttons()[-1])
        self._reload_sticker_icons()
        self.lbl_stk_name.setText(tr("stk_imported", self.c.lang, n=len(done)))

    def _import_sticker(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, tr("btn_import_sticker", self.c.lang), "", "Stickers (*.png *.gif *.webp)")
        if paths:
            self.import_paths(paths)

    def _open_my_stickers(self) -> None:
        folder = str(self.c.my_stickers_dir())
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            QMessageBox.information(self, "HMZ", folder)

    def _plugins(self) -> list:
        return self.c.ai_registry.list_plugins()

    def _refresh_ai_list(self) -> None:
        lang = self.c.lang
        row = self.ai_list.currentRow()
        self.ai_list.blockSignals(True)
        self.ai_list.clear()
        for p in self._plugins():
            d = p.descriptor
            if p.dependency_error():
                state = tr("ai_status_nodeps", lang)
            elif not d.model_filename:
                state = tr("ai_status_builtin", lang)
            else:
                state = tr("ai_status_installed" if p.is_installed() else "ai_status_not_installed", lang)
            size = f"  (~{d.approx_size_mb} MB)" if d.model_filename and not p.is_installed() else ""
            self.ai_list.addItem(f"{d.name_ar if lang == 'ar' else d.name_en}\n{state}{size}")
        self.ai_list.blockSignals(False)
        self.ai_list.setCurrentRow(row if row >= 0 else 0)
        self._refresh_ai_detail()

    def _refresh_ai_detail(self, *_: Any) -> None:
        row = self.ai_list.currentRow()
        plugins = self._plugins()
        if 0 <= row < len(plugins):
            d = plugins[row].descriptor
            self.lbl_ai_desc.setText(d.desc_ar if self.c.lang == "ar" else d.desc_en)

    def _current_plugin(self) -> Any:
        row = self.ai_list.currentRow()
        plugins = self._plugins()
        return plugins[row] if 0 <= row < len(plugins) else None

    def _ai_set_busy(self, busy: bool) -> None:
        self.btn_ai_install.setEnabled(not busy)
        self.btn_ai_run.setEnabled(not busy)
        self.btn_ai_cancel.setVisible(busy)
        self.ai_progress.setVisible(busy)
        if not busy:
            self.ai_progress.setValue(0)

    def _ai_cancel(self) -> None:
        if self._ai_job is not None:
            self._ai_job.cancel_flag = True

    def _ai_message(self, res: Dict[str, Any]) -> str:
        lang = self.c.lang
        reason = str(res.get("reason") or "error")
        key = f"ai_reason_{reason}"
        text = tr(key, lang, detail=res.get("detail", ""))
        return text if text != key else tr("ai_reason_error", lang, detail=res.get("detail") or reason)

    def _ai_start(self, mode: str) -> None:
        p = self._current_plugin()
        if p is None or self._ai_job is not None:
            return
        lang = self.c.lang
        if p.descriptor.plugin_id == "ai_whisper_captions":
            options = ["tiny (~75 MB)", "base (~145 MB)", "small (~490 MB)", "medium (~1.5 GB)", "large-v3 (~3 GB)"]
            current_size = getattr(p, "model_size", "base")
            current_index = ["tiny", "base", "small", "medium", "large-v3"].index(current_size) if current_size in ["tiny", "base", "small", "medium", "large-v3"] else 1
            selected, ok = QInputDialog.getItem(
                self, "Whisper model", "Choose model size (larger models need more disk space and memory):",
                options, current_index, False,
            )
            if not ok:
                return
            p.model_size = ["tiny", "base", "small", "medium", "large-v3"][options.index(selected)]
            p.descriptor.approx_size_mb = p.MODEL_OPTIONS[p.model_size]
        if mode == "install" and not p.descriptor.model_filename:
            QMessageBox.information(self, "HMZ", tr("ai_no_model_needed", lang))
            return
        clip = self.c.get_selected_clip()
        if mode == "run":
            if p.descriptor.needs_clip and clip is None:
                QMessageBox.information(self, "HMZ", tr("no_clip_selected", lang))
                return
            if p.descriptor.model_filename and not p.is_installed():
                if QMessageBox.question(self, "HMZ", tr("ai_need_model_ask", lang, size=p.descriptor.approx_size_mb)) != QMessageBox.StandardButton.Yes:
                    return
                mode = "install_run"
        params = self.c.ai_registry.params(self.c.ffmpeg_path())
        params["language"] = None
        if mode == "run" and p.descriptor.plugin_id == "ai_motion_tracking":
            if clip is None or clip.clip_type != "video":
                QMessageBox.information(self, "HMZ", "Select the source video clip first.")
                return
            roi_text, ok = QInputDialog.getText(
                self, "Motion Tracking ROI", "Enter tracking region as normalized x,y,width,height (0..1):",
                text="0.25,0.25,0.25,0.25",
            )
            if not ok:
                return
            try:
                roi = tuple(float(v.strip()) for v in roi_text.split(","))
                if len(roi) != 4 or any(v < 0 or v > 1 for v in roi) or roi[2] <= 0 or roi[3] <= 0 or roi[0]+roi[2] > 1 or roi[1]+roi[3] > 1:
                    raise ValueError("ROI must fit inside 0..1")
            except Exception:
                QMessageBox.warning(self, "HMZ", "Invalid ROI. Use x,y,width,height between 0 and 1.")
                return
            overlays = [(f"{cl.name}  [{cl.id}]", cl.id) for trk in self.c.project.tracks for cl in trk.clips if cl.clip_type in ("text", "sticker")]
            if not overlays:
                QMessageBox.information(self, "HMZ", "Add a text or sticker layer first, then run Motion Tracking.")
                return
            labels = [item[0] for item in overlays]
            chosen, ok = QInputDialog.getItem(self, "Attach Motion Track", "Choose the text/sticker layer to follow the tracked subject:", labels, 0, False)
            if not ok:
                return
            params["roi"] = roi
            params["target_overlay_id"] = overlays[labels.index(chosen)][1]
        job = AIJobThread(p, mode, clip, params)
        job.progress.connect(self.ai_progress.setValue)
        job.finished_result.connect(self._ai_finished)
        register_worker = getattr(self.host, "register_background_worker", None)
        if callable(register_worker):
            register_worker(job)
        self._ai_job = job
        self._ai_job_clip_id = clip.id if clip else None
        self._ai_set_busy(True)
        job.start()

    def _ai_install(self) -> None:
        self._ai_start("install")

    def _ai_run(self) -> None:
        self._ai_start("run")

    def _ai_finished(self, plugin_id: str, mode: str, res: Dict[str, Any]) -> None:
        lang = self.c.lang
        self._ai_job = None
        self._ai_set_busy(False)
        self._refresh_ai_list()
        if not res.get("ok"):
            if res.get("reason") != "cancelled":
                QMessageBox.warning(self, "HMZ", self._ai_message(res))
            return
        if mode == "install":
            QMessageBox.information(self, "HMZ", tr("ai_model_ready", lang))
            return
        p = self.c.ai_registry.get_plugin(plugin_id)
        clip = None
        if self._ai_job_clip_id:
            found = self.c.project.find_clip(self._ai_job_clip_id)
            clip = found[1] if found else None
        if p is None or (p.descriptor.needs_clip and clip is None):
            QMessageBox.warning(self, "HMZ", tr("ai_clip_gone", lang))
            return
        applied = p.apply(self.c.project, clip, res)
        self.host.refresh_all()
        if not applied.get("ok"):
            QMessageBox.warning(self, "HMZ", self._ai_message(applied))
            return
        done = {
            "ai_beat_detection": ("ai_done_beats", {"n": applied.get("markers_added", 0), "bpm": applied.get("bpm", 0)}),
            "ai_scene_split": ("ai_done_scenes", {"n": applied.get("splits", 0)}),
            "ai_noise_reduction": ("ai_done_noise", {}),
            "ai_silence_remover": ("ai_done_silence", {"n": applied.get("removed", 0)}),
            "ai_whisper_captions": ("ai_done_captions", {"n": applied.get("generated_captions", 0)}),
            "ai_auto_cutout": ("ai_done_cutout", {}),
        }.get(plugin_id)
        if done:
            QMessageBox.information(self, "HMZ", tr(done[0], lang, **done[1]))

    def _ai_open_folder(self) -> None:
        folder = str(self.c.ai_registry.models_dir)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass

    # ---- language / refresh --------------------------------------------
    def retranslate(self) -> None:
        lang = self.c.lang
        for widget, key, setter in self._i18n:
            getattr(widget, setter)(tr(key, lang))
        glyphs = ["🎞", "🎵", "Aa", "✨", "⇄", "🧠", "😀"]
        names = ["rail_media", "rail_audio", "rail_text", "rail_effects", "rail_trans", "rail_ai", "rail_stickers"]
        full = ["tab_media", "tab_audio", "tab_text", "tab_effects", "tab_transitions", "tab_ai_hub", "tab_stickers"]
        for i, (g, k, fk) in enumerate(zip(glyphs, names, full)):
            self.setTabText(i, f"{g}\n{tr(k, lang)}")
            self.setTabToolTip(i, tr(fk, lang))
        self._refill_sticker_colors()
        if self._stk_loaded:
            self._reload_sticker_icons()
        self.fx_list.clear()
        for _, k in EFFECTS:
            self.fx_list.addItem(tr(k, lang))
        self.tr_list.clear()
        for _, k in TRANSITIONS:
            self.tr_list.addItem(tr(k, lang))
        self._refresh_ai_list()
        self.refresh_media()
        self.refresh_audio()


class InspectorPanel(QTabWidget):
    """5 tabs: Video/Blend/Mask/Chroma, Color/LUT, Speed, Audio/EQ, Keyframes/Text."""

    def __init__(self, host: Any):
        super().__init__()
        self.host = host
        self.c = host.controller
        self.setObjectName("InspectorPanel")
        self._i18n: List[Tuple[Any, str, str]] = []
        self._combos: List[Tuple[QComboBox, List[Tuple[str, str]]]] = []
        self._loading = False
        self._last_snapshot = 0.0
        self.setMinimumWidth(260)
        # Keep the right-side inspector dense without changing the application's global theme.
        self.setStyleSheet("""
            QTabWidget#InspectorPanel QTabBar::tab { padding: 3px 6px; margin: 1px; }
            QTabWidget#InspectorPanel QDoubleSpinBox,
            QTabWidget#InspectorPanel QComboBox,
            QTabWidget#InspectorPanel QLineEdit { min-height: 21px; max-height: 25px; padding: 1px 4px; }
            QTabWidget#InspectorPanel QPushButton { min-height: 22px; max-height: 26px; padding: 1px 6px; }
            QTabWidget#InspectorPanel QCheckBox { spacing: 4px; }
        """)
        self.tabBar().setExpanding(False)
        self._build_video()
        self._build_color()
        self._build_speed()
        self._build_audio()
        self._build_keyframes()
        self._build_anim()
        self.text_panel = TextEditorPanel(host)
        self.addTab(self.text_panel, "")

    # ---- helpers -------------------------------------------------------
    def _page(self) -> Tuple[QWidget, QFormLayout]:
        inner = QWidget()
        form = QFormLayout(inner)
        form.setContentsMargins(4, 4, 4, 4)
        form.setVerticalSpacing(2)
        form.setHorizontalSpacing(4)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        self.addTab(scroll, "")
        return inner, form

    def _pair(self, f: QFormLayout, k1: str, w1: QWidget, k2: str, w2: QWidget) -> None:
        """Two short 'label + field' groups on one row: halves the height of long forms."""
        box = QHBoxLayout()
        box.setSpacing(3)
        for k, w in ((k1, w1), (k2, w2)):
            lbl = QLabel()
            self._i18n.append((lbl, k, "setText"))
            box.addWidget(lbl)
            box.addWidget(w, 1)
        f.addRow(box)

    def _label(self, key: str) -> QLabel:
        lbl = QLabel()
        lbl.setWordWrap(True)
        self._i18n.append((lbl, key, "setText"))
        return lbl

    def _spin(self, lo: float, hi: float, step: float, apply: Callable[[TimelineClip, float], None], decimals: int = 1) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setDecimals(decimals)
        sp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        sp.setMinimumWidth(48)
        sp.setMaximumWidth(96)
        sp.setMinimumHeight(22)
        sp.setMaximumHeight(25)
        sp.valueChanged.connect(lambda v: self._edit(lambda cl: apply(cl, float(v))))
        return sp

    def _check(self, key: str, apply: Callable[[TimelineClip, bool], None]) -> QCheckBox:
        cb = QCheckBox()
        self._i18n.append((cb, key, "setText"))
        cb.toggled.connect(lambda v: self._edit(lambda cl: apply(cl, bool(v))))
        return cb

    def _combo(self, items: List[Tuple[str, str]], apply: Callable[[TimelineClip, str], None]) -> QComboBox:
        cb = QComboBox()
        cb.setMinimumHeight(22)
        cb.setMaximumHeight(26)
        cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        cb.setMinimumContentsLength(6)
        self._combos.append((cb, items))
        cb.currentIndexChanged.connect(lambda _i: self._edit(lambda cl: apply(cl, str(cb.currentData()))))
        return cb

    def _button(self, key: str, slot: Callable[[], None]) -> QPushButton:
        b = QPushButton()
        b.setMinimumHeight(22)
        b.setMaximumHeight(26)
        self._i18n.append((b, key, "setText"))
        b.clicked.connect(lambda _=False: slot())
        return b

    def _hex_edit(self, apply: Callable[[TimelineClip, str], None]) -> QLineEdit:
        le = QLineEdit()
        le.setMaxLength(7)
        le.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

        def _changed(text: str) -> None:
            t = text.strip()
            if len(t) == 7 and t.startswith("#"):
                try:
                    int(t[1:], 16)
                except ValueError:
                    return
                self._edit(lambda cl: apply(cl, t))

        le.textChanged.connect(_changed)
        return le

    def _edit(self, mutate: Callable[[TimelineClip], None]) -> None:
        """Apply a property change to the selected clip (coalescing undo snapshots)."""
        if self._loading:
            return
        clip = self.c.get_selected_clip()
        if clip is None:
            return
        now = time.monotonic()
        if now - self._last_snapshot > 1.0:
            self.c.project.push_undo_snapshot()
            self._last_snapshot = now
        mutate(clip)
        self.host.refresh_preview_only()

    # ---- tab 1: video & blend ------------------------------------------
    def _build_video(self) -> None:
        _, f = self._page()
        self.sp_x = self._spin(-4000, 4000, 5, lambda c, v: setattr(c, "pos_x", v))
        self.sp_y = self._spin(-4000, 4000, 5, lambda c, v: setattr(c, "pos_y", v))
        self.sp_scale = self._spin(1, 800, 1, lambda c, v: setattr(c, "scale", v))
        self.sp_rot = self._spin(-360, 360, 1, lambda c, v: setattr(c, "rotation", v))
        self.sp_opacity = self._spin(0, 100, 1, lambda c, v: setattr(c, "opacity", v))
        self.sp_effect_intensity = self._spin(0, 100, 1, lambda c, v: setattr(c, "effect_intensity", v))
        self.cb_flip_h = self._check("lbl_flip_h", lambda c, v: setattr(c, "flip_h", v))
        self.cb_flip_v = self._check("lbl_flip_v", lambda c, v: setattr(c, "flip_v", v))
        self.cmb_blend = self._combo(BLENDS, lambda c, v: setattr(c, "blend_mode", v))
        self.cmb_mask = self._combo(MASKS, lambda c, v: setattr(c.mask, "shape", v))
        self.sp_feather = self._spin(0, 100, 1, lambda c, v: setattr(c.mask, "feather", v))
        self.cb_chroma = self._check("lbl_chroma_enable", lambda c, v: setattr(c.chroma, "enabled", v))
        self.le_chroma = self._hex_edit(lambda c, v: setattr(c.chroma, "key_color_hex", v))
        self.sp_sim = self._spin(0, 1, 0.01, lambda c, v: setattr(c.chroma, "similarity", v), 2)
        self.sp_blend = self._spin(0, 1, 0.01, lambda c, v: setattr(c.chroma, "blend", v), 2)
        self.cb_stab = self._check("lbl_stabilize", self._set_stabilize)
        self.sp_crop = {
            side: self._spin(0, 45, 1, (lambda c, v, side=side: setattr(c, f"crop_{side}", v / 100.0)))
            for side in ("left", "right", "top", "bottom")
        }
        self._pair(f, "sh_x", self.sp_x, "sh_y", self.sp_y)
        self._pair(f, "sh_scale", self.sp_scale, "sh_rot", self.sp_rot)
        self._pair(f, "sh_opacity", self.sp_opacity, "sh_feather", self.sp_feather)
        flips = QHBoxLayout()
        flips.addWidget(self.cb_flip_h)
        flips.addWidget(self.cb_flip_v)
        flips.addWidget(self.cb_stab)
        f.addRow(flips)
        f.addRow(self._label("lbl_effect_intensity"), self.sp_effect_intensity)
        f.addRow(self._label("lbl_blend_mode"), self.cmb_blend)
        f.addRow(self._label("lbl_mask_shape"), self.cmb_mask)
        f.addRow(self.cb_chroma)
        f.addRow(self._label("lbl_chroma_color"), self.le_chroma)
        self._pair(f, "sh_sim", self.sp_sim, "sh_blend", self.sp_blend)
        self._pair(f, "sh_cl", self.sp_crop["left"], "sh_cr", self.sp_crop["right"])
        self._pair(f, "sh_ct", self.sp_crop["top"], "sh_cb", self.sp_crop["bottom"])

    def _set_stabilize(self, clip: TimelineClip, enabled: bool) -> None:
        clip.stabilize = bool(enabled)
        if enabled:
            # Analysis is scheduled by the main window; never run video analysis
            # inside the Qt signal handler/UI thread.
            self.host.prepare_stabilization(clip.id)
        else:
            self.host.cancel_stabilization(clip.id)

    # ---- tab 2: color ---------------------------------------------------
    def _build_color(self) -> None:
        _, f = self._page()
        self.color_spins: Dict[str, QDoubleSpinBox] = {}
        for attr, key, lo in (
            ("brightness", "lbl_brightness", -100),
            ("contrast", "lbl_contrast", -100),
            ("saturation", "lbl_saturation", -100),
            ("sharpness", "lbl_sharpness", 0),
            ("temperature", "lbl_temperature", -100),
            ("tint", "lbl_tint", -100),
            ("highlights", "lbl_highlights", -100),
            ("shadows", "lbl_shadows", -100),
        ):
            sp = self._spin(lo, 100, 1, lambda c, v, a=attr: setattr(c.color, a, v))
            self.color_spins[attr] = sp
        order = [("brightness", "sh_bright"), ("contrast", "sh_contrast"), ("saturation", "sh_sat"), ("sharpness", "sh_sharp"),
                 ("temperature", "sh_temp"), ("tint", "sh_tint"), ("highlights", "sh_hi"), ("shadows", "sh_sh")]
        for i in range(0, len(order), 2):
            (a1, k1), (a2, k2) = order[i], order[i + 1]
            self._pair(f, k1, self.color_spins[a1], k2, self.color_spins[a2])
        self.lbl_lut = QLabel("-")
        self.lbl_lut.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        f.addRow(self._label("lbl_lut_path"), self.lbl_lut)
        f.addRow(self._button("btn_reset_color", self._reset_color))

    def _reset_color(self) -> None:
        def _do(c: TimelineClip) -> None:
            lut = c.color.lut_path
            c.color = type(c.color)()
            c.color.lut_path = lut

        self._edit(_do)
        self.load_clip()

    # ---- tab 3: speed ---------------------------------------------------
    def _build_speed(self) -> None:
        _, f = self._page()
        self.sp_speed = self._spin(0.1, 100, 0.1, lambda c, v: setattr(c, "speed", v), 2)
        self.cb_pitch = self._check("lbl_keep_pitch", lambda c, v: setattr(c, "keep_pitch", v))
        self.cb_reverse = self._check("lbl_reverse_clip", lambda c, v: setattr(c, "reverse", v))
        self.cmb_curve = self._combo(CURVES, lambda c, v: setattr(c, "speed_curve", v))
        f.addRow(self._label("lbl_speed_mult"), self.sp_speed)
        f.addRow(self.cb_pitch)
        f.addRow(self.cb_reverse)
        f.addRow(self._label("lbl_speed_curve"), self.cmb_curve)
        f.addRow(self._button("btn_freeze_frame", self._freeze))

    def _freeze(self) -> None:
        clip = self.c.get_selected_clip()
        if clip is not None and self.c.project.freeze_frame_at(clip.id):
            self.host.refresh_all()

    # ---- tab 4: audio ---------------------------------------------------
    def _build_audio(self) -> None:
        _, f = self._page()
        self.sp_vol = self._spin(-60, 24, 1, lambda c, v: setattr(c, "volume_db", v))
        self.sp_fin = self._spin(0, 30, 0.1, lambda c, v: setattr(c, "fade_in", v))
        self.sp_fout = self._spin(0, 30, 0.1, lambda c, v: setattr(c, "fade_out", v))
        self.sp_pitch = self._spin(-12, 12, 1, lambda c, v: setattr(c, "pitch_semitones", v))
        self.cmb_eq = self._combo(EQS, lambda c, v: setattr(c, "eq_preset", v))
        self.cb_ducking = QCheckBox(tr("auto_ducking", self.c.lang))
        self.cb_ducking.toggled.connect(self._set_auto_ducking)
        self._i18n.append((self.cb_ducking, "auto_ducking", "setText"))
        f.addRow(self.cb_ducking)
        self._pair(f, "sh_vol", self.sp_vol, "sh_pitch", self.sp_pitch)
        self._pair(f, "sh_fin", self.sp_fin, "sh_fout", self.sp_fout)
        f.addRow(self._label("lbl_eq_preset"), self.cmb_eq)
        f.addRow(self._button("btn_detach_audio", self._detach))

    def _set_auto_ducking(self, enabled: bool) -> None:
        if self._loading:
            return
        self.c.project.push_undo_snapshot()
        self.c.project.auto_ducking = bool(enabled)
        self.host.refresh_all()

    def _detach(self) -> None:
        clip = self.c.get_selected_clip()
        if clip is not None and self.c.project.detach_audio_from_clip(clip.id):
            self.host.refresh_all()

    # ---- tab 5: keyframes & text ---------------------------------------
    def _build_keyframes(self) -> None:
        _, f = self._page()
        self.cmb_kf_prop = QComboBox()
        self._combos.append((self.cmb_kf_prop, KF_PROPS))
        self.cmb_kf_ease = QComboBox()
        self._combos.append((self.cmb_kf_ease, EASINGS))
        f.addRow(self._label("lbl_kf_property"), self.cmb_kf_prop)
        f.addRow(self._label("lbl_kf_easing"), self.cmb_kf_ease)
        self.kf_curve = KeyframeCurveWidget(self.host)
        f.addRow(self.kf_curve)
        self.cmb_kf_prop.currentIndexChanged.connect(self._sync_keyframe_curve)
        f.addRow(self._button("btn_add_keyframe", self._add_keyframe))
        f.addRow(self._button("btn_clear_keyframes", self._clear_keyframes))
        self.lbl_none = self._label("no_clip_selected")
        f.addRow(self.lbl_none)

    def _sync_keyframe_curve(self, *_: Any) -> None:
        self.kf_curve.set_curve(self.c.get_selected_clip(), str(self.cmb_kf_prop.currentData()))

    def _add_keyframe(self) -> None:
        clip = self.c.get_selected_clip()
        if clip is None:
            return
        prop = str(self.cmb_kf_prop.currentData())
        local_t = max(0.0, self.c.project.playhead_sec - clip.timeline_start)
        if prop.startswith("color."):
            current_value = float(getattr(clip.color, prop.split(".", 1)[1]))
        else:
            current_value = float(getattr(clip, prop))
        self.c.project.add_keyframe(clip.id, prop, local_t, current_value, str(self.cmb_kf_ease.currentData()))
        self.host.refresh_all()

    def _clear_keyframes(self) -> None:
        clip = self.c.get_selected_clip()
        if clip is None:
            return
        self.c.project.push_undo_snapshot()
        clip.keyframes.pop(str(self.cmb_kf_prop.currentData()), None)
        self.host.refresh_all()

    # ---- tab 6: motion (In / Out / Loop animations for any visual clip, stickers included) ----------
    def _build_anim(self) -> None:
        _, f = self._page()

        def items(keys: Tuple[str, ...], prefix: str) -> List[Tuple[str, str]]:
            return [(k, "anim_none" if k == "none" else prefix + k) for k in keys]

        self.cmb_ain = self._combo(items(ANIM_IN_KEYS, "anim_"), lambda c, v: setattr(c, "anim_in", v))
        self.cmb_aout = self._combo(items(ANIM_OUT_KEYS, "anim_"), lambda c, v: setattr(c, "anim_out", v))
        self.cmb_aloop = self._combo(items(ANIM_LOOP_KEYS, "loop_"), lambda c, v: setattr(c, "anim_loop", v))
        self.sp_adur = self._spin(0.1, 3.0, 0.1, lambda c, v: setattr(c, "anim_duration", v), 1)
        f.addRow(self._label("lbl_anim_in"), self.cmb_ain)
        f.addRow(self._label("lbl_anim_out"), self.cmb_aout)
        f.addRow(self._label("lbl_anim_loop"), self.cmb_aloop)
        f.addRow(self._label("lbl_anim_duration"), self.sp_adur)
        f.addRow(self._button("btn_anim_clear", self._clear_anim))

    def _clear_anim(self) -> None:
        def _do(c: TimelineClip) -> None:
            c.anim_in = c.anim_out = c.anim_loop = "none"

        self._edit(_do)
        self.load_clip()

    # ---- sync with selected clip ---------------------------------------
    def load_clip(self) -> None:
        clip = self.c.get_selected_clip()
        self._loading = True
        try:
            self.setEnabled(clip is not None)
            self.lbl_none.setVisible(clip is None)
            self.cb_ducking.setChecked(bool(self.c.project.auto_ducking))
            if clip is None:
                return
            self.sp_x.setValue(clip.pos_x)
            self.sp_y.setValue(clip.pos_y)
            self.sp_scale.setValue(clip.scale)
            self.sp_rot.setValue(clip.rotation)
            self.sp_opacity.setValue(clip.opacity)
            self.sp_effect_intensity.setValue(clip.effect_intensity)
            self.cb_flip_h.setChecked(clip.flip_h)
            self.cb_flip_v.setChecked(clip.flip_v)
            self.cmb_blend.setCurrentIndex(max(0, self.cmb_blend.findData(clip.blend_mode)))
            self.cmb_mask.setCurrentIndex(max(0, self.cmb_mask.findData(clip.mask.shape)))
            self.sp_feather.setValue(clip.mask.feather)
            self.cb_chroma.setChecked(clip.chroma.enabled)
            self.le_chroma.setText(clip.chroma.key_color_hex)
            self.sp_sim.setValue(clip.chroma.similarity)
            self.sp_blend.setValue(clip.chroma.blend)
            self.cb_stab.setEnabled(clip.clip_type == "video")
            self.cb_stab.setChecked(clip.stabilize if clip.clip_type == "video" else False)
            for side, sp in self.sp_crop.items():
                sp.setValue(getattr(clip, f"crop_{side}") * 100.0)
            for attr, sp in self.color_spins.items():
                sp.setValue(getattr(clip.color, attr))
            self.lbl_lut.setText(Path(clip.color.lut_path).name if clip.color.lut_path else "-")
            self.sp_speed.setValue(clip.speed)
            self.cb_pitch.setChecked(clip.keep_pitch)
            self.cb_reverse.setChecked(clip.reverse)
            self.cmb_curve.setCurrentIndex(max(0, self.cmb_curve.findData(clip.speed_curve)))
            self.sp_vol.setValue(clip.volume_db)
            self.sp_fin.setValue(clip.fade_in)
            self.sp_fout.setValue(clip.fade_out)
            self.sp_pitch.setValue(clip.pitch_semitones)
            self.cmb_eq.setCurrentIndex(max(0, self.cmb_eq.findData(clip.eq_preset)))
            self.cmb_ain.setCurrentIndex(max(0, self.cmb_ain.findData(clip.anim_in)))
            self.cmb_aout.setCurrentIndex(max(0, self.cmb_aout.findData(clip.anim_out)))
            self.cmb_aloop.setCurrentIndex(max(0, self.cmb_aloop.findData(clip.anim_loop)))
            self.sp_adur.setValue(clip.anim_duration)
        finally:
            self._loading = False
            self.kf_curve.set_curve(clip, str(self.cmb_kf_prop.currentData()))
            self.text_panel.load_clip()

    def retranslate(self) -> None:
        lang = self.c.lang
        for widget, key, setter in self._i18n:
            getattr(widget, setter)(tr(key, lang))
        for combo, items in self._combos:
            _fill_combo(combo, items, lang)
        for i, (k, fk) in enumerate([("insptab_video", "insp_tab_video"), ("insptab_color", "insp_tab_color"), ("insptab_speed", "insp_tab_speed"),
                                     ("insptab_audio", "insp_tab_audio"), ("insptab_keys", "insp_tab_keyframes"), ("insptab_anim", "ctx_animation"),
                                     ("insptab_text", "insp_tab_text")]):
            self.setTabText(i, tr(k, lang))
            self.setTabToolTip(i, tr(fk, lang))
        self.text_panel.retranslate()
        self.load_clip()

    def show_for_clip(self, clip_id: str, focus_text: bool = False) -> None:
        """Bring the right inspector tab forward (Text tab for text clips) after a click / double-click."""
        clip = self.c.get_selected_clip()
        if clip is None:
            return
        self.load_clip()
        if clip.clip_type == "text":
            self.setCurrentIndex(6)
            if focus_text:
                self.text_panel.focus_text()
        elif self.currentIndex() == 6:
            self.setCurrentIndex(0)
