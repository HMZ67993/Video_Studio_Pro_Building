# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Home / Start screen (`video_studio_home.py`)

What the user sees first: quick actions (new / open / import), quick-start formats (16:9, 9:16, ...),
recent projects as cards (with pin / remove / reveal), a "what's new" panel, quick links and a tip.
Pure view: it never edits the project; it only emits signals that the main window handles.
Every string comes from video_studio_i18n. Requires PyQt6 (imported only when PyQt6 is available).
"""

import datetime
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QRectF, QSize, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from video_studio_core import ASPECT_RATIOS
from video_studio_i18n import APP_VERSION, TRANSLATIONS, tr
from video_studio_recent import age_parts, format_duration

# Palette shared with the custom-painted widgets (updated by HomeScreen.apply_palette).
_PAL: Dict[str, str] = {"accent": "#00D2E6", "accent_pressed": "#00A3B3", "text_on_accent": "#071013", "text_main": "#F1F5F9", "mode": "dark"}

CARD_MIN_WIDTH = 205
CARD_GAP = 12
SIDE_PANEL_WIDTH = 330
MAX_VISIBLE_RECENTS = 12


def _hue_for(text: str) -> int:
    """Stable 0..359 hue from a project name so each project keeps its own cover color."""
    h = 0
    for ch in text:
        h = (h * 131 + ord(ch)) % 360
    return h


class ElidedLabel(QLabel):
    """Single-line label that shows `...` instead of forcing the card wider."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._full = ""
        self.setMinimumWidth(20)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full = text
        self.setToolTip(text)
        self._apply()

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._apply()

    def _apply(self) -> None:
        el = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, max(10, self.width()))
        if el != self.text():
            self.setText(el)


class LogoMark(QWidget):
    """Small accent-gradient rounded square with a play triangle (brand mark)."""

    def __init__(self, size: int = 36, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0.0, QColor(_PAL["accent"]))
        grad.setColorAt(1.0, QColor(_PAL["accent_pressed"]))
        path = QPainterPath()
        path.addRoundedRect(r, r.width() * 0.28, r.width() * 0.28)
        p.fillPath(path, grad)
        c = r.center()
        s = r.width() * 0.2
        tri = QPainterPath()
        tri.moveTo(c.x() - s * 0.7, c.y() - s * 1.1)
        tri.lineTo(c.x() + s * 1.1, c.y())
        tri.lineTo(c.x() - s * 0.7, c.y() + s * 1.1)
        tri.closeSubpath()
        p.fillPath(tri, QColor(_PAL["text_on_accent"]))
        p.end()


class ThumbWidget(QWidget):
    """Generated project cover: per-project gradient + a frame in the project's aspect ratio + duration badge.
    (Drawn with QPainter: no file reads, so the Home screen opens instantly.)"""

    def __init__(self, name: str, aspect: str, duration_text: str, pinned: bool, pin_text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._hue = _hue_for(name)
        self._aspect = aspect
        self._dur = duration_text
        self._pinned = pinned
        self._pin_text = pin_text
        self.setFixedHeight(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: Any) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        light = _PAL.get("mode") == "light"
        c1 = QColor.fromHsl(self._hue, 150, 135 if light else 78)
        c2 = QColor.fromHsl((self._hue + 38) % 360, 165, 100 if light else 44)
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        path = QPainterPath()
        path.addRoundedRect(r, 9, 9)
        p.fillPath(path, grad)

        w, h = ASPECT_RATIOS.get(self._aspect, (16, 9))
        ratio = w / float(h)
        box_h = r.height() * 0.62
        box_w = box_h * ratio
        if box_w > r.width() * 0.62:
            box_w = r.width() * 0.62
            box_h = box_w / ratio
        frame = QRectF(r.center().x() - box_w / 2, r.center().y() - box_h / 2, box_w, box_h)
        p.setPen(QPen(QColor(255, 255, 255, 190), 1.6))
        p.setBrush(QColor(255, 255, 255, 34))
        p.drawRoundedRect(frame, 6, 6)

        cx, cy = frame.center().x(), frame.center().y()
        s = max(6.0, min(frame.width(), frame.height()) * 0.2)
        tri = QPainterPath()
        tri.moveTo(cx - s * 0.6, cy - s)
        tri.lineTo(cx + s * 1.0, cy)
        tri.lineTo(cx - s * 0.6, cy + s)
        tri.closeSubpath()
        p.fillPath(tri, QColor(255, 255, 255, 235))

        fm = p.fontMetrics()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        tw = fm.horizontalAdvance(self._dur) + 14
        bh = fm.height() + 4
        badge = QRectF(r.right() - tw - 6, r.bottom() - bh - 6, tw, bh)
        p.drawRoundedRect(badge, 6, 6)
        p.setPen(QColor(255, 255, 255))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, self._dur)

        if self._pinned:
            pw = fm.horizontalAdvance(self._pin_text) + 14
            pb = QRectF(r.left() + 6, r.top() + 6, pw, bh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(pb, 6, 6)
            p.setPen(QColor(255, 255, 255))
            p.drawText(pb, Qt.AlignmentFlag.AlignCenter, self._pin_text)
        p.end()


class ProjectCard(QFrame):
    open_requested = pyqtSignal(str)
    pin_requested = pyqtSignal(str)
    reveal_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)

    def __init__(self, entry: Dict[str, Any], lang: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("ProjectCard")
        self._path = str(entry["path"])
        self._lang = lang
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(CARD_MIN_WIDTH)
        name = str(entry.get("name") or Path(self._path).stem)
        aspect = str(entry.get("aspect", "16:9"))
        dur = format_duration(float(entry.get("duration", 0.0) or 0.0))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)
        self.thumb = ThumbWidget(name, aspect, dur, bool(entry.get("pinned")), tr("home_pinned", lang))
        lay.addWidget(self.thumb)
        lbl_name = ElidedLabel(name)
        lbl_name.setObjectName("CardTitle")
        lay.addWidget(lbl_name)
        meta = tr("home_meta", lang, aspect=aspect, dur=dur, clips=int(entry.get("clips", 0) or 0))
        lbl_meta = ElidedLabel(meta)
        lbl_meta.setObjectName("CardMeta")
        lay.addWidget(lbl_meta)
        ts = float(entry.get("opened") or entry.get("mtime") or time.time())
        unit, n = age_parts(time.time() - ts)
        lbl_age = ElidedLabel(tr(f"home_age_{unit}", lang, n=n))
        lbl_age.setObjectName("CardMeta")
        lay.addWidget(lbl_age)
        self.setToolTip(self._path)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.open_requested.emit(self._path)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.open_requested.emit(self._path)
        elif event.key() == Qt.Key.Key_Delete:
            self.remove_requested.emit(self._path)
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event: Any) -> None:
        menu = QMenu(self)
        a_open = menu.addAction(tr("home_ctx_open", self._lang))
        a_pin = menu.addAction(tr("home_ctx_pin", self._lang))
        a_reveal = menu.addAction(tr("home_ctx_reveal", self._lang))
        menu.addSeparator()
        a_remove = menu.addAction(tr("home_ctx_remove", self._lang))
        chosen = menu.exec(event.globalPos())
        if chosen is a_open:
            self.open_requested.emit(self._path)
        elif chosen is a_pin:
            self.pin_requested.emit(self._path)
        elif chosen is a_reveal:
            self.reveal_requested.emit(self._path)
        elif chosen is a_remove:
            self.remove_requested.emit(self._path)


def _aspect_icon(key: str, color_hex: str) -> QIcon:
    """Tiny outline of the format (so users recognise 9:16 vs 16:9 at a glance)."""
    pm = QPixmap(24, 24)
    pm.fill(Qt.GlobalColor.transparent)
    w, h = ASPECT_RATIOS.get(key, (16, 9))
    ratio = w / float(h)
    bw, bh = (20.0, 20.0 / ratio) if ratio >= 1 else (20.0 * ratio, 20.0)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(color_hex), 1.8))
    p.drawRoundedRect(QRectF((24 - bw) / 2, (24 - bh) / 2, bw, bh), 3, 3)
    p.end()
    return QIcon(pm)


class HomeScreen(QWidget):
    new_project = pyqtSignal(str)          # aspect ratio key
    open_project_dialog = pyqtSignal()
    import_media = pyqtSignal()
    resume_editor = pyqtSignal()
    open_recent = pyqtSignal(str)          # path
    recover_requested = pyqtSignal()
    discard_recovery_requested = pyqtSignal()
    open_guide = pyqtSignal()
    open_store = pyqtSignal()
    open_about = pyqtSignal()
    open_license = pyqtSignal()
    toggle_language = pyqtSignal()
    update_clicked = pyqtSignal(str)       # download url

    def __init__(self, controller: Any, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.controller = controller
        self.setObjectName("HomeRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._cards: List[ProjectCard] = []
        self._cols = 0
        self._update_url = ""
        self._build()
        self.retranslate()

    # ---- construction ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 16, 28, 14)
        root.setSpacing(12)

        # top bar
        top = QHBoxLayout()
        top.setSpacing(10)
        self.logo = LogoMark(34)
        top.addWidget(self.logo)
        self.lbl_brand = QLabel("HMZ Video Studio Pro")
        self.lbl_brand.setObjectName("BrandName")
        self.lbl_brand.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        self.lbl_version = QLabel(f"v{APP_VERSION}")
        self.lbl_version.setObjectName("Muted")
        self.lbl_version.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        top.addWidget(self.lbl_brand)
        top.addWidget(self.lbl_version)
        top.addStretch(1)
        self.btn_lang = QPushButton()
        self.btn_lang.setObjectName("GhostButton")
        self.btn_lang.clicked.connect(self.toggle_language.emit)
        self.btn_menu = QToolButton()
        self.btn_menu.setObjectName("GhostButton")
        self.btn_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        top.addWidget(self.btn_lang)
        top.addWidget(self.btn_menu)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(18)
        root.addLayout(body, 1)

        # ---- left column ----
        left = QVBoxLayout()
        left.setSpacing(10)
        body.addLayout(left, 1)

        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("HomeTitle")
        self.lbl_subtitle = QLabel()
        self.lbl_subtitle.setObjectName("HomeSubtitle")
        left.addWidget(self.lbl_title)
        left.addWidget(self.lbl_subtitle)

        self.banner_recovery = QFrame()
        self.banner_recovery.setObjectName("BannerWarn")
        br = QHBoxLayout(self.banner_recovery)
        br.setContentsMargins(12, 8, 12, 8)
        self.lbl_recovery = QLabel()
        self.lbl_recovery.setWordWrap(True)
        self.btn_recover = QPushButton()
        self.btn_recover.setObjectName("AccentButton")
        self.btn_recover.clicked.connect(self.recover_requested.emit)
        self.btn_discard = QPushButton()
        self.btn_discard.clicked.connect(self.discard_recovery_requested.emit)
        br.addWidget(self.lbl_recovery, 1)
        br.addWidget(self.btn_recover)
        br.addWidget(self.btn_discard)
        self.banner_recovery.setVisible(False)
        left.addWidget(self.banner_recovery)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.btn_new = QPushButton()
        self.btn_new.setObjectName("BigAccent")
        self.btn_new.clicked.connect(lambda: self.new_project.emit("16:9"))
        self.btn_open = QPushButton()
        self.btn_open.setObjectName("BigSoft")
        self.btn_open.clicked.connect(self.open_project_dialog.emit)
        self.btn_import = QPushButton()
        self.btn_import.setObjectName("BigSoft")
        self.btn_import.clicked.connect(self.import_media.emit)
        self.btn_continue = QPushButton()
        self.btn_continue.setObjectName("BigSoft")
        self.btn_continue.clicked.connect(self.resume_editor.emit)
        self.btn_continue.setVisible(False)
        for b in (self.btn_new, self.btn_open, self.btn_import, self.btn_continue):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(b)
        actions.addStretch(1)
        left.addLayout(actions)

        self.lbl_quick = QLabel()
        self.lbl_quick.setObjectName("SectionTitle")
        left.addWidget(self.lbl_quick)
        tiles = QHBoxLayout()
        tiles.setSpacing(8)
        self.format_tiles: Dict[str, QPushButton] = {}
        for key in ASPECT_RATIOS:
            b = QPushButton()
            b.setObjectName("FormatTile")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setIconSize(QSize(22, 22))
            b.clicked.connect(lambda _=False, k=key: self.new_project.emit(k))
            self.format_tiles[key] = b
            tiles.addWidget(b)
        tiles.addStretch(1)
        left.addLayout(tiles)

        recent_head = QHBoxLayout()
        self.lbl_recent = QLabel()
        self.lbl_recent.setObjectName("SectionTitle")
        self.btn_clear = QPushButton()
        self.btn_clear.setObjectName("LinkButton")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self._on_clear)
        recent_head.addWidget(self.lbl_recent)
        recent_head.addStretch(1)
        recent_head.addWidget(self.btn_clear)
        left.addLayout(recent_head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("HomeRoot")
        self.grid = QGridLayout(holder)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setHorizontalSpacing(CARD_GAP)
        self.grid.setVerticalSpacing(CARD_GAP)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(holder)
        left.addWidget(self.scroll, 1)

        self.empty_zone = QFrame()
        self.empty_zone.setObjectName("DropZone")
        ez = QVBoxLayout(self.empty_zone)
        ez.setContentsMargins(20, 22, 20, 22)
        ez.setSpacing(6)
        icon = QLabel("🎬")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 34px; background: transparent;")
        self.lbl_empty_title = QLabel()
        self.lbl_empty_title.setObjectName("EmptyTitle")
        self.lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_body = QLabel()
        self.lbl_empty_body.setObjectName("Muted")
        self.lbl_empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_body.setWordWrap(True)
        ez.addStretch(1)
        ez.addWidget(icon)
        ez.addWidget(self.lbl_empty_title)
        ez.addWidget(self.lbl_empty_body)
        ez.addStretch(1)
        left.addWidget(self.empty_zone, 1)

        # ---- right column ----
        right = QVBoxLayout()
        right.setSpacing(12)
        right_holder = QWidget()
        right_holder.setObjectName("HomeRoot")
        right_holder.setFixedWidth(SIDE_PANEL_WIDTH)
        right_holder.setLayout(right)
        right.setContentsMargins(0, 0, 0, 0)
        body.addWidget(right_holder)

        self.banner_update = QFrame()
        self.banner_update.setObjectName("Banner")
        bu = QHBoxLayout(self.banner_update)
        bu.setContentsMargins(12, 8, 12, 8)
        self.lbl_update = QLabel()
        self.lbl_update.setWordWrap(True)
        self.btn_update = QPushButton()
        self.btn_update.setObjectName("AccentButton")
        self.btn_update.clicked.connect(lambda: self.update_clicked.emit(self._update_url))
        bu.addWidget(self.lbl_update, 1)
        bu.addWidget(self.btn_update)
        self.banner_update.setVisible(False)
        right.addWidget(self.banner_update)

        card_new = QFrame()
        card_new.setObjectName("Card")
        cn = QVBoxLayout(card_new)
        cn.setContentsMargins(16, 14, 16, 14)
        cn.setSpacing(8)
        self.lbl_whats_new = QLabel()
        self.lbl_whats_new.setObjectName("SectionTitle")
        cn.addWidget(self.lbl_whats_new)
        self.new_items: List[QLabel] = []
        for _ in range(6):
            it = QLabel()
            it.setWordWrap(True)
            self.new_items.append(it)
            cn.addWidget(it)
        right.addWidget(card_new)

        card_links = QFrame()
        card_links.setObjectName("Card")
        cl = QVBoxLayout(card_links)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(2)
        self.lbl_links = QLabel()
        self.lbl_links.setObjectName("SectionTitle")
        cl.addWidget(self.lbl_links)
        self.link_buttons: Dict[str, QPushButton] = {}
        for key, sig in (("btn_guide", self.open_guide), ("btn_more_apps", self.open_store), ("btn_license", self.open_license), ("btn_about", self.open_about)):
            b = QPushButton()
            b.setObjectName("LinkButton")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(sig.emit)
            self.link_buttons[key] = b
            cl.addWidget(b, 0, Qt.AlignmentFlag.AlignLeading)
        right.addWidget(card_links)

        card_tip = QFrame()
        card_tip.setObjectName("Card")
        ct = QVBoxLayout(card_tip)
        ct.setContentsMargins(16, 12, 16, 12)
        ct.setSpacing(4)
        self.lbl_tip_title = QLabel()
        self.lbl_tip_title.setObjectName("SectionTitle")
        self.lbl_tip = QLabel()
        self.lbl_tip.setWordWrap(True)
        self.lbl_tip.setObjectName("Muted")
        ct.addWidget(self.lbl_tip_title)
        ct.addWidget(self.lbl_tip)
        right.addWidget(card_tip)
        right.addStretch(1)

    # ---- public API --------------------------------------------------------------------
    def set_menu(self, menu: QMenu) -> None:
        self.btn_menu.setMenu(menu)

    def set_session(self, project_name: Optional[str]) -> None:
        """Show 'Continue: <project>' when an editing session is already open."""
        lang = self.controller.lang
        if project_name:
            self.btn_continue.setText(tr("home_continue", lang, name=project_name))
            self.btn_continue.setVisible(True)
        else:
            self.btn_continue.setVisible(False)

    def set_recovery(self, visible: bool) -> None:
        self.banner_recovery.setVisible(bool(visible))

    def set_update(self, version: Optional[str], url: str = "") -> None:
        if version:
            self._update_url = url
            self.lbl_update.setText(tr("home_update_banner", self.controller.lang, ver=version))
            self.banner_update.setVisible(True)
        else:
            self.banner_update.setVisible(False)

    def apply_palette(self, pal: Dict[str, str]) -> None:
        _PAL.update(pal)
        self.logo.update()
        self._refresh_tile_icons()
        for c in self._cards:
            c.thumb.update()

    def retranslate(self) -> None:
        lang = self.controller.lang
        self.btn_lang.setText(tr("lang_toggle", lang))
        self.btn_menu.setText(tr("btn_menu", lang))
        self.btn_menu.setToolTip(tr("btn_menu_tip", lang))
        self.lbl_title.setText(tr("home_greeting", lang))
        self.lbl_subtitle.setText(tr("home_tagline", lang))
        self.lbl_recovery.setText(tr("home_recovery_msg", lang))
        self.btn_recover.setText(tr("home_recovery_restore", lang))
        self.btn_discard.setText(tr("home_recovery_discard", lang))
        self.btn_new.setText(tr("home_new", lang))
        self.btn_open.setText(tr("home_open", lang))
        self.btn_import.setText(tr("home_import", lang))
        self.lbl_quick.setText(tr("home_quick_start", lang))
        for key, b in self.format_tiles.items():
            hint_key = f"home_ar_{key}"
            hint = tr(hint_key, lang) if hint_key in TRANSLATIONS else ""
            b.setText(f"{key}   {hint}".strip())
        self._refresh_tile_icons()
        self.lbl_recent.setText(tr("home_recent", lang))
        self.btn_clear.setText(tr("home_recent_clear", lang))
        self.lbl_empty_title.setText(tr("home_recent_empty_title", lang))
        self.lbl_empty_body.setText(tr("home_recent_empty_body", lang))
        self.lbl_whats_new.setText(tr("home_whats_new", lang))
        for i, lbl in enumerate(self.new_items, start=1):
            lbl.setText("•  " + tr(f"home_new_{i}", lang))
        self.btn_update.setText(tr("home_update_btn", lang))
        self.lbl_links.setText(tr("home_links", lang))
        for key, b in self.link_buttons.items():
            b.setText(tr(key, lang))
        self.lbl_tip_title.setText(tr("home_tip_title", lang))
        self.lbl_tip.setText(tr(f"home_tip_{datetime.date.today().toordinal() % 4 + 1}", lang))
        self.refresh()

    def refresh(self) -> None:
        """Rebuild the recent-projects grid from the saved list."""
        lang = self.controller.lang
        for c in self._cards:
            self.grid.removeWidget(c)
            c.setParent(None)
            c.deleteLater()
        self._cards = []
        entries = self.controller.recents.entries(limit=MAX_VISIBLE_RECENTS)
        for e in entries:
            card = ProjectCard(e, lang)
            card.open_requested.connect(self.open_recent.emit)
            card.pin_requested.connect(self._on_pin)
            card.reveal_requested.connect(self._reveal)
            card.remove_requested.connect(self._on_remove)
            self._cards.append(card)
        has = bool(self._cards)
        self.scroll.setVisible(has)
        self.empty_zone.setVisible(not has)
        self.btn_clear.setVisible(has)
        self._cols = 0
        self._relayout()

    # ---- internals ---------------------------------------------------------------------
    def _refresh_tile_icons(self) -> None:
        for key, b in self.format_tiles.items():
            b.setIcon(_aspect_icon(key, _PAL.get("text_main", "#F1F5F9")))

    def _relayout(self) -> None:
        avail = self.width() - 56 - SIDE_PANEL_WIDTH - 18 - 14
        cols = max(2, min(5, (avail + CARD_GAP) // (CARD_MIN_WIDTH + CARD_GAP)))
        if cols == self._cols and self.grid.count() == len(self._cards):
            return
        self._cols = cols
        for c in self._cards:
            self.grid.removeWidget(c)
        for i, c in enumerate(self._cards):
            self.grid.addWidget(c, i // cols, i % cols)
            c.show()
        for col in range(5):
            self.grid.setColumnStretch(col, 1 if col < cols else 0)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _on_pin(self, path: str) -> None:
        self.controller.recents.toggle_pin(path)
        self.refresh()

    def _on_remove(self, path: str) -> None:
        self.controller.recents.remove(path)
        self.refresh()

    def _on_clear(self) -> None:
        self.controller.recents.clear(keep_pinned=True)
        self.refresh()

    def _reveal(self, path: str) -> None:
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select," + os.path.normpath(path)])
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))
        except Exception:
            pass
