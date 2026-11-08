# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Multi-Theme & Accent Palette Engine
Central palette -> QPalette + one QSS. Every color used by the UI comes from here (no colors scattered in widgets).
Light / Dark / System + 5 accents. Derived tones (accent_soft, accent_border, ...) are computed so that
selection/hover washes look right in BOTH light and dark themes.
"""

import tempfile
from pathlib import Path
from string import Template
from typing import Any, Dict, Optional

ACCENT_COLORS: Dict[str, Dict[str, str]] = {
    "cyan": {
        "name_key": "accent_cyan",
        "primary": "#00D2E6",
        "hover": "#26E3F5",
        "pressed": "#00A3B3",
        "muted": "#0D3B42",
        "text_on_accent": "#071013",
    },
    "purple": {
        "name_key": "accent_purple",
        "primary": "#7C4DFF",
        "hover": "#9873FF",
        "pressed": "#5E35B1",
        "muted": "#281A4D",
        "text_on_accent": "#FFFFFF",
    },
    "emerald": {
        "name_key": "accent_emerald",
        "primary": "#10B981",
        "hover": "#34D399",
        "pressed": "#059669",
        "muted": "#0B3B2C",
        "text_on_accent": "#061812",
    },
    "amber": {
        "name_key": "accent_amber",
        "primary": "#F59E0B",
        "hover": "#FBBF24",
        "pressed": "#D97706",
        "muted": "#422C08",
        "text_on_accent": "#181002",
    },
    "crimson": {
        "name_key": "accent_crimson",
        "primary": "#F43F5E",
        "hover": "#FB7185",
        "pressed": "#E11D48",
        "muted": "#47121D",
        "text_on_accent": "#FFFFFF",
    },
}

BASE_PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "window_bg": "#0E1014",
        "panel_bg": "#161920",
        "card_bg": "#1D212A",
        "input_bg": "#11141A",
        "timeline_bg": "#0B0D11",
        "track_header_bg": "#151821",
        "track_lane_bg": "#12151B",
        "canvas_bg": "#07080B",
        "text_main": "#F1F5F9",
        "text_muted": "#96A3B8",
        "border": "#272C38",
        "border_focus": "#3E4758",
        "hover_bg": "#242936",
        "scroll": "#303747",
        "scroll_hover": "#46506A",
        "tooltip_bg": "#1D212A",
        "danger": "#EF4444",
        "success": "#22C55E",
        "warning": "#F59E0B",
    },
    "light": {
        "window_bg": "#EEF2F7",
        "panel_bg": "#FFFFFF",
        "card_bg": "#F6F8FB",
        "input_bg": "#FFFFFF",
        "timeline_bg": "#E3E9F1",
        "track_header_bg": "#EEF2F7",
        "track_lane_bg": "#E9EEF5",
        "canvas_bg": "#1E293B",
        "text_main": "#0F172A",
        "text_muted": "#55637A",
        "border": "#D5DCE7",
        "border_focus": "#A9B5C6",
        "hover_bg": "#E9EEF5",
        "scroll": "#C3CCDA",
        "scroll_hover": "#9AA8BD",
        "tooltip_bg": "#FFFFFF",
        "danger": "#DC2626",
        "success": "#16A34A",
        "warning": "#D97706",
    },
}


def mix_colors(c1: str, c2: str, t: float) -> str:
    """Linear blend of two #RRGGBB colors: t=0 -> c1, t=1 -> c2."""
    a = c1.lstrip("#")
    b = c2.lstrip("#")
    t = max(0.0, min(1.0, float(t)))
    out = "".join(f"{int(round(int(a[i:i + 2], 16) * (1 - t) + int(b[i:i + 2], 16) * t)):02X}" for i in (0, 2, 4))
    return "#" + out


def detect_system_mode() -> str:
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is not None and hasattr(app, "styleHints"):
            hints = app.styleHints()
            if hasattr(hints, "colorScheme"):
                scheme = hints.colorScheme()
                if scheme == Qt.ColorScheme.Light:
                    return "light"
                if scheme == Qt.ColorScheme.Dark:
                    return "dark"
    except Exception:
        pass
    return "dark"


def get_effective_palette(mode: str = "dark", accent_key: str = "cyan") -> Dict[str, str]:
    resolved_mode = detect_system_mode() if mode == "system" else mode
    if resolved_mode not in BASE_PALETTES:
        resolved_mode = "dark"
    accent = ACCENT_COLORS.get(accent_key, ACCENT_COLORS["cyan"])
    merged = dict(BASE_PALETTES[resolved_mode])
    merged["mode"] = resolved_mode
    merged["accent_key"] = accent_key
    merged["accent"] = accent["primary"]
    merged["accent_hover"] = accent["hover"]
    merged["accent_pressed"] = accent["pressed"]
    merged["accent_muted"] = accent["muted"]
    merged["text_on_accent"] = accent["text_on_accent"]
    # Derived tones (work in both light and dark): a gentle accent wash for selections / hover / banners.
    wash = 0.18 if resolved_mode == "dark" else 0.13
    merged["accent_soft"] = mix_colors(merged["panel_bg"], accent["primary"], wash)
    merged["accent_border"] = mix_colors(merged["border"], accent["primary"], 0.55)
    merged["warning_soft"] = mix_colors(merged["panel_bg"], merged["warning"], wash)
    merged["text_disabled"] = mix_colors(merged["text_muted"], merged["panel_bg"], 0.45)
    return merged


def _icon_dir() -> Path:
    return Path(tempfile.gettempdir()) / "HMZVideoStudioPro_ui"


def checkmark_icon(color_hex: str) -> Optional[str]:
    """Render a 16x16 check-mark PNG (cached) for QCheckBox::indicator:checked. None if Qt is unavailable."""
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

        d = _icon_dir()
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"check_{color_hex.lstrip('#').lower()}.png"
        if not f.exists():
            img = QImage(16, 16, QImage.Format.Format_ARGB32)
            img.fill(Qt.GlobalColor.transparent)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(color_hex), 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(3.6, 8.4)
            path.lineTo(6.8, 11.4)
            path.lineTo(12.4, 4.8)
            painter.drawPath(path)
            painter.end()
            if not img.save(str(f), "PNG"):
                return None
        return f.as_posix()
    except Exception:
        return None


_QSS = Template(
    """
    QMainWindow, QDialog {
        background-color: ${window_bg};
        color: ${text_main};
        font-family: "Segoe UI", "Noto Sans Arabic", "Tahoma", sans-serif;
        font-size: 13px;
    }
    QWidget {
        color: ${text_main};
        font-family: "Segoe UI", "Noto Sans Arabic", "Tahoma", sans-serif;
    }
    QWidget:disabled { color: ${text_disabled}; }
    QLabel { background: transparent; }
    QToolTip {
        background-color: ${tooltip_bg};
        color: ${text_main};
        border: 1px solid ${border_focus};
        padding: 5px 8px;
    }

    /* ---------- surfaces ---------- */
    QFrame#PanelFrame, QWidget#PanelWidget {
        background-color: ${panel_bg};
        border: 1px solid ${border};
        border-radius: 10px;
    }
    QFrame#HeaderBar {
        background-color: ${panel_bg};
        border: 1px solid ${border};
        border-radius: 10px;
    }
    QFrame#Card {
        background-color: ${panel_bg};
        border: 1px solid ${border};
        border-radius: 12px;
    }
    QFrame#ProjectCard {
        background-color: ${panel_bg};
        border: 1px solid ${border};
        border-radius: 12px;
    }
    QFrame#ProjectCard:hover {
        border-color: ${accent};
        background-color: ${card_bg};
    }
    QFrame#ProjectCard:focus { border: 2px solid ${accent}; }
    QFrame#VSep { background-color: ${border}; border: none; }
    QFrame#Banner {
        background-color: ${accent_soft};
        border: 1px solid ${accent_border};
        border-radius: 10px;
    }
    QFrame#BannerWarn {
        background-color: ${warning_soft};
        border: 1px solid ${warning};
        border-radius: 10px;
    }
    QFrame#DropZone {
        background-color: transparent;
        border: 2px dashed ${border_focus};
        border-radius: 14px;
    }
    QWidget#HomeRoot { background-color: ${window_bg}; }
    QLabel#HomeTitle { font-size: 26px; font-weight: 800; }
    QLabel#HomeSubtitle { color: ${text_muted}; font-size: 13px; }
    QLabel#BrandName { font-size: 15px; font-weight: 800; }
    QLabel#SectionTitle { font-size: 15px; font-weight: 700; }
    QLabel#Muted { color: ${text_muted}; }
    QLabel#CardTitle { font-size: 13px; font-weight: 700; }
    QLabel#CardMeta { color: ${text_muted}; font-size: 12px; }
    QLabel#EmptyTitle { font-size: 16px; font-weight: 700; }

    /* ---------- tabs ---------- */
    QTabWidget::pane {
        border: 1px solid ${border};
        background-color: ${panel_bg};
        border-radius: 10px;
        top: -1px;
    }
    QTabBar::tab {
        background-color: transparent;
        color: ${text_muted};
        padding: 4px 8px;
        margin: 2px 1px;
        border: 1px solid transparent;
        border-radius: 8px;
        font-weight: 600;
    }
    QTabBar::tab:hover { background-color: ${hover_bg}; color: ${text_main}; }
    QTabBar::tab:selected {
        background-color: ${accent};
        color: ${text_on_accent};
        border-color: ${accent};
    }

    /* ---------- buttons ---------- */
    QPushButton {
        background-color: ${card_bg};
        color: ${text_main};
        border: 1px solid ${border};
        border-radius: 7px;
        padding: 3px 9px;
        font-weight: 600;
    }
    QPushButton:hover { border-color: ${accent_border}; background-color: ${hover_bg}; }
    QPushButton:pressed { background-color: ${accent_soft}; border-color: ${accent}; }
    QPushButton:focus { border-color: ${accent}; }
    QPushButton:disabled { color: ${text_disabled}; background-color: ${panel_bg}; border-color: ${border}; }
    QPushButton#AccentButton {
        background-color: ${accent};
        color: ${text_on_accent};
        border: 1px solid ${accent};
        font-weight: 700;
    }
    QPushButton#AccentButton:hover { background-color: ${accent_hover}; border-color: ${accent_hover}; }
    QPushButton#AccentButton:pressed { background-color: ${accent_pressed}; border-color: ${accent_pressed}; }
    QPushButton#AccentButton:disabled { background-color: ${accent_soft}; color: ${text_disabled}; border-color: ${accent_soft}; }
    QPushButton#BigAccent {
        background-color: ${accent};
        color: ${text_on_accent};
        border: 1px solid ${accent};
        border-radius: 12px;
        padding: 12px 26px;
        font-size: 15px;
        font-weight: 800;
    }
    QPushButton#BigAccent:hover { background-color: ${accent_hover}; border-color: ${accent_hover}; }
    QPushButton#BigAccent:pressed { background-color: ${accent_pressed}; border-color: ${accent_pressed}; }
    QPushButton#BigSoft {
        background-color: ${panel_bg};
        border: 1px solid ${border_focus};
        border-radius: 12px;
        padding: 12px 22px;
        font-size: 14px;
        font-weight: 700;
    }
    QPushButton#BigSoft:hover { border-color: ${accent}; background-color: ${hover_bg}; }
    QPushButton#DangerButton {
        background-color: ${danger};
        color: #FFFFFF;
        border: 1px solid ${danger};
    }
    QPushButton#IconButton { padding: 2px 8px; min-width: 22px; font-size: 15px; }
    QPushButton#ChipButton {
        background-color: transparent; border: 1px solid ${border}; border-radius: 10px;
        padding: 1px 9px; font-weight: 600; color: ${text_muted};
    }
    QPushButton#ChipButton:hover { border-color: ${accent_border}; color: ${text_main}; }
    QPushButton#ChipButton:checked { background-color: ${accent}; border-color: ${accent}; color: ${text_on_accent}; }
    QLabel#HintLabel { color: ${text_muted}; font-size: 11px; }
    QFrame#RailFrame { background-color: ${panel_bg}; border: 1px solid ${border}; border-radius: 10px; }
    QToolButton#RailButton {
        background: transparent; border: 1px solid transparent; border-radius: 8px;
        color: ${text_muted}; font-size: 11px; font-weight: 600; padding: 2px;
    }
    QToolButton#RailButton:hover { background-color: ${hover_bg}; color: ${text_main}; }
    QToolButton#RailButton:checked { background-color: ${accent}; color: ${text_on_accent}; border-color: ${accent}; }
    QPushButton#GhostButton, QToolButton#GhostButton {
        background-color: transparent;
        border: 1px solid transparent;
        color: ${text_main};
        font-weight: 600;
    }
    QPushButton#GhostButton:hover, QToolButton#GhostButton:hover { background-color: ${hover_bg}; border-color: ${border}; }
    QPushButton#GhostButton:pressed, QToolButton#GhostButton:pressed { background-color: ${accent_soft}; }
    QPushButton#FormatTile {
        background-color: ${panel_bg};
        border: 1px solid ${border};
        border-radius: 10px;
        padding: 8px 12px;
        font-weight: 600;
    }
    QPushButton#FormatTile:hover { border-color: ${accent}; background-color: ${accent_soft}; }
    QPushButton#LinkButton {
        background: transparent;
        border: none;
        color: ${accent};
        padding: 3px 6px;
    }
    QPushButton#LinkButton:hover { color: ${accent_hover}; text-decoration: underline; }
    QToolButton {
        background-color: transparent;
        border: 1px solid transparent;
        border-radius: 8px;
        padding: 6px 12px;
        font-weight: 600;
    }
    QToolButton:hover { background-color: ${hover_bg}; border-color: ${border}; }
    QToolButton:pressed { background-color: ${accent_soft}; }
    QToolButton::menu-indicator { image: none; width: 0px; }

    /* ---------- inputs ---------- */
    QLineEdit, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit, QTextBrowser {
        background-color: ${input_bg};
        color: ${text_main};
        border: 1px solid ${border};
        border-radius: 6px;
        padding: 2px 6px;
        selection-background-color: ${accent};
        selection-color: ${text_on_accent};
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
        border: 1px solid ${accent};
    }
    QComboBox {
        background-color: ${input_bg};
        color: ${text_main};
        border: 1px solid ${border};
        border-radius: 6px;
        padding: 2px 8px;
    }
    QComboBox:hover { border-color: ${accent_border}; }
    QComboBox:focus { border-color: ${accent}; }
    QComboBox QAbstractItemView {
        background-color: ${panel_bg};
        color: ${text_main};
        border: 1px solid ${accent};
        outline: 0;
        selection-background-color: ${accent};
        selection-color: ${text_on_accent};
    }
    QComboBox QAbstractItemView::item {
        min-height: 26px;
        padding: 4px 8px;
        color: ${text_main};
        background-color: ${panel_bg};
    }
    QComboBox QAbstractItemView::item:selected, QComboBox QAbstractItemView::item:hover {
        background-color: ${accent};
        color: ${text_on_accent};
    }
    QCheckBox, QRadioButton { spacing: 8px; color: ${text_main}; }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
        border: 1px solid ${border_focus};
        border-radius: 5px;
        background-color: ${input_bg};
    }
    QCheckBox::indicator:hover { border-color: ${accent}; }
    QCheckBox::indicator:checked {
        background-color: ${accent};
        border-color: ${accent};
        ${check_image}
    }
    QRadioButton::indicator {
        width: 14px;
        height: 14px;
        border: 1px solid ${border_focus};
        border-radius: 8px;
        background-color: ${input_bg};
    }
    QRadioButton::indicator:checked { background-color: ${accent}; border-color: ${accent}; }
    QGroupBox {
        border: 1px solid ${border};
        border-radius: 10px;
        margin-top: 14px;
        padding: 10px 8px 8px 8px;
        font-weight: 700;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        color: ${text_muted};
    }

    /* ---------- lists / views ---------- */
    QListView, QListWidget, QTreeView, QTreeWidget, QTableView, QTableWidget {
        background-color: ${input_bg};
        color: ${text_main};
        border: 1px solid ${border};
        border-radius: 8px;
        outline: 0;
    }
    QListView::item, QListWidget::item { padding: 2px 4px; border-radius: 6px; }
    QListView::item:hover, QListWidget::item:hover { background-color: ${hover_bg}; }
    QListView::item:selected, QListWidget::item:selected { background-color: ${accent_soft}; color: ${text_main}; }
    QListWidget#HomeList { background: transparent; border: none; }

    /* ---------- menus ---------- */
    QMenu {
        background-color: ${panel_bg};
        color: ${text_main};
        border: 1px solid ${border_focus};
        padding: 5px;
    }
    QMenu::item { padding: 7px 28px 7px 14px; border-radius: 5px; }
    QMenu::item:selected { background-color: ${accent_soft}; color: ${text_main}; }
    QMenu::item:disabled { color: ${text_disabled}; }
    QMenu::separator { height: 1px; background: ${border}; margin: 5px 8px; }

    /* ---------- scrollbars (slim, rounded) ---------- */
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
    QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px; }
    QScrollBar::handle:vertical { background: ${scroll}; border-radius: 4px; min-height: 30px; }
    QScrollBar::handle:horizontal { background: ${scroll}; border-radius: 4px; min-width: 30px; }
    QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: ${scroll_hover}; }
    QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; background: none; border: none; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

    /* ---------- sliders / progress / splitters ---------- */
    QSlider::groove:horizontal { height: 4px; background: ${border_focus}; border-radius: 2px; }
    QSlider::sub-page:horizontal { background: ${accent}; border-radius: 2px; }
    QSlider::handle:horizontal {
        background: ${accent};
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover { background: ${accent_hover}; }
    QSlider::groove:vertical { width: 4px; background: ${border_focus}; border-radius: 2px; }
    QSlider::add-page:vertical { background: ${accent}; border-radius: 2px; }
    QSlider::handle:vertical {
        background: ${accent};
        width: 14px;
        height: 14px;
        margin: 0 -5px;
        border-radius: 7px;
    }
    QProgressBar {
        background-color: ${input_bg};
        border: 1px solid ${border};
        border-radius: 7px;
        text-align: center;
        min-height: 14px;
        max-height: 16px;
    }
    QProgressBar::chunk { background-color: ${accent}; border-radius: 6px; }
    QSplitter::handle { background: transparent; }
    QSplitter::handle:horizontal { width: 5px; }
    QSplitter::handle:vertical { height: 5px; }
    QSplitter::handle:hover { background: ${accent_soft}; }
    """
)


def build_stylesheet(palette: Dict[str, str]) -> str:
    p = dict(palette)
    # Allow callers/tests that pass a hand-made palette: fill derived keys on demand.
    p.setdefault("hover_bg", mix_colors(p["panel_bg"], p["accent"], 0.10))
    p.setdefault("scroll", p["border_focus"])
    p.setdefault("scroll_hover", p["accent"])
    p.setdefault("tooltip_bg", p["card_bg"])
    p.setdefault("accent_soft", mix_colors(p["panel_bg"], p["accent"], 0.16))
    p.setdefault("accent_border", mix_colors(p["border"], p["accent"], 0.55))
    p.setdefault("warning_soft", mix_colors(p["panel_bg"], p["warning"], 0.16))
    p.setdefault("text_disabled", mix_colors(p["text_muted"], p["panel_bg"], 0.45))
    icon = checkmark_icon(p["text_on_accent"])
    p["check_image"] = f'image: url("{icon}");' if icon else ""
    return _QSS.safe_substitute(p)


def apply_theme_to_app(app: Any, mode: str = "dark", accent_key: str = "cyan") -> Dict[str, str]:
    palette_dict = get_effective_palette(mode, accent_key)
    try:
        from PyQt6.QtGui import QColor, QPalette

        qpal = QPalette()
        qpal.setColor(QPalette.ColorRole.Window, QColor(palette_dict["window_bg"]))
        qpal.setColor(QPalette.ColorRole.WindowText, QColor(palette_dict["text_main"]))
        qpal.setColor(QPalette.ColorRole.Base, QColor(palette_dict["input_bg"]))
        qpal.setColor(QPalette.ColorRole.AlternateBase, QColor(palette_dict["card_bg"]))
        qpal.setColor(QPalette.ColorRole.Text, QColor(palette_dict["text_main"]))
        qpal.setColor(QPalette.ColorRole.Button, QColor(palette_dict["card_bg"]))
        qpal.setColor(QPalette.ColorRole.ButtonText, QColor(palette_dict["text_main"]))
        qpal.setColor(QPalette.ColorRole.ToolTipBase, QColor(palette_dict["tooltip_bg"]))
        qpal.setColor(QPalette.ColorRole.ToolTipText, QColor(palette_dict["text_main"]))
        qpal.setColor(QPalette.ColorRole.PlaceholderText, QColor(palette_dict["text_muted"]))
        qpal.setColor(QPalette.ColorRole.Highlight, QColor(palette_dict["accent"]))
        qpal.setColor(QPalette.ColorRole.HighlightedText, QColor(palette_dict["text_on_accent"]))
        app.setPalette(qpal)
        app.setStyleSheet(build_stylesheet(palette_dict))
    except Exception:
        pass
    return palette_dict
