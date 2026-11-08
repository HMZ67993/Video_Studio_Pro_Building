# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Text inspector tab: full control over a text clip's content and style
(font, size, bold/italic/underline, alignment, spacing, fill, outline, shadow, glow, background box,
reflection, flip/mirror, in/out animations, quick presets). Requires PyQt6.
"""

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from video_studio_core import TextStyleSettings, TimelineClip
from video_studio_i18n import tr
from video_studio_text import ALIGNMENTS, ANIMATIONS_IN, ANIMATIONS_OUT

PRESETS: Dict[str, Dict[str, Any]] = {
    "txt_preset_neon": dict(text_color_hex="#FFFFFF", stroke_width=0, glow_enabled=True, glow_color_hex="#00D2E6", glow_radius=16, shadow_enabled=False, bg_enabled=False, bold=True),
    "txt_preset_outline": dict(text_color_hex="#FFFFFF", stroke_color_hex="#000000", stroke_width=6, shadow_enabled=False, glow_enabled=False, bg_enabled=False, bold=True),
    "txt_preset_shadow": dict(text_color_hex="#FFFFFF", stroke_width=0, shadow_enabled=True, shadow_color_hex="#000000", shadow_dx=5, shadow_dy=6, shadow_blur=9, shadow_opacity=75, glow_enabled=False, bg_enabled=False),
    "txt_preset_boxed": dict(text_color_hex="#FFFFFF", stroke_width=0, bg_enabled=True, bg_color_hex="#111827", bg_opacity=85, bg_padding=18, bg_radius=12, shadow_enabled=False, glow_enabled=False),
    "txt_preset_gold": dict(text_color_hex="#FFD166", stroke_color_hex="#5A3A00", stroke_width=3, reflection_enabled=True, reflection_opacity=45, shadow_enabled=True, shadow_dx=3, shadow_dy=4, shadow_blur=6, glow_enabled=False, bg_enabled=False),
}


class ColorButton(QPushButton):
    """Swatch button that opens a color dialog; emits the new #RRGGBB value."""

    color_picked = pyqtSignal(str)

    def __init__(self, title_provider: Callable[[], str]):
        super().__init__()
        self._title = title_provider
        self._hex = "#FFFFFF"
        self.setMinimumWidth(50)
        self.setMaximumWidth(72)
        self.setMinimumHeight(22)
        self.setMaximumHeight(25)
        self.clicked.connect(self._pick)
        self._paint()

    def set_hex(self, hex_str: str) -> None:
        self._hex = hex_str if len(hex_str) == 7 and hex_str.startswith("#") else "#FFFFFF"
        self._paint()

    def hex(self) -> str:
        return self._hex

    def _paint(self) -> None:
        col = QColor(self._hex)
        fg = "#000000" if col.lightness() > 140 else "#FFFFFF"
        self.setStyleSheet(f"QPushButton {{ background-color: {self._hex}; color: {fg}; border: 1px solid #64748B; border-radius: 4px; padding: 3px 6px; }}")
        self.setText(self._hex.upper())
        self.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    def _pick(self) -> None:
        col = QColorDialog.getColor(QColor(self._hex), self, self._title())
        if col.isValid():
            self.set_hex(col.name().upper())
            self.color_picked.emit(self._hex)


class TextEditorPanel(QScrollArea):
    """Dedicated, always-visible editor for the selected text clip."""

    def __init__(self, host: Any):
        super().__init__()
        self.host = host
        self.c = host.controller
        self._loading = False
        self._last_snapshot = 0.0
        self._i18n: List[Tuple[Any, str, str]] = []
        self._combos: List[Tuple[QComboBox, List[Tuple[str, str]]]] = []
        self.setObjectName("TextInspectorPanel")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Compact styling is deliberately scoped to this panel, so dialogs and other editors
        # keep their normal comfortable control sizes.
        self.setStyleSheet("""
            QScrollArea#TextInspectorPanel QGroupBox {
                margin-top: 10px;
                padding: 5px 6px 4px 6px;
                border-radius: 8px;
            }
            QScrollArea#TextInspectorPanel QDoubleSpinBox,
            QScrollArea#TextInspectorPanel QComboBox,
            QScrollArea#TextInspectorPanel QFontComboBox {
                min-height: 21px; max-height: 25px; padding: 1px 4px;
            }
            QScrollArea#TextInspectorPanel QPushButton {
                min-height: 21px; max-height: 25px; padding: 1px 5px; border-radius: 5px;
            }
            QScrollArea#TextInspectorPanel QCheckBox { spacing: 4px; }
            QScrollArea#TextInspectorPanel QCheckBox::indicator { width: 13px; height: 13px; }
            QScrollArea#TextInspectorPanel QPlainTextEdit {
                min-height: 48px; max-height: 72px; padding: 2px 4px;
            }
        """)
        inner = QWidget()
        self.setWidget(inner)
        root = QVBoxLayout(inner)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(3)

        self.lbl_hint = self._label("txt_not_text")
        self.lbl_hint.setWordWrap(True)
        root.addWidget(self.lbl_hint)
        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(3)
        root.addWidget(self.body)
        root.addStretch(1)

        # ---- content ----
        g, gl = self._group("txt_grp_content", body)
        self.te_text = QPlainTextEdit()
        self.te_text.setMinimumHeight(48)
        self.te_text.setMaximumHeight(72)
        self.te_text.textChanged.connect(lambda: self._edit(lambda ts: setattr(ts, "text", self.te_text.toPlainText())))
        gl.addWidget(self.te_text, 0, 0, 1, 4)

        # ---- font ----
        g, gl = self._group("txt_grp_font", body)
        self.cmb_font = QFontComboBox()
        self.cmb_font.setMinimumHeight(22)
        self.cmb_font.setMaximumHeight(26)
        self.cmb_font.setMinimumContentsLength(7)
        self.cmb_font.currentFontChanged.connect(lambda f: self._edit(lambda ts: setattr(ts, "font_family", f.family())))
        self.sp_size = self._spin(6, 500, 1, "font_size", 0)
        self.btn_b = self._toggle("B", "txt_bold", "bold", QFont.Weight.Bold)
        self.btn_i = self._toggle("I", "txt_italic", "italic")
        self.btn_u = self._toggle("U", "txt_underline", "underline")
        self.cmb_align = self._combo([(a, f"txt_align_{a}") for a in ALIGNMENTS], "align")
        self.sp_ls = self._spin(-30, 120, 0.5, "letter_spacing", 1)
        self.sp_line = self._spin(0.5, 3.0, 0.05, "line_spacing", 2)
        self._row(gl, 0, "txt_font_family", self.cmb_font, span=3)
        self._row(gl, 1, "txt_font_size", self.sp_size)
        gl.addWidget(self.btn_b, 1, 2)
        gl.addWidget(self.btn_i, 1, 3)
        gl.addWidget(self.btn_u, 2, 3)
        self._row(gl, 2, "txt_align", self.cmb_align)
        self._row(gl, 3, "txt_letter_spacing", self.sp_ls)
        self._row(gl, 4, "txt_line_spacing", self.sp_line)

        # ---- fill ----
        g, gl = self._group("txt_grp_fill", body)
        self.cb_fill = self._color("text_color_hex")
        self.sp_fill_op = self._spin(0, 100, 1, "text_opacity", 0)
        self._row(gl, 0, "txt_color", self.cb_fill)
        self._row(gl, 1, "txt_opacity", self.sp_fill_op)

        # ---- outline ----
        g, gl = self._group("txt_grp_outline", body)
        self.cb_stroke = self._color("stroke_color_hex")
        self.sp_stroke = self._spin(0, 40, 1, "stroke_width", 0)
        self._row(gl, 0, "txt_color", self.cb_stroke)
        self._row(gl, 1, "txt_outline_width", self.sp_stroke)

        # ---- shadow ----
        g, gl = self._group("txt_grp_shadow", body)
        self.ck_shadow = self._check("txt_shadow_enable", "shadow_enabled")
        self.cb_shadow = self._color("shadow_color_hex")
        self.sp_sdx = self._spin(-100, 100, 1, "shadow_dx", 0)
        self.sp_sdy = self._spin(-100, 100, 1, "shadow_dy", 0)
        self.sp_sblur = self._spin(0, 60, 1, "shadow_blur", 0)
        self.sp_sop = self._spin(0, 100, 1, "shadow_opacity", 0)
        gl.addWidget(self.ck_shadow, 0, 0, 1, 4)
        self._row(gl, 1, "txt_color", self.cb_shadow)
        self._row(gl, 1, "txt_shadow_blur", self.sp_sblur, col=2)
        self._row(gl, 2, "txt_shadow_x", self.sp_sdx)
        self._row(gl, 2, "txt_shadow_y", self.sp_sdy, col=2)
        self._row(gl, 3, "txt_opacity", self.sp_sop)

        # ---- glow ----
        g, gl = self._group("txt_grp_glow", body)
        self.ck_glow = self._check("txt_glow_enable", "glow_enabled")
        self.cb_glow = self._color("glow_color_hex")
        self.sp_glow = self._spin(1, 80, 1, "glow_radius", 0)
        gl.addWidget(self.ck_glow, 0, 0, 1, 4)
        self._row(gl, 1, "txt_color", self.cb_glow)
        self._row(gl, 1, "txt_glow_radius", self.sp_glow, col=2)

        # ---- background ----
        g, gl = self._group("txt_grp_bg", body)
        self.ck_bg = self._check("txt_bg_enable", "bg_enabled")
        self.cb_bg = self._color("bg_color_hex")
        self.sp_bgop = self._spin(0, 100, 1, "bg_opacity", 0)
        self.sp_bgpad = self._spin(0, 120, 1, "bg_padding", 0)
        self.sp_bgrad = self._spin(0, 80, 1, "bg_radius", 0)
        gl.addWidget(self.ck_bg, 0, 0, 1, 4)
        self._row(gl, 1, "txt_color", self.cb_bg)
        self._row(gl, 1, "txt_opacity", self.sp_bgop, col=2)
        self._row(gl, 2, "txt_bg_padding", self.sp_bgpad)
        self._row(gl, 2, "txt_bg_radius", self.sp_bgrad, col=2)

        # ---- reflection / flip ----
        g, gl = self._group("txt_grp_reflect", body)
        self.ck_refl = self._check("txt_refl_enable", "reflection_enabled")
        self.sp_rop = self._spin(0, 100, 1, "reflection_opacity", 0)
        self.sp_rgap = self._spin(-50, 200, 1, "reflection_gap", 0)
        self.ck_flip_h = QCheckBox()
        self.ck_flip_v = QCheckBox()
        self._i18n += [(self.ck_flip_h, "lbl_flip_h", "setText"), (self.ck_flip_v, "lbl_flip_v", "setText")]
        self.ck_flip_h.toggled.connect(lambda v: self._edit_clip(lambda cl: setattr(cl, "flip_h", bool(v))))
        self.ck_flip_v.toggled.connect(lambda v: self._edit_clip(lambda cl: setattr(cl, "flip_v", bool(v))))
        gl.addWidget(self.ck_refl, 0, 0, 1, 4)
        self._row(gl, 1, "txt_opacity", self.sp_rop)
        self._row(gl, 1, "txt_refl_gap", self.sp_rgap, col=2)
        gl.addWidget(self.ck_flip_h, 2, 0, 1, 2)
        gl.addWidget(self.ck_flip_v, 2, 2, 1, 2)

        # ---- animation ----
        g, gl = self._group("txt_grp_anim", body)
        self.cmb_in = self._combo([(a, f"anim_{a}") for a in ANIMATIONS_IN], "animation_in")
        self.cmb_out = self._combo([(a, f"anim_{a}") for a in ANIMATIONS_OUT], "animation_out")
        self.sp_adur = self._spin(0.1, 5.0, 0.1, "animation_duration", 1)
        self._row(gl, 0, "txt_anim_in", self.cmb_in)
        self._row(gl, 0, "txt_anim_out", self.cmb_out, col=2)
        self._row(gl, 1, "txt_anim_dur", self.sp_adur)

        # ---- presets ----
        g, gl = self._group("txt_grp_presets", body)
        for i, key in enumerate(PRESETS):
            b = QPushButton()
            self._i18n.append((b, key, "setText"))
            b.clicked.connect(lambda _=False, k=key: self._apply_preset(k))
            gl.addWidget(b, i // 2, (i % 2) * 2, 1, 2)
        reset = QPushButton()
        self._i18n.append((reset, "txt_preset_reset", "setText"))
        reset.clicked.connect(self._reset_style)
        gl.addWidget(reset, (len(PRESETS) + 1) // 2, 0, 1, 4)

    # ---- widget factories -------------------------------------------------
    def _label(self, key: str) -> QLabel:
        lbl = QLabel()
        lbl.setMinimumWidth(0)
        lbl.setMaximumWidth(78)
        lbl.setToolTip("")
        self._i18n.append((lbl, key, "setText"))
        return lbl

    def _group(self, key: str, layout: QVBoxLayout) -> Tuple[QGroupBox, QGridLayout]:
        g = QGroupBox()
        g.setObjectName("TextInspectorGroup")
        self._i18n.append((g, key, "setTitle"))
        gl = QGridLayout(g)
        gl.setContentsMargins(5, 5, 5, 5)
        gl.setHorizontalSpacing(5)
        gl.setVerticalSpacing(3)
        gl.setColumnStretch(1, 1)
        gl.setColumnStretch(3, 1)
        layout.addWidget(g)
        return g, gl

    def _row(self, gl: QGridLayout, row: int, label_key: str, widget: QWidget, col: int = 0, span: int = 1) -> None:
        gl.addWidget(self._label(label_key), row, col)
        gl.addWidget(widget, row, col + 1, 1, span)

    def _spin(self, lo: float, hi: float, step: float, attr: str, decimals: int) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setDecimals(decimals)
        sp.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        sp.setMinimumWidth(54)
        sp.setMaximumWidth(92)
        sp.setMinimumHeight(22)
        sp.setMaximumHeight(25)
        is_int = attr in ("font_size", "stroke_width")
        sp.valueChanged.connect(lambda v: self._edit(lambda ts: setattr(ts, attr, int(v) if is_int else float(v))))
        return sp

    def _check(self, key: str, attr: str) -> QCheckBox:
        cb = QCheckBox()
        self._i18n.append((cb, key, "setText"))
        cb.toggled.connect(lambda v: self._edit(lambda ts: setattr(ts, attr, bool(v))))
        return cb

    def _toggle(self, glyph: str, tip_key: str, attr: str, weight: Optional[Any] = None) -> QPushButton:
        b = QPushButton(glyph)
        b.setCheckable(True)
        b.setFixedSize(28, 24)
        f = b.font()
        if glyph == "B":
            f.setBold(True)
        if glyph == "I":
            f.setItalic(True)
        if glyph == "U":
            f.setUnderline(True)
        b.setFont(f)
        self._i18n.append((b, tip_key, "setToolTip"))
        b.toggled.connect(lambda v: self._edit(lambda ts: setattr(ts, attr, bool(v))))
        return b

    def _combo(self, items: List[Tuple[str, str]], attr: str) -> QComboBox:
        cb = QComboBox()
        cb.setMinimumHeight(22)
        cb.setMaximumHeight(25)
        cb.setMinimumContentsLength(6)
        cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._combos.append((cb, items))
        cb.currentIndexChanged.connect(lambda _i: self._edit(lambda ts: setattr(ts, attr, str(cb.currentData()))))
        return cb

    def _color(self, attr: str) -> ColorButton:
        btn = ColorButton(lambda: tr("txt_pick_color", self.c.lang))
        btn.color_picked.connect(lambda hx: self._edit(lambda ts: setattr(ts, attr, hx)))
        return btn

    # ---- editing ----------------------------------------------------------
    def _snapshot(self) -> None:
        now = time.monotonic()
        if now - self._last_snapshot > 1.0:
            self.c.project.push_undo_snapshot()
            self._last_snapshot = now

    def _edit(self, mutate: Callable[[TextStyleSettings], None]) -> None:
        if self._loading:
            return
        clip = self.c.get_selected_clip()
        if clip is None or clip.clip_type != "text":
            return
        self._snapshot()
        mutate(clip.text_style)
        clip.name = clip.text_style.text.replace("\n", " ")[:24] or clip.name
        self.host.refresh_preview_only()

    def _edit_clip(self, mutate: Callable[[TimelineClip], None]) -> None:
        if self._loading:
            return
        clip = self.c.get_selected_clip()
        if clip is None:
            return
        self._snapshot()
        mutate(clip)
        self.host.refresh_preview_only()

    def _apply_preset(self, key: str) -> None:
        clip = self.c.get_selected_clip()
        if clip is None or clip.clip_type != "text":
            return
        self.c.project.push_undo_snapshot()
        for k, v in PRESETS[key].items():
            setattr(clip.text_style, k, v)
        self.load_clip()
        self.host.refresh_preview_only()

    def _reset_style(self) -> None:
        clip = self.c.get_selected_clip()
        if clip is None or clip.clip_type != "text":
            return
        self.c.project.push_undo_snapshot()
        text = clip.text_style.text
        clip.text_style = TextStyleSettings(text=text)
        self.load_clip()
        self.host.refresh_preview_only()

    # ---- sync -------------------------------------------------------------
    def focus_text(self) -> None:
        self.te_text.setFocus()
        self.te_text.selectAll()

    def load_clip(self) -> None:
        clip = self.c.get_selected_clip()
        is_text = clip is not None and clip.clip_type == "text"
        self.lbl_hint.setVisible(not is_text)
        self.body.setVisible(is_text)
        if not is_text or clip is None:
            return
        ts = clip.text_style
        self._loading = True
        try:
            if self.te_text.toPlainText() != ts.text:
                self.te_text.setPlainText(ts.text)
            self.cmb_font.setCurrentFont(QFont(ts.font_family))
            self.sp_size.setValue(ts.font_size)
            self.btn_b.setChecked(ts.bold)
            self.btn_i.setChecked(ts.italic)
            self.btn_u.setChecked(ts.underline)
            self.cmb_align.setCurrentIndex(max(0, self.cmb_align.findData(ts.align)))
            self.sp_ls.setValue(ts.letter_spacing)
            self.sp_line.setValue(ts.line_spacing)
            self.cb_fill.set_hex(ts.text_color_hex)
            self.sp_fill_op.setValue(ts.text_opacity)
            self.cb_stroke.set_hex(ts.stroke_color_hex)
            self.sp_stroke.setValue(ts.stroke_width)
            self.ck_shadow.setChecked(ts.shadow_enabled)
            self.cb_shadow.set_hex(ts.shadow_color_hex)
            self.sp_sdx.setValue(ts.shadow_dx)
            self.sp_sdy.setValue(ts.shadow_dy)
            self.sp_sblur.setValue(ts.shadow_blur)
            self.sp_sop.setValue(ts.shadow_opacity)
            self.ck_glow.setChecked(ts.glow_enabled)
            self.cb_glow.set_hex(ts.glow_color_hex)
            self.sp_glow.setValue(ts.glow_radius)
            self.ck_bg.setChecked(ts.bg_enabled)
            self.cb_bg.set_hex(ts.bg_color_hex)
            self.sp_bgop.setValue(ts.bg_opacity)
            self.sp_bgpad.setValue(ts.bg_padding)
            self.sp_bgrad.setValue(ts.bg_radius)
            self.ck_refl.setChecked(ts.reflection_enabled)
            self.sp_rop.setValue(ts.reflection_opacity)
            self.sp_rgap.setValue(ts.reflection_gap)
            self.ck_flip_h.setChecked(clip.flip_h)
            self.ck_flip_v.setChecked(clip.flip_v)
            self.cmb_in.setCurrentIndex(max(0, self.cmb_in.findData(ts.animation_in)))
            self.cmb_out.setCurrentIndex(max(0, self.cmb_out.findData(ts.animation_out)))
            self.sp_adur.setValue(ts.animation_duration)
        finally:
            self._loading = False

    def retranslate(self) -> None:
        lang = self.c.lang
        for widget, key, setter in self._i18n:
            getattr(widget, setter)(tr(key, lang))
        for combo, items in self._combos:
            cur = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for data_key, tr_key in items:
                combo.addItem(tr(tr_key, lang), data_key)
            combo.setCurrentIndex(max(0, combo.findData(cur)) if cur is not None else 0)
            combo.blockSignals(False)
        self.load_clip()
