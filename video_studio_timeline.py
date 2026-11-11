# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Interactive preview canvas and multi-track timeline widgets.

Features: click-to-select on the preview (text/video), drag to move, corner-drag to scale,
double-click to edit, right-click menus; timeline with multi-select, trim handles,
drag between tracks, wheel scroll/zoom, adaptive ruler, and rich context menus for
clips, track headers, the ruler and empty lanes. Requires PyQt6.
"""

import json
import os
import threading
from pathlib import Path
from collections import OrderedDict
from queue import Empty, Queue
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QObject, QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QInputDialog, QMenu, QScrollBar, QWidget

from video_studio_core import ANIM_IN_KEYS, ANIM_LOOP_KEYS, ANIM_OUT_KEYS, VideoStudioProject, close_reader_pool, generate_thumbnail, track_accepts
from video_studio_i18n import tr, track_display_name
from video_studio_stickers import clip_display_name
from video_studio_theme import get_effective_palette

STICKER_MIME = "application/x-hmz-sticker"  # internal drag from the Stickers panel: JSON {"sticker_id", "sticker_color"} or {}

EFFECT_KEYS = [
    ("none", "effect_none"), ("warm_film", "effect_warm_film"), ("cyber_teal", "effect_cyber_teal"),
    ("vintage_bw", "effect_vintage_bw"), ("vhs_glitch", "effect_vhs_glitch"), ("motion_blur", "effect_motion_blur"),
    ("camera_shake", "effect_camera_shake"), ("vignette", "effect_vignette"),
    ("gaussian_blur", "effect_gaussian_blur"), ("pixelate", "effect_pixelate"),
    ("invert", "effect_invert"), ("sepia", "effect_sepia"), ("negative_film", "effect_negative_film"),
]
TRANS_KEYS = [
    ("none", "trans_none"), ("crossfade", "trans_crossfade"), ("fade_black", "trans_fade_black"),
    ("wipe_left", "trans_wipe_left"), ("slide", "trans_slide"), ("zoom_in", "trans_zoom_in"),
    ("wipe_right", "trans_wipe_right"), ("wipe_up", "trans_wipe_up"), ("wipe_down", "trans_wipe_down"),
    ("circle_reveal", "trans_circle"), ("diamond", "trans_diamond"), ("blinds", "trans_blinds"),
    ("checkerboard", "trans_checkerboard"), ("push_left", "trans_push_left"), ("push_right", "trans_push_right"),
    ("push_up", "trans_push_up"), ("push_down", "trans_push_down"), ("rotate_in", "trans_rotate"),
    ("blur_in", "trans_blur"), ("flash", "trans_flash"),
]
SPEEDS = (0.25, 0.5, 1.0, 1.5, 2.0, 4.0)
TRACK_GLYPH = {"video": "🎞", "sticker": "✨", "text": "Aa", "audio": "🎵"}
CLIP_COLORS = {"video": "#155E75", "image": "#1D4ED8", "audio": "#065F46", "text": "#6D28D9", "sticker": "#9D174D"}


def _palette(controller: Any) -> Dict[str, str]:
    return get_effective_palette(controller.settings.data.get("theme", "dark"), controller.settings.data.get("accent", "cyan"))


def bgr_to_qimage(bgr: np.ndarray) -> QImage:
    """BGR uint8 array -> detached QImage without a channel-swap copy (Qt reads BGR directly)."""
    arr = np.ascontiguousarray(bgr)
    h, w = arr.shape[:2]
    return QImage(arr.data, w, h, int(arr.strides[0]), QImage.Format.Format_BGR888).copy()


def build_clip_menu(host: Any, clip_id: str, parent: QWidget) -> Optional[QMenu]:
    """Shared right-click menu for a clip (used by the timeline and the preview)."""
    c = host.controller
    lang = c.lang
    found = c.project.find_clip(clip_id)
    if not found:
        return None
    trk, clip = found
    menu = QMenu(parent)

    def add(label_key: str, slot: Any, checked: Optional[bool] = None, enabled: bool = True, target: Optional[QMenu] = None, text: Optional[str] = None) -> Any:
        act = (target or menu).addAction(text if text is not None else tr(label_key, lang))
        if checked is not None:
            act.setCheckable(True)
            act.setChecked(checked)
        act.setEnabled(enabled)
        act.triggered.connect(lambda _=False: slot())
        return act

    add("ctx_properties", lambda: host.open_inspector_for(clip_id, focus_text=False))
    if clip.clip_type == "text":
        add("ctx_edit_text", lambda: host.open_inspector_for(clip_id, focus_text=True))
        if (clip.ai_metadata or {}).get("transcript_source_clip_id"):
            add("ctx_cut_transcript", lambda: (c.project.remove_transcript_segment(clip_id), host.refresh_all()))
    menu.addSeparator()
    add("ctx_split", host.split_at_playhead)
    t = c.project.playhead_sec
    inside = clip.timeline_start + 0.1 < t < clip.timeline_end - 0.1
    add("ctx_trim_start", lambda: host.trim_to_playhead(clip_id, "start"), enabled=inside)
    add("ctx_trim_end", lambda: host.trim_to_playhead(clip_id, "end"), enabled=inside)
    menu.addSeparator()
    add("ctx_copy", host.copy_selected)
    add("ctx_cut", host.cut_selected)
    add("ctx_paste", lambda: host.paste_clipboard(trk.id, c.project.playhead_sec), enabled=bool(c.clipboard))
    add("ctx_duplicate", host.duplicate_selected)
    menu.addSeparator()
    add("ctx_delete", host.delete_selected, enabled=not trk.locked)
    add("ctx_ripple_delete", host.ripple_delete_selected, enabled=not trk.locked)
    menu.addSeparator()
    if clip.clip_type in ("video", "audio"):
        sp = menu.addMenu(tr("ctx_speed", lang))
        for v in SPEEDS:
            add("", lambda v=v: host.set_speed_selected(v), checked=abs(clip.speed - v) < 1e-6, target=sp, text=f"{v:g}x")
        add("ctx_reverse", lambda: host.toggle_clip_flag("reverse"), checked=clip.reverse, enabled=clip.clip_type == "video")
        add("ctx_mute_clip", lambda: host.toggle_clip_flag("muted"), checked=clip.muted)
        add("ctx_fade_in", lambda: host.set_clip_value("fade_in", 0.5))
        add("ctx_fade_out", lambda: host.set_clip_value("fade_out", 0.5))
        if clip.clip_type == "video":
            add("ctx_freeze", host.freeze_selected)
            add("ctx_detach", host.detach_selected)
    if clip.clip_type != "audio":
        tm = menu.addMenu(tr("ctx_transition", lang))
        for key, lbl in TRANS_KEYS:
            add(lbl, lambda key=key: host.set_clip_value("transition_in", key), checked=clip.transition_in == key, target=tm)
        am = menu.addMenu(tr("ctx_animation", lang))
        for title_key, attr, keys, prefix in (("ctx_anim_in", "anim_in", ANIM_IN_KEYS, "anim_"), ("ctx_anim_out", "anim_out", ANIM_OUT_KEYS, "anim_"), ("ctx_anim_loop", "anim_loop", ANIM_LOOP_KEYS, "loop_")):
            sub = am.addMenu(tr(title_key, lang))
            for key in keys:
                lbl = tr("anim_none" if key == "none" else prefix + key, lang)
                add("", lambda a=attr, k=key: host.set_clip_value(a, k), checked=getattr(clip, attr) == key, target=sub, text=lbl)
        em = menu.addMenu(tr("ctx_effect", lang))
        for key, lbl in EFFECT_KEYS:
            add(lbl, lambda key=key: host.set_clip_value("visual_effect", key), checked=clip.visual_effect == key, target=em)
        if clip.clip_type != "text":
            add("ctx_flip_h", lambda: host.toggle_clip_flag("flip_h"), checked=clip.flip_h)
        add("ctx_reset_transform", host.reset_transform_selected)
    menu.addSeparator()
    add("ctx_lock_track", lambda: host.set_track_flag(trk.id, "locked", not trk.locked), checked=trk.locked)
    return menu


class _FrameBus(QObject):
    frame_ready = pyqtSignal(object, int)  # (QImage, request token)


class _FrameWorker:
    """Renders preview frames on one long-lived background thread. Only the newest request is kept ("latest wins"),
    so dragging or playing never queues up stale frames and the UI thread never waits for video decoding."""

    def __init__(self, bus: _FrameBus):
        self._bus = bus
        self._cv = threading.Condition()
        self._req: Optional[Tuple[Any, float, float, int, Optional[str]]] = None
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="HMZ-preview", daemon=True)
        self._thread.start()

    def request(self, project_json: str, t: float, scale: float, token: int, stabilization_cache_dir: Optional[str] = None) -> None:
        # The JSON was captured on the UI thread. The worker reconstructs its own project so UI edits
        # can never race with rendering or mutate objects being read by OpenCV/Pillow.
        with self._cv:
            self._req = (project_json, t, scale, token, stabilization_cache_dir)
            self._cv.notify()

    def stop(self) -> None:
        with self._cv:
            self._stop = True
            self._req = None
            self._cv.notify_all()

    def join(self, timeout: Optional[float] = None) -> None:
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        try:
            while True:
                with self._cv:
                    while self._req is None and not self._stop:
                        self._cv.wait()
                    if self._stop:
                        return
                    project_json, t, scale, token, cache_dir = self._req  # type: ignore[misc]
                    self._req = None
                try:
                    project = VideoStudioProject()
                    project.load_from_json_string(project_json)
                    project.stabilization_cache_dir = Path(cache_dir) if cache_dir else None
                    img = bgr_to_qimage(project.render_composite_frame(t, preview_scale=scale, use_proxy=True))
                except Exception:
                    continue
                try:
                    self._bus.frame_ready.emit(img, token)
                except RuntimeError:  # the widget was destroyed while rendering
                    return
        finally:
            close_reader_pool()


class PreviewCanvasWidget(QWidget):
    clip_selected = pyqtSignal(str)
    edit_requested = pyqtSignal(str)
    clip_moved = pyqtSignal(float, float)
    clip_changed = pyqtSignal()

    HANDLE = 7.0

    def __init__(self, controller: Any, host: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.controller = controller
        self.host = host
        self.setMinimumSize(240, 140)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self._mode = ""  # "", "move", "scale"
        self._last = QPointF()
        self._start_scale = 100.0
        self._start_dist = 1.0
        self._moved = False
        self._image: Optional[QImage] = None
        self._pix: Optional[QPixmap] = None
        self._img_rect = QRectF()
        self._token = 0
        self._shown_token = 0
        self._bus = _FrameBus(self)
        self._bus.frame_ready.connect(self._on_frame)
        self._worker = _FrameWorker(self._bus)

    # ---- rendering ------------------------------------------------------
    def refresh_frame(self, sync: bool = False) -> None:
        """Ask for a fresh preview frame. Rendering happens on a worker thread (the UI never blocks on decoding);
        `sync=True` renders right here, used only for the very first paint."""
        proj = self.controller.project
        scale = self.controller.preview_quality_scale
        self._token += 1
        if sync:
            self._set_image(bgr_to_qimage(proj.render_composite_frame(proj.playhead_sec, preview_scale=scale, use_proxy=True)), self._token)
            return
        snapshot = proj._snapshot_string() if hasattr(proj, "_snapshot_string") else proj.to_json_string()
        cache_dir = str(proj.stabilization_cache_dir) if proj.stabilization_cache_dir else None
        self._worker.request(snapshot, proj.playhead_sec, scale, self._token, cache_dir)

    def _set_image(self, img: QImage, token: int) -> None:
        self._shown_token = token
        self._image = img
        self._pix = QPixmap.fromImage(img)  # converted once per frame, not once per paint
        self.update()

    def _on_frame(self, img: Any, token: int) -> None:
        if token >= self._shown_token:
            self._set_image(img, token)

    def shutdown(self) -> None:
        self._worker.stop()
        self._worker.join(timeout=2.0)

    def _compute_rect(self) -> QRectF:
        base_w, base_h = self.controller.project.canvas_size
        avail = QRectF(6, 6, max(10, self.width() - 12), max(10, self.height() - 12))
        ratio = base_w / float(base_h)
        w = avail.width()
        h = w / ratio
        if h > avail.height():
            h = avail.height()
            w = h * ratio
        return QRectF(avail.x() + (avail.width() - w) / 2, avail.y() + (avail.height() - h) / 2, w, h)

    def _to_canvas(self, p: QPointF) -> Tuple[float, float]:
        bw, bh = self.controller.project.canvas_size
        r = self._img_rect
        return (p.x() - r.x()) / max(1.0, r.width()) * bw, (p.y() - r.y()) / max(1.0, r.height()) * bh

    def _from_canvas(self, x: float, y: float) -> QPointF:
        bw, bh = self.controller.project.canvas_size
        r = self._img_rect
        return QPointF(r.x() + x / bw * r.width(), r.y() + y / bh * r.height())

    def _selected_bounds(self) -> Optional[QRectF]:
        cid = self.controller.selected_clip_id
        if not cid:
            return None
        b = self.controller.project.clip_canvas_bounds(cid)
        if not b:
            return None
        a, d = self._from_canvas(b[0], b[1]), self._from_canvas(b[2], b[3])
        return QRectF(a, d)

    def paintEvent(self, event: Any) -> None:
        pal = _palette(self.controller)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor(pal["canvas_bg"]))
        if self._pix is None:
            # Never decode media synchronously from paintEvent. The first frame is
            # already requested by show_editor(); this fallback covers rare cases
            # where the widget is painted before that request was queued.
            if self._token == 0:
                try:
                    self.refresh_frame()
                except Exception:
                    pass
            return
        self._img_rect = self._compute_rect()
        painter.drawPixmap(self._img_rect.toRect(), self._pix)
        painter.setPen(QPen(QColor(pal["border"]), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._img_rect)
        box = self._selected_bounds()
        if box is not None:
            painter.setClipRect(self._img_rect.adjusted(-8, -8, 8, 8))
            painter.setPen(QPen(QColor(pal["accent"]), 1.6, Qt.PenStyle.DashLine))
            painter.drawRect(box)
            painter.setBrush(QColor(pal["accent"]))
            painter.setPen(Qt.PenStyle.NoPen)
            for pt in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
                painter.drawRect(QRectF(pt.x() - self.HANDLE / 2, pt.y() - self.HANDLE / 2, self.HANDLE, self.HANDLE))

    # ---- interaction ----------------------------------------------------
    def _corner_hit(self, pos: QPointF) -> bool:
        box = self._selected_bounds()
        if box is None:
            return False
        for pt in (box.topLeft(), box.topRight(), box.bottomLeft(), box.bottomRight()):
            if abs(pt.x() - pos.x()) <= self.HANDLE and abs(pt.y() - pos.y()) <= self.HANDLE:
                return True
        return False

    def _clip_under(self, pos: QPointF) -> Optional[str]:
        x, y = self._to_canvas(pos)
        return self.controller.project.clip_at_point(x, y)

    def mousePressEvent(self, event: Any) -> None:
        pos = event.position()
        if not self._img_rect.contains(pos) and not self._corner_hit(pos):
            return
        if event.button() == Qt.MouseButton.LeftButton:
            sel = self.controller.get_selected_clip()
            if sel is not None and self._corner_hit(pos):
                box = self._selected_bounds()
                assert box is not None
                ctr = box.center()
                self._mode = "scale"
                self._start_scale = sel.scale
                self._start_dist = max(4.0, ((pos.x() - ctr.x()) ** 2 + (pos.y() - ctr.y()) ** 2) ** 0.5)
                self._moved = False
                return
            cid = self._clip_under(pos)
            if cid is None:
                self.controller.select_clip(None)
                self.clip_selected.emit("")
                self.update()
                return
            additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.controller.select_clip(cid, toggle=additive)
            self.clip_selected.emit(cid)
            self._mode = "move"
            self._last = pos
            self._moved = False
            self.update()

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.position()
        clip = self.controller.get_selected_clip()
        if self._mode and clip is not None:
            if not self._moved:
                self.controller.project.push_undo_snapshot()
                self._moved = True
            if self._mode == "move":
                bw, _bh = self.controller.project.canvas_size
                k = bw / max(1.0, self._img_rect.width())
                clip.pos_x = round(clip.pos_x + (pos.x() - self._last.x()) * k, 1)
                clip.pos_y = round(clip.pos_y + (pos.y() - self._last.y()) * k, 1)
                self._last = pos
                self.clip_moved.emit(clip.pos_x, clip.pos_y)
            else:
                box = self._selected_bounds()
                if box is not None:
                    ctr = box.center()
                    dist = max(4.0, ((pos.x() - ctr.x()) ** 2 + (pos.y() - ctr.y()) ** 2) ** 0.5)
                    clip.scale = round(max(5.0, min(800.0, self._start_scale * dist / self._start_dist)), 1)
                    self.clip_changed.emit()
            self.refresh_frame()
            return
        if clip is not None and self._corner_hit(pos):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif self._img_rect.contains(pos) and self._clip_under(pos) is not None:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        else:
            self.unsetCursor()

    def mouseReleaseEvent(self, event: Any) -> None:
        was = self._mode
        self._mode = ""
        if was and self._moved:
            self.clip_changed.emit()

    def mouseDoubleClickEvent(self, event: Any) -> None:
        cid = self._clip_under(event.position())
        if cid:
            self.controller.select_clip(cid)
            self.edit_requested.emit(cid)

    def contextMenuEvent(self, event: Any) -> None:
        cid = self._clip_under(QPointF(event.pos()))
        if cid is None:
            return
        if cid not in self.controller.selected_ids:
            self.controller.select_clip(cid)
            self.clip_selected.emit(cid)
        menu = build_clip_menu(self.host, cid, self)
        if menu is not None:
            menu.exec(event.globalPos())


class ThumbnailCache:
    """Generates clip thumbnails on a background thread so painting never blocks on video decoding."""

    TILE_H = 36

    def __init__(self, on_ready: Any):
        self._cache: "OrderedDict[Tuple[str, float], Optional[QImage]]" = OrderedDict()
        self._pending: set = set()
        self._queue: "Queue[Tuple[str, float]]" = Queue()
        self._on_ready = on_ready
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def get(self, path: str, t: float) -> Optional[QImage]:
        key = (path, round(t, 1))
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            if key not in self._pending:
                self._pending.add(key)
                self._queue.put(key)
                self._ensure_thread()
        return None

    def _ensure_thread(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._work, daemon=True)
            self._thread.start()

    def _work(self) -> None:
        try:
            while True:
                try:
                    path, t = self._queue.get(timeout=2.0)
                except Empty:
                    return
                img: Optional[QImage] = None
                try:
                    arr = generate_thumbnail(path, t, self.TILE_H)
                    if arr is not None:
                        img = bgr_to_qimage(arr)
                except Exception:
                    img = None
                with self._lock:
                    self._pending.discard((path, t))
                    self._cache[(path, t)] = img
                    while len(self._cache) > 400:
                        self._cache.popitem(last=False)
                # tell the UI only when the queue is drained or every few tiles: avoids a repaint per thumbnail
                if self._queue.empty() or len(self._cache) % 6 == 0:
                    try:
                        self._on_ready()
                    except Exception:
                        return
        finally:
            close_reader_pool()


class MultiTrackTimelineWidget(QWidget):
    thumbs_ready = pyqtSignal()
    clip_selected = pyqtSignal(str)
    clip_edit_requested = pyqtSignal(str)
    playhead_changed = pyqtSignal(float)
    timeline_modified = pyqtSignal()
    zoom_changed = pyqtSignal(float)

    HEADER_WIDTH = 122
    RULER_HEIGHT = 24
    TRACK_HEIGHT = 46
    H_SCROLLBAR_HEIGHT = 14
    EDGE = 7
    MIN_ZOOM = 4.0
    MAX_ZOOM = 300.0
    BTN_W = 22
    BTN_H = 16

    def __init__(self, controller: Any, host: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.controller = controller
        self.host = host
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(120)
        self.pixels_per_sec = 65.0
        self.scroll_x = 0.0
        self.scroll_y = 0.0
        self.selected_track_id = ""
        self._mode = ""  # playhead | move | trim_l | trim_r
        self._press_sec = 0.0
        self._orig: Dict[str, Tuple[float, float]] = {}
        self._primary = ""
        self._moved = False
        self._drop_hint: Optional[Tuple[int, float]] = None
        self._thumbs = ThumbnailCache(self.thumbs_ready.emit)
        self._thumb_version = 0
        self.thumbs_ready.connect(self._on_thumbs_ready)
        # the heavy part (lanes, clips, thumbnails, waveforms, ruler, headers) is painted into this pixmap and only
        # re-painted when something visible changed; during playback only the playhead line is drawn on top of it
        self._cache: Optional[QPixmap] = None
        self._cache_sig: Any = None

        # A visible vertical scrollbar makes lower tracks discoverable without
        # requiring modifier keys. It is kept inside the timeline widget so
        # the ruler and track headers remain aligned.
        self.v_scrollbar = QScrollBar(Qt.Orientation.Vertical, self)
        self.v_scrollbar.setObjectName("TimelineVerticalScrollBar")
        self.v_scrollbar.setFixedWidth(14)
        self.v_scrollbar.setRange(0, 0)
        self.v_scrollbar.valueChanged.connect(self._on_vertical_scrollbar)
        self.v_scrollbar.hide()

        # A dedicated horizontal scrollbar makes the full duration reachable
        # without requiring Shift+wheel (which differs across input devices).
        self.h_scrollbar = QScrollBar(Qt.Orientation.Horizontal, self)
        self.h_scrollbar.setObjectName("TimelineHorizontalScrollBar")
        self.h_scrollbar.setFixedHeight(self.H_SCROLLBAR_HEIGHT)
        self.h_scrollbar.setRange(0, 0)
        self.h_scrollbar.valueChanged.connect(self._on_horizontal_scrollbar)
        self.h_scrollbar.show()
        self._clamp_scroll()

    def _viewport_bottom(self) -> int:
        return max(self.RULER_HEIGHT + 1, self.height() - self.H_SCROLLBAR_HEIGHT)

    def _viewport_right(self) -> int:
        reserved = self.v_scrollbar.width() if not self.v_scrollbar.isHidden() else 0
        return max(self.HEADER_WIDTH + 1, self.width() - reserved)

    def _on_thumbs_ready(self) -> None:
        self._thumb_version += 1
        self.update()

    def invalidate(self) -> None:
        self._cache_sig = None
        self.update()

    # ---- geometry ---------------------------------------------------------
    def set_zoom(self, px_per_sec: float, anchor_x: Optional[float] = None) -> None:
        old = self.pixels_per_sec
        new = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(px_per_sec)))
        if anchor_x is not None and old > 0:
            sec_at = self.scroll_x + (anchor_x - self.HEADER_WIDTH) / old
            self.scroll_x = max(0.0, sec_at - (anchor_x - self.HEADER_WIDTH) / new)
        self.pixels_per_sec = new
        self._clamp_scroll()
        self.update()

    def fit_to_view(self) -> None:
        """Zoom so the whole project fits the visible width (CapCut's 'fit timeline')."""
        total = max(1.0, self.controller.project.total_duration())
        avail = max(60.0, self._viewport_right() - self.HEADER_WIDTH - 24.0)
        self.scroll_x = 0.0
        self.set_zoom(avail / total)
        self._clamp_scroll()
        self.zoom_changed.emit(self.pixels_per_sec)

    def _sec_to_x(self, sec: float) -> float:
        return self.HEADER_WIDTH + (sec - self.scroll_x) * self.pixels_per_sec

    def _x_to_sec(self, x: float) -> float:
        return max(0.0, self.scroll_x + (x - self.HEADER_WIDTH) / self.pixels_per_sec)

    def _track_y(self, idx: int) -> float:
        return self.RULER_HEIGHT + idx * self.TRACK_HEIGHT - self.scroll_y

    def _track_index_at(self, y: float) -> int:
        if y < self.RULER_HEIGHT or y >= self._viewport_bottom():
            return -1
        idx = int((y - self.RULER_HEIGHT + self.scroll_y) // self.TRACK_HEIGHT)
        return idx if 0 <= idx < len(self.controller.project.tracks) else -1

    def ensure_visible(self, sec: float) -> None:
        visible = max(1.0, (self._viewport_right() - self.HEADER_WIDTH) / self.pixels_per_sec)
        if sec < self.scroll_x or sec > self.scroll_x + visible - 0.5:
            self.scroll_x = max(0.0, sec - visible * 0.25)
            self._clamp_scroll()
            self.update()

    def _clamp_scroll(self) -> None:
        total = self.controller.project.total_duration() + 10
        content_h = len(self.controller.project.tracks) * self.TRACK_HEIGHT
        view_h = max(1, self._viewport_bottom() - self.RULER_HEIGHT)
        max_scroll = max(0.0, content_h - view_h)
        self.scroll_y = max(0.0, min(self.scroll_y, max_scroll))
        bar = getattr(self, "v_scrollbar", None)
        if bar is not None:
            bar.blockSignals(True)
            bar.setPageStep(view_h)
            bar.setSingleStep(self.TRACK_HEIGHT)
            bar.setRange(0, int(max_scroll))
            bar.setValue(int(round(self.scroll_y)))
            bar.blockSignals(False)
            bar.setVisible(max_scroll > 0)
            bar.setGeometry(max(0, self.width() - bar.width()), self.RULER_HEIGHT,
                            bar.width(), view_h)

        visible_width = max(1, self._viewport_right() - self.HEADER_WIDTH)
        visible_seconds = visible_width / max(0.01, self.pixels_per_sec)
        max_scroll_x = max(0.0, total - visible_seconds)
        self.scroll_x = max(0.0, min(self.scroll_x, max_scroll_x))
        hbar = getattr(self, "h_scrollbar", None)
        if hbar is not None:
            # Scrollbar units are milliseconds; editor geometry remains seconds.
            hbar.blockSignals(True)
            hbar.setPageStep(max(1, int(round(visible_seconds * 1000))))
            hbar.setSingleStep(250)
            hbar.setRange(0, int(round(max_scroll_x * 1000)))
            hbar.setValue(int(round(self.scroll_x * 1000)))
            hbar.blockSignals(False)
            hbar.setGeometry(self.HEADER_WIDTH, self.height() - self.H_SCROLLBAR_HEIGHT,
                             visible_width, self.H_SCROLLBAR_HEIGHT)

    # ---- track header controls -------------------------------------------------
    @staticmethod
    def _header_buttons(trk: Any) -> List[Tuple[str, str, str]]:
        """(flag, glyph when off, glyph when on) for the quick toggles that make sense for this kind of track."""
        if trk.track_type == "audio":
            return [("muted", "🔊", "🔇"), ("locked", "🔓", "🔒")]
        if trk.track_type == "video":
            return [("muted", "🔊", "🔇"), ("hidden", "👁", "🚫"), ("locked", "🔓", "🔒")]
        return [("hidden", "👁", "🚫"), ("locked", "🔓", "🔒")]

    def _header_button_rects(self, idx: int, trk: Any) -> List[Tuple[str, QRectF]]:
        ty = self._track_y(idx)
        y = ty + self.TRACK_HEIGHT - 4 - self.BTN_H
        return [(flag, QRectF(8 + i * (self.BTN_W + 4), y, self.BTN_W, self.BTN_H)) for i, (flag, _a, _b) in enumerate(self._header_buttons(trk))]

    # ---- painting ---------------------------------------------------------
    def _signature(self) -> Any:
        """Everything the cached pixmap depends on, as one hashable value (cheap: one tuple per clip)."""
        c = self.controller
        proj = c.project
        parts: List[Any] = [
            self.width(), self.height(), round(self.devicePixelRatioF(), 2), round(self.scroll_x, 4), round(self.scroll_y, 2),
            round(self.pixels_per_sec, 3), c.lang, c.settings.data.get("theme"), c.settings.data.get("accent"),
            tuple(c.selected_ids), c.selected_clip_id, self.selected_track_id, self._thumb_version,
            tuple((m.time_sec, m.color_hex) for m in proj.markers),
        ]
        for trk in proj.tracks:
            parts.append((trk.id, trk.name, trk.track_type, trk.muted, trk.hidden, trk.locked))
            for cl in trk.clips:
                keyframes = tuple(sorted((key, tuple((round(k.time_offset, 4), round(k.value, 4)) for k in values))
                                         for key, values in cl.keyframes.items()))
                parts.append((cl.id, cl.timeline_start, cl.duration, cl.name, cl.clip_type, cl.source_path, cl.speed,
                              cl.transition_in, cl.source_in, cl.source_out, cl.effect_intensity, tuple(cl.waveform_peaks), keyframes,
                              cl.text_style.text if cl.clip_type == "text" else "", cl.muted,
                              str(cl.ai_metadata.get("sticker_id", ""))))
        return hash(tuple(parts))

    def paintEvent(self, event: Any) -> None:
        sig = self._signature()
        dpr = self.devicePixelRatioF()
        size = QSize(max(1, int(self.width() * dpr)), max(1, int(self.height() * dpr)))
        if self._cache is None or sig != self._cache_sig or self._cache.size() != size:
            pm = QPixmap(size)
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.GlobalColor.transparent)
            cp = QPainter(pm)
            try:
                self._paint_static(cp)
            finally:
                cp.end()
            self._cache, self._cache_sig = pm, sig
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._cache)
        self._paint_overlay(painter)

    def _paint_overlay(self, painter: QPainter) -> None:
        """Playhead + drop hint: the only things that change while playing."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        view_right = self._viewport_right()
        view_bottom = self._viewport_bottom()
        painter.save()
        painter.setClipRect(QRectF(0, 0, view_right, view_bottom))
        pal = _palette(self.controller)
        if self._drop_hint is not None:
            idx, sec = self._drop_hint
            hx = self._sec_to_x(sec)
            if idx >= 0:
                painter.fillRect(QRectF(self.HEADER_WIDTH, self._track_y(idx), view_right, self.TRACK_HEIGHT - 2), QColor(pal["accent"]).lighter(100).darker(250))
            painter.setPen(QPen(QColor(pal["accent"]), 1.6, Qt.PenStyle.DashLine))
            painter.drawLine(int(hx), self.RULER_HEIGHT, int(hx), view_bottom)
        px = self._sec_to_x(self.controller.project.playhead_sec)
        if self.HEADER_WIDTH <= px <= view_right:
            painter.setPen(QPen(QColor("#F43F5E"), 2.0))
            painter.drawLine(int(px), 0, int(px), view_bottom)
            painter.setBrush(QColor("#F43F5E"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPolygon([QPointF(px - 6, 0), QPointF(px + 6, 0), QPointF(px, 11)])
        painter.restore()

    def _paint_static(self, painter: QPainter) -> None:
        proj = self.controller.project
        lang = self.controller.lang
        pal = _palette(self.controller)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(0, 0, w, h, QColor(pal["timeline_bg"]))
        accent = QColor(pal["accent"])
        small = QFont(painter.font())
        if small.pointSizeF() > 0:
            small.setPointSizeF(max(7.5, small.pointSizeF() - 1.0))
        elif small.pixelSize() > 0:  # the stylesheet sets sizes in px
            small.setPixelSize(max(10, small.pixelSize() - 1))

        painter.save()
        view_right = self._viewport_right()
        view_bottom = self._viewport_bottom()
        painter.setClipRect(QRectF(self.HEADER_WIDTH, self.RULER_HEIGHT,
                                   view_right - self.HEADER_WIDTH, view_bottom - self.RULER_HEIGHT))
        for idx, trk in enumerate(proj.tracks):
            ty = self._track_y(idx)
            if ty > view_bottom or ty + self.TRACK_HEIGHT < self.RULER_HEIGHT:
                continue
            painter.fillRect(QRectF(self.HEADER_WIDTH, ty, view_right, self.TRACK_HEIGHT - 2), QColor(pal["track_lane_bg"]))
            for clip in trk.clips:
                cx = self._sec_to_x(clip.timeline_start)
                cw = max(14.0, clip.duration * self.pixels_per_sec)
                if cx + cw < self.HEADER_WIDTH or cx > view_right:
                    continue
                rect = QRectF(cx, ty + 3, cw, self.TRACK_HEIGHT - 8)
                col = QColor(CLIP_COLORS.get(clip.clip_type, "#155E75"))
                if trk.locked or trk.hidden or trk.muted:
                    col.setAlpha(120)
                path = QPainterPath()
                path.addRoundedRect(rect, 5.0, 5.0)
                painter.fillPath(path, col)
                if clip.clip_type in ("video", "image", "sticker") and cw > 26 and clip.source_path:
                    self._paint_thumbs(painter, clip, rect, path)
                if clip.waveform_peaks and cw > 24:
                    painter.setPen(QPen(QColor(255, 255, 255, 90), 1.0))
                    n = len(clip.waveform_peaks)
                    stride = max(1, int(n / max(1.0, cw / 2.0)))  # at most one line per 2 px
                    base_y = ty + self.TRACK_HEIGHT - 7
                    for i in range(0, n, stride):
                        px = cx + (i / max(1, n)) * cw
                        bh = clip.waveform_peaks[i] * (self.TRACK_HEIGHT - 22)
                        painter.drawLine(QPointF(px, base_y), QPointF(px, base_y - bh))
                if clip.transition_in != "none":
                    painter.setBrush(QColor(255, 255, 255, 150))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawPolygon([QPointF(cx, ty + 3), QPointF(cx + 11, ty + 3), QPointF(cx, ty + 14)])
                label = clip.text_style.text.replace("\n", " ") if clip.clip_type == "text" else clip_display_name(clip, lang)
                if clip.clip_type == "sticker" and not (clip.ai_metadata or {}).get("sticker_id"):
                    label = self.controller.sticker_label(os.path.basename(clip.source_path), lang) if hasattr(self.controller, "sticker_label") else label
                if abs(clip.speed - 1.0) > 0.01 and clip.clip_type not in ("text", "sticker"):
                    label += f"  {clip.speed:g}x"
                lx = cx + 5
                if clip.clip_type == "sticker":
                    lx = cx + 5 + (self.TRACK_HEIGHT - 12)  # label starts after the sticker icon
                painter.setFont(small)
                painter.setPen(QColor("#FFFFFF"))
                avail = int(cx + cw - lx - 4)
                if avail > 12:
                    painter.drawText(QRectF(lx, ty + 4, avail, 15), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(label, Qt.TextElideMode.ElideRight, avail))
                for kfl in clip.keyframes.values():
                    painter.setBrush(QColor("#FBBF24"))
                    painter.setPen(Qt.PenStyle.NoPen)
                    for kf in kfl:
                        kx = self._sec_to_x(clip.timeline_start + kf.time_offset)
                        painter.drawEllipse(QPointF(kx, ty + self.TRACK_HEIGHT - 9), 2.6, 2.6)
                if clip.id in self.controller.selected_ids:
                    primary = clip.id == self.controller.selected_clip_id
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(accent if primary else accent.lighter(130), 2.2 if primary else 1.4))
                    painter.drawPath(path)
                    painter.setBrush(accent)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(QRectF(cx, ty + 7, 4, self.TRACK_HEIGHT - 16), 2, 2)
                    painter.drawRoundedRect(QRectF(cx + cw - 4, ty + 7, 4, self.TRACK_HEIGHT - 16), 2, 2)
        painter.restore()

        # ruler
        painter.setFont(small)
        painter.fillRect(0, 0, w, self.RULER_HEIGHT, QColor(pal["panel_bg"]))
        step = next((s for s in (0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300) if s * self.pixels_per_sec >= 56), 600)
        painter.setPen(QColor(pal["text_muted"]))
        t = int(self.scroll_x // step) * step
        while self._sec_to_x(t) < view_right:
            x = self._sec_to_x(t)
            if x >= self.HEADER_WIDTH:
                painter.drawLine(int(x), self.RULER_HEIGHT - 7, int(x), self.RULER_HEIGHT)
                mm, ss = divmod(int(t), 60)
                painter.drawText(int(x) + 3, self.RULER_HEIGHT - 9, f"{mm:02d}:{ss:02d}" + (f".{int((t % 1) * 10)}" if t % 1 else ""))
            t += step
        for m in proj.markers:
            mx = self._sec_to_x(m.time_sec)
            if self.HEADER_WIDTH <= mx <= view_right:
                painter.setBrush(QColor(m.color_hex))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPolygon([QPointF(mx - 5, 2), QPointF(mx + 5, 2), QPointF(mx, 11)])

        # track headers: type glyph + localized name on the first line, quick toggles on the second
        glyph_font = QFont(small)
        painter.save()
        painter.setClipRect(QRectF(0, self.RULER_HEIGHT, self.HEADER_WIDTH, view_bottom - self.RULER_HEIGHT))
        for idx, trk in enumerate(proj.tracks):
            ty = self._track_y(idx)
            if ty > view_bottom or ty + self.TRACK_HEIGHT < self.RULER_HEIGHT:
                continue
            painter.fillRect(QRectF(0, ty, self.HEADER_WIDTH - 2, self.TRACK_HEIGHT - 2), QColor(pal["track_header_bg"]))
            if trk.id == self.selected_track_id:
                painter.fillRect(QRectF(0, ty, 3, self.TRACK_HEIGHT - 2), accent)
            painter.setFont(small)
            painter.setPen(QColor(pal["text_muted"]))
            painter.drawText(QRectF(6, ty + 3, 22, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, TRACK_GLYPH.get(trk.track_type, ""))
            painter.setPen(QColor(pal["text_main"]))
            nm = track_display_name(trk, lang)
            painter.drawText(QRectF(28, ty + 3, self.HEADER_WIDTH - 36, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, painter.fontMetrics().elidedText(nm, Qt.TextElideMode.ElideRight, self.HEADER_WIDTH - 36))
            for (flag, rect), (_f, glyph_off, glyph_on) in zip(self._header_button_rects(idx, trk), self._header_buttons(trk)):
                on = bool(getattr(trk, flag))
                if on:
                    painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 70))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRoundedRect(rect, 4, 4)
                painter.setPen(QColor(pal["text_main"]) if on else QColor(pal["text_muted"]))
                painter.setFont(glyph_font)
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph_on if on else glyph_off)
        painter.restore()
        painter.fillRect(0, 0, self.HEADER_WIDTH, self.RULER_HEIGHT, QColor(pal["panel_bg"]))

    def _paint_thumbs(self, painter: QPainter, clip: Any, rect: QRectF, path: QPainterPath) -> None:
        th = rect.height() - 6
        painter.save()
        painter.setClipPath(path)
        w_view = self._viewport_right()
        if clip.clip_type == "sticker":
            # one clearly visible icon at the start of the clip (stickers are small drawings, tiling them would be noise)
            img = self._thumbs.get(clip.source_path, 0.0)
            side = self.TRACK_HEIGHT - 12
            if img is not None and img.height() > 0:
                k = min(side / max(1, img.width()), side / max(1, img.height()))
                iw, ih = img.width() * k, img.height() * k
                painter.drawImage(QRectF(rect.x() + 3 + (side - iw) / 2, rect.y() + 3 + (side - ih) / 2, iw, ih), img)
            painter.restore()
            return
        tw = max(24.0, th * 16 / 9)
        n = max(1, int(rect.width() // tw))
        step = rect.width() / n
        span = max(0.05, clip.source_out - clip.source_in)
        painter.setOpacity(0.85)
        for i in range(n):
            x = rect.x() + i * step
            if x + step < self.HEADER_WIDTH or x > w_view:
                continue  # draw only visible tiles
            img = self._thumbs.get(clip.source_path, clip.source_in + (i + 0.5) / n * span)
            if img is not None:
                painter.drawImage(QRectF(x, rect.y() + 3, step, th), img)
        painter.restore()
        painter.fillRect(QRectF(rect.x(), rect.y(), rect.width(), 18), QColor(0, 0, 0, 120))  # keeps the label readable

    # ---- drag & drop: place a sticker / media file at the current playhead --------------------------
    def dragEnterEvent(self, event: Any) -> None:
        md = event.mimeData()
        if md.hasUrls() or md.hasFormat(STICKER_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: Any) -> None:
        self.dragEnterEvent(event)

    def dropEvent(self, event: Any) -> None:
        md = event.mimeData()
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        meta: Optional[Dict[str, Any]] = None
        if md.hasFormat(STICKER_MIME):
            try:
                meta = json.loads(bytes(md.data(STICKER_MIME)).decode("utf-8"))
            except Exception:
                meta = {}
        elif paths and all(Path(p).suffix.lower() in (".png", ".gif", ".webp") for p in paths):
            meta = {}  # images dropped on the canvas are intended as overlay stickers
        if paths:
            self.host.handle_timeline_drop(paths, self.controller.project.playhead_sec, None, meta)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ---- hit testing ------------------------------------------------------
    def _hit_clip(self, pos: QPointF) -> Tuple[Optional[Any], Optional[Any], str]:
        idx = self._track_index_at(pos.y())
        if idx < 0 or pos.x() < self.HEADER_WIDTH:
            return None, None, ""
        trk = self.controller.project.tracks[idx]
        for clip in reversed(trk.clips):
            x0 = self._sec_to_x(clip.timeline_start)
            x1 = x0 + max(14.0, clip.duration * self.pixels_per_sec)
            if x0 <= pos.x() <= x1:
                region = "left" if pos.x() - x0 <= self.EDGE else ("right" if x1 - pos.x() <= self.EDGE else "body")
                return trk, clip, region
        return trk, None, ""

    # ---- mouse ------------------------------------------------------------
    def mousePressEvent(self, event: Any) -> None:
        self.setFocus()
        pos = event.position()
        proj = self.controller.project
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if pos.x() < self.HEADER_WIDTH and pos.y() >= self.RULER_HEIGHT:
            idx = self._track_index_at(pos.y())
            if idx >= 0:
                trk = proj.tracks[idx]
                for flag, rect in self._header_button_rects(idx, trk):
                    if rect.adjusted(-2, -2, 2, 2).contains(pos):
                        self.host.set_track_flag(trk.id, flag, not getattr(trk, flag))
                        return
                self.selected_track_id = trk.id
                self.update()
            return
        if pos.y() <= self.RULER_HEIGHT:
            self._mode = "playhead"
            proj.playhead_sec = round(self._x_to_sec(pos.x()), 3)
            self.playhead_changed.emit(proj.playhead_sec)
            self.update()
            return
        trk, clip, region = self._hit_clip(pos)
        if clip is None:
            self.controller.select_clip(None)
            self.clip_selected.emit("")
            self._mode = "playhead"
            proj.playhead_sec = round(self._x_to_sec(pos.x()), 3)
            self.playhead_changed.emit(proj.playhead_sec)
            self.update()
            return
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.controller.select_clip(clip.id, toggle=True)
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            self.controller.select_clip(clip.id, additive=True)
        elif clip.id not in self.controller.selected_ids:
            self.controller.select_clip(clip.id)
        else:
            self.controller.selected_clip_id = clip.id
        if trk is not None:
            self.selected_track_id = trk.id
        self.clip_selected.emit(clip.id)
        self._press_sec = self._x_to_sec(pos.x())
        self._primary = clip.id
        self._moved = False
        self._orig = {}
        for cid in self.controller.selected_ids:
            f = proj.find_clip(cid)
            if f:
                self._orig[cid] = (f[1].timeline_start, f[1].timeline_end)
        if trk is not None and not trk.locked:
            self._mode = "trim_l" if region == "left" else ("trim_r" if region == "right" else "move")
        self.update()

    def mouseMoveEvent(self, event: Any) -> None:
        pos = event.position()
        proj = self.controller.project
        if not self._mode:
            _trk, clip, region = self._hit_clip(pos)
            if clip is not None and region in ("left", "right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif clip is not None:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            return
        if self._mode == "playhead":
            proj.playhead_sec = round(self._x_to_sec(pos.x()), 3)
            self.playhead_changed.emit(proj.playhead_sec)
            self.update()
            return
        if self._primary not in self._orig:
            return
        if not self._moved:
            proj.push_undo_snapshot()
            self._moved = True
        cur = self._x_to_sec(pos.x())
        delta = cur - self._press_sec
        o_start, o_end = self._orig[self._primary]
        if self._mode == "move":
            snapped = proj.compute_snap_time(max(0.0, o_start + delta), exclude_clip_id=self._primary)
            shift = snapped - o_start
            for cid, (s0, _e0) in self._orig.items():
                proj.move_clip(cid, max(0.0, s0 + shift))
            if len(self._orig) == 1:
                idx = self._track_index_at(pos.y())
                if idx >= 0:
                    proj.move_clip(self._primary, proj.find_clip(self._primary)[1].timeline_start, proj.tracks[idx].id)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif self._mode == "trim_l":
            proj.trim_clip(self._primary, new_start=proj.compute_snap_time(o_start + delta, exclude_clip_id=self._primary))
        elif self._mode == "trim_r":
            proj.trim_clip(self._primary, new_end=proj.compute_snap_time(o_end + delta, exclude_clip_id=self._primary))
        self.timeline_modified.emit()
        self.update()

    def mouseReleaseEvent(self, event: Any) -> None:
        was_moved = self._moved and self._mode in ("move", "trim_l", "trim_r")
        self._mode = ""
        self._moved = False
        self.unsetCursor()
        if was_moved:
            self.timeline_modified.emit()
            self.host.refresh_all()

    def mouseDoubleClickEvent(self, event: Any) -> None:
        _trk, clip, _ = self._hit_clip(event.position())
        if clip is not None:
            self.controller.select_clip(clip.id)
            self.clip_edit_requested.emit(clip.id)

    def wheelEvent(self, event: Any) -> None:
        dx = event.angleDelta().x()
        dy = event.angleDelta().y()
        delta = dy or dx
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.pixels_per_sec * (1.15 if delta > 0 else 1 / 1.15), anchor_x=event.position().x())
            self.zoom_changed.emit(self.pixels_per_sec)
        elif mods & Qt.KeyboardModifier.ShiftModifier:
            self.scroll_x -= (dx or dy) / self.pixels_per_sec * 1.2
        elif dx:
            # Touchpads and horizontal mouse wheels may send an X delta directly.
            self.scroll_x -= dx / self.pixels_per_sec * 1.2
        else:
            # Plain mouse wheel scrolls through tracks; Shift+wheel scrolls time.
            self.scroll_y -= dy / 2.0
        self._clamp_scroll()
        self.update()
        event.accept()

    def _on_vertical_scrollbar(self, value: int) -> None:
        self.scroll_y = float(value)
        self._clamp_scroll()
        self.update()

    def _on_horizontal_scrollbar(self, value: int) -> None:
        self.scroll_x = float(value) / 1000.0
        self._clamp_scroll()
        self.update()

    def ensure_track_visible(self, track_id: str) -> None:
        for idx, trk in enumerate(self.controller.project.tracks):
            if trk.id == track_id:
                top = idx * self.TRACK_HEIGHT
                view_h = max(1, self._viewport_bottom() - self.RULER_HEIGHT)
                if top < self.scroll_y:
                    self.scroll_y = float(top)
                elif top + self.TRACK_HEIGHT > self.scroll_y + view_h:
                    self.scroll_y = float(top + self.TRACK_HEIGHT - view_h)
                self._clamp_scroll()
                self.update()
                return

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._clamp_scroll()

    # ---- drag & drop (stickers from the panel, or any media file from the computer) ------------------
    @staticmethod
    def _has_payload(event: Any) -> bool:
        md = event.mimeData()
        return md.hasUrls() or md.hasFormat(STICKER_MIME)

    def dragEnterEvent(self, event: Any) -> None:
        if self._has_payload(event):
            event.acceptProposedAction()

    def dragMoveEvent(self, event: Any) -> None:
        if not self._has_payload(event):
            return
        pos = event.position()
        self._drop_hint = (self._track_index_at(pos.y()), self._x_to_sec(pos.x()))
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: Any) -> None:
        self._drop_hint = None
        self.update()

    def dropEvent(self, event: Any) -> None:
        self._drop_hint = None
        md = event.mimeData()
        pos = event.position()
        meta: Optional[Dict[str, Any]] = None
        if md.hasFormat(STICKER_MIME):
            try:
                meta = json.loads(bytes(md.data(STICKER_MIME)).decode("utf-8"))
            except Exception:
                meta = {}
        paths = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        idx = self._track_index_at(pos.y())
        trk = self.controller.project.tracks[idx] if idx >= 0 else None
        at = round(self._x_to_sec(pos.x()), 3)
        event.acceptProposedAction()
        if paths:
            self.host.handle_timeline_drop(paths, at, trk.id if trk is not None else None, meta)
        self.update()

    # ---- context menus ----------------------------------------------------
    def contextMenuEvent(self, event: Any) -> None:
        pos = QPointF(event.pos())
        c = self.controller
        proj = c.project
        lang = c.lang
        gp = event.globalPos()
        if pos.y() <= self.RULER_HEIGHT and pos.x() >= self.HEADER_WIDTH:
            self._ruler_menu(pos, gp)
            return
        if pos.x() < self.HEADER_WIDTH:
            idx = self._track_index_at(pos.y())
            if idx >= 0:
                self.selected_track_id = proj.tracks[idx].id
                self.update()
                self._track_menu(proj.tracks[idx], gp)
            return
        trk, clip, _ = self._hit_clip(pos)
        if clip is not None:
            if clip.id not in c.selected_ids:
                c.select_clip(clip.id)
                self.clip_selected.emit(clip.id)
            menu = build_clip_menu(self.host, clip.id, self)
            if menu is not None:
                menu.exec(gp)
            return
        if trk is None:
            return
        t_click = round(self._x_to_sec(pos.x()), 3)
        menu = QMenu(self)
        menu.addAction(tr("ctx_paste", lang)).triggered.connect(lambda _=False: self.host.paste_clipboard(trk.id, t_click))
        menu.actions()[0].setEnabled(bool(c.clipboard))
        menu.addAction(tr("ctx_move_playhead", lang)).triggered.connect(lambda _=False: self._set_playhead(t_click))
        menu.addAction(tr("ctx_add_marker", lang)).triggered.connect(lambda _=False: self.host.add_marker_at(t_click))
        if trk.track_type == "text":
            menu.addAction(tr("ctx_new_text_here", lang)).triggered.connect(lambda _=False: self.host.add_text_at(t_click))
        menu.addAction(tr("ctx_close_gaps", lang)).triggered.connect(lambda _=False: self.host.close_track_gaps(trk.id))
        menu.addSeparator()
        menu.addAction(tr("ctx_select_all", lang)).triggered.connect(lambda _=False: self.host.select_all())
        self._add_track_actions(menu)
        menu.exec(gp)

    def _set_playhead(self, t: float) -> None:
        self.controller.project.playhead_sec = t
        self.playhead_changed.emit(t)
        self.update()

    def _add_track_actions(self, menu: QMenu) -> None:
        lang = self.controller.lang
        sub = menu.addMenu(tr("ctx_add_track", lang))
        for ttype, key in (("video", "tool_add_vtrack"), ("sticker", "tool_add_stickertrack"), ("text", "tool_add_ttrack"), ("audio", "tool_add_atrack")):
            sub.addAction(tr(key, lang)).triggered.connect(lambda _=False, tt=ttype: self.host._on_add_track(tt))

    def _ruler_menu(self, pos: QPointF, gp: QPoint) -> None:
        proj = self.controller.project
        lang = self.controller.lang
        t = round(self._x_to_sec(pos.x()), 3)
        menu = QMenu(self)
        menu.addAction(tr("ctx_add_marker", lang)).triggered.connect(lambda _=False: self.host.add_marker_at(t))
        near = next((m for m in proj.markers if abs(self._sec_to_x(m.time_sec) - pos.x()) <= 8), None)
        if near is not None:
            menu.addAction(tr("ctx_remove_marker", lang)).triggered.connect(lambda _=False: self.host.remove_marker(near.id))
        menu.addAction(tr("ctx_clear_markers", lang)).triggered.connect(lambda _=False: self.host.clear_markers())
        menu.addSeparator()
        menu.addAction(tr("ctx_goto_start", lang)).triggered.connect(lambda _=False: self._set_playhead(0.0))
        menu.addAction(tr("ctx_goto_end", lang)).triggered.connect(lambda _=False: self._set_playhead(proj.total_duration()))
        menu.exec(gp)

    def _track_menu(self, trk: Any, gp: QPoint) -> None:
        lang = self.controller.lang
        proj = self.controller.project
        menu = QMenu(self)
        for flag, key in (("muted", "ctx_track_mute"), ("hidden", "ctx_track_hide"), ("locked", "ctx_track_lock")):
            act = menu.addAction(tr(key, lang))
            act.setCheckable(True)
            act.setChecked(bool(getattr(trk, flag)))
            act.triggered.connect(lambda _=False, f=flag: self.host.set_track_flag(trk.id, f, not getattr(trk, f)))
        menu.addSeparator()
        menu.addAction(tr("ctx_rename_track", lang)).triggered.connect(lambda _=False: self._rename_track(trk))
        i = proj.tracks.index(trk)
        up = menu.addAction(tr("ctx_move_up", lang))
        up.setEnabled(i > 0)
        up.triggered.connect(lambda _=False: self._move_track(trk.id, -1))
        down = menu.addAction(tr("ctx_move_down", lang))
        down.setEnabled(i < len(proj.tracks) - 1)
        down.triggered.connect(lambda _=False: self._move_track(trk.id, 1))
        menu.addAction(tr("ctx_select_track_clips", lang)).triggered.connect(lambda _=False: self.host.select_track_clips(trk.id))
        menu.addAction(tr("ctx_close_gaps", lang)).triggered.connect(lambda _=False: self.host.close_track_gaps(trk.id))
        menu.addSeparator()
        self._add_track_actions(menu)
        dele = menu.addAction(tr("ctx_delete_track", lang))
        dele.setEnabled(len(proj.tracks) > 1 and not trk.locked)
        dele.triggered.connect(lambda _=False: self._delete_track(trk.id))
        menu.exec(gp)

    def _rename_track(self, trk: Any) -> None:
        lang = self.controller.lang
        name, ok = QInputDialog.getText(self, tr("dlg_rename_track_title", lang), tr("dlg_rename_track_label", lang), text=track_display_name(trk, lang))
        if ok and self.controller.project.rename_track(trk.id, name):
            self.invalidate()

    def _move_track(self, track_id: str, d: int) -> None:
        if self.controller.project.move_track(track_id, d):
            self.host.refresh_all()

    def _delete_track(self, track_id: str) -> None:
        if self.controller.project.delete_track(track_id):
            self.host.refresh_all()
