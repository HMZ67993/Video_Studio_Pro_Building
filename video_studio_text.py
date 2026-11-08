# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Headless rich-text rendering engine.

Renders a TextStyleSettings-like object into a BGR image + alpha mask with:
font family / bold / italic-aware file lookup, size, alignment, letter & line spacing,
underline, fill opacity, outline (stroke), drop shadow (offset/blur/opacity), glow,
background box (padding/radius/opacity), mirror reflection, and in/out animations
(fade, slide, zoom, typewriter). No Qt dependency, so it is fully unit-testable.
"""

import os
import sys
from collections import OrderedDict
from dataclasses import asdict, is_dataclass
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

ANIMATIONS_IN = ("none", "fade", "slide_up", "slide_down", "zoom", "typewriter")
ANIMATIONS_OUT = ("none", "fade", "slide_up", "slide_down", "zoom")
ALIGNMENTS = ("left", "center", "right")

_FALLBACK_FAMILIES = ("Segoe UI", "Tahoma", "Arial", "Noto Sans Arabic", "DejaVu Sans", "Liberation Sans", "FreeSans")
_HAS_RAQM = bool(features.check("raqm"))

_font_index: Optional[Dict[str, Dict[str, str]]] = None


def _font_dirs() -> List[Path]:
    dirs: List[Path] = []
    if sys.platform.startswith("win"):
        dirs.append(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts", Path.home() / ".local/share/fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts")]
    return dirs


def _scan_fonts() -> Dict[str, Dict[str, str]]:
    """Map lower-case family -> {regular,bold,italic,bolditalic: path}. Built once, lazily."""
    index: Dict[str, Dict[str, str]] = {}
    for base in _font_dirs():
        if not base.exists():
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.lower().endswith((".ttf", ".otf")):
                    continue
                path = os.path.join(root, fn)
                try:
                    fam, style = ImageFont.truetype(path, 12).getname()
                except Exception:
                    continue
                st = (style or "").lower()
                bold = "bold" in st or "black" in st or "heavy" in st
                ital = "italic" in st or "oblique" in st
                key = ("bold" if bold else "") + ("italic" if ital else "") or "regular"
                if not bold and not ital and st not in ("regular", "normal", "book", ""):
                    # Light/Medium/Condensed variants: keep only if no plain regular exists yet.
                    index.setdefault(fam.lower(), {}).setdefault("regular", path)
                    continue
                index.setdefault(fam.lower(), {})[key] = path
    return index


def font_index() -> Dict[str, Dict[str, str]]:
    global _font_index
    if _font_index is None:
        _font_index = _scan_fonts()
    return _font_index


def available_font_families() -> List[str]:
    return sorted({k.title() if k.islower() else k for k in font_index()})


@lru_cache(maxsize=256)
def resolve_font(family: str, bold: bool, italic: bool, size: int) -> Any:
    idx = font_index()
    wanted = [family] + list(_FALLBACK_FAMILIES)
    variant = ("bold" if bold else "") + ("italic" if italic else "") or "regular"
    for fam in wanted:
        entry = idx.get((fam or "").lower())
        if not entry:
            continue
        for key in (variant, "bold" if bold else "regular", "regular", next(iter(entry))):
            path = entry.get(key)
            if path:
                try:
                    return _load(path, size)
                except Exception:
                    continue
    return ImageFont.load_default()


def _load(path: str, size: int) -> Any:
    if _HAS_RAQM:
        return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)
    return ImageFont.truetype(path, size)


def _shape(text: str) -> str:
    """Join/reorder Arabic only when Pillow lacks raqm (optional arabic_reshaper + python-bidi)."""
    if _HAS_RAQM or not any("\u0600" <= ch <= "\u06ff" for ch in text):
        return text
    try:
        import arabic_reshaper  # type: ignore
        from bidi.algorithm import get_display  # type: ignore

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _hex_rgb(hex_str: str, default: Tuple[int, int, int] = (255, 255, 255)) -> Tuple[int, int, int]:
    h = (hex_str or "").lstrip("#")
    if len(h) != 6:
        return default
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return default


def _g(ts: Any, name: str, default: Any) -> Any:
    return getattr(ts, name, default)


def _anim_state(ts: Any, local_t: Optional[float], duration: Optional[float]) -> Tuple[float, float, str, str]:
    """Return (progress_in, progress_out, anim_in, anim_out); progress 1.0 means fully shown."""
    if local_t is None or duration is None:
        return 1.0, 1.0, "none", "none"
    dur = max(0.05, float(_g(ts, "animation_duration", 0.5)))
    p_in = max(0.0, min(1.0, local_t / dur))
    p_out = max(0.0, min(1.0, (duration - local_t) / dur))
    return p_in, p_out, str(_g(ts, "animation_in", "none")), str(_g(ts, "animation_out", "none"))


def _blur_alpha(mask: Image.Image, radius: float) -> Image.Image:
    return mask.filter(ImageFilter.GaussianBlur(max(0.1, radius))) if radius > 0 else mask


def _tint(mask: Image.Image, rgb: Tuple[int, int, int], opacity: float) -> Image.Image:
    layer = Image.new("RGBA", mask.size, rgb + (0,))
    arr = np.asarray(mask, dtype=np.float32) * max(0.0, min(1.0, opacity))
    layer.putalpha(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)))
    return layer


_CACHE: "OrderedDict[Tuple[Any, ...], Tuple[np.ndarray, np.ndarray]]" = OrderedDict()
_CACHE_MAX = 24
_CACHE_LOCK = threading.Lock()  # preview thread, UI thread and export thread all render text


def render_text_layer(
    ts: Any,
    width: int,
    height: int,
    anchor_y: float = 0.78,
    local_t: Optional[float] = None,
    duration: Optional[float] = None,
    flip_h: bool = False,
    flip_v: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """Render styled text to (bgr uint8 HxWx3, alpha float32 HxW in 0..1). Position offsets are applied by the compositor."""
    p_in, p_out, a_in, a_out = _anim_state(ts, local_t, duration)
    d = asdict(ts) if is_dataclass(ts) else dict(vars(ts))
    key = (width, height, anchor_y, round(p_in, 2), round(p_out, 2), a_in, a_out, flip_h, flip_v, tuple(sorted((k, str(v)) for k, v in d.items())))
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
            return hit[0], hit[1]

    scale_h = height / 1080.0
    text = str(_g(ts, "text", "")) or " "
    if a_in == "typewriter" and p_in < 1.0:
        text = text[: max(1, int(len(text) * p_in))]
    size_mult = 1.0
    if a_in == "zoom" and p_in < 1.0:
        size_mult = 0.55 + 0.45 * p_in
    if a_out == "zoom" and p_out < 1.0:
        size_mult = min(size_mult, 0.55 + 0.45 * p_out)
    font_px = max(10, int(float(_g(ts, "font_size", 48)) * scale_h * size_mult))
    font = resolve_font(str(_g(ts, "font_family", "Segoe UI")), bool(_g(ts, "bold", True)), bool(_g(ts, "italic", False)), font_px)

    probe = ImageDraw.Draw(Image.new("RGBA", (4, 4)))
    lines = [_shape(ln) for ln in text.split("\n")] or [" "]
    spacing = float(_g(ts, "letter_spacing", 0.0)) * scale_h
    has_arabic = any("\u0600" <= ch <= "\u06ff" for ch in text)
    use_spacing = abs(spacing) > 0.01 and not has_arabic  # per-character drawing would break Arabic joining
    widths: List[float] = []
    for ln in lines:
        w_ln = probe.textlength(ln, font=font)
        if use_spacing:
            w_ln += spacing * max(0, len(ln) - 1)
        widths.append(w_ln)
    try:
        ascent, descent = font.getmetrics()
    except Exception:
        ascent, descent = font_px, int(font_px * 0.25)
    line_h = (ascent + descent) * max(0.5, float(_g(ts, "line_spacing", 1.0)))
    block_w = max(widths) if widths else 1.0
    block_h = line_h * len(lines)

    cx = width / 2.0
    top = anchor_y * height - block_h / 2.0
    if a_in == "slide_up" and p_in < 1.0:
        top += (1.0 - p_in) * height * 0.08
    if a_in == "slide_down" and p_in < 1.0:
        top -= (1.0 - p_in) * height * 0.08
    if a_out == "slide_up" and p_out < 1.0:
        top -= (1.0 - p_out) * height * 0.08
    if a_out == "slide_down" and p_out < 1.0:
        top += (1.0 - p_out) * height * 0.08
    align = str(_g(ts, "align", "center"))

    stroke_w = max(0, int(round(float(_g(ts, "stroke_width", 0)) * scale_h)))
    fill_rgb = _hex_rgb(str(_g(ts, "text_color_hex", "#FFFFFF")))
    stroke_rgb = _hex_rgb(str(_g(ts, "stroke_color_hex", "#000000")), (0, 0, 0))
    fill_a = int(255 * max(0, min(100, float(_g(ts, "text_opacity", 100)))) / 100.0)

    text_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    td = ImageDraw.Draw(text_layer)
    for i, ln in enumerate(lines):
        lw = widths[i]
        x0 = cx - block_w / 2.0 if align == "left" else (cx + block_w / 2.0 - lw if align == "right" else cx - lw / 2.0)
        y0 = top + i * line_h
        if use_spacing:
            x = x0
            for ch in ln:
                td.text((x, y0), ch, font=font, fill=fill_rgb + (fill_a,), stroke_width=stroke_w, stroke_fill=stroke_rgb + (255,))
                x += probe.textlength(ch, font=font) + spacing
        else:
            td.text((x0, y0), ln, font=font, fill=fill_rgb + (fill_a,), stroke_width=stroke_w, stroke_fill=stroke_rgb + (255,))
        if bool(_g(ts, "underline", False)):
            uy = y0 + ascent + max(2, font_px // 12)
            td.line([(x0, uy), (x0 + lw, uy)], fill=fill_rgb + (fill_a,), width=max(1, font_px // 14))

    layers: List[Image.Image] = []
    if bool(_g(ts, "bg_enabled", False)):
        pad = float(_g(ts, "bg_padding", 14)) * scale_h
        bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(bg).rounded_rectangle(
            [cx - block_w / 2 - pad, top - pad * 0.6, cx + block_w / 2 + pad, top + block_h + pad * 0.6],
            radius=float(_g(ts, "bg_radius", 10)) * scale_h,
            fill=_hex_rgb(str(_g(ts, "bg_color_hex", "#000000")), (0, 0, 0)) + (int(255 * float(_g(ts, "bg_opacity", 75)) / 100.0),),
        )
        layers.append(bg)
    alpha_mask = text_layer.split()[3]
    if bool(_g(ts, "glow_enabled", False)):
        r = float(_g(ts, "glow_radius", 12)) * scale_h
        glow_mask = _blur_alpha(alpha_mask, r).point(lambda v: min(255, int(v * 2.2)))
        layers.append(_tint(glow_mask, _hex_rgb(str(_g(ts, "glow_color_hex", "#00D2E6")), (0, 210, 230)), 1.0))
    if bool(_g(ts, "shadow_enabled", False)):
        sh = Image.new("L", (width, height), 0)
        sh.paste(alpha_mask, (int(float(_g(ts, "shadow_dx", 4)) * scale_h), int(float(_g(ts, "shadow_dy", 4)) * scale_h)))
        sh = _blur_alpha(sh, float(_g(ts, "shadow_blur", 6)) * scale_h)
        layers.append(_tint(sh, _hex_rgb(str(_g(ts, "shadow_color_hex", "#000000")), (0, 0, 0)), float(_g(ts, "shadow_opacity", 70)) / 100.0))
    if bool(_g(ts, "reflection_enabled", False)):
        y_a = max(0, int(top - stroke_w - 2))
        y_b = min(height, int(top + block_h + stroke_w + 2))
        if y_b > y_a:
            region = text_layer.crop((0, y_a, width, y_b)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            arr = np.asarray(region, dtype=np.float32).copy()
            fade = np.linspace(1.0, 0.0, arr.shape[0], dtype=np.float32)[:, None]
            arr[..., 3] *= fade * (float(_g(ts, "reflection_opacity", 40)) / 100.0)
            refl = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            refl.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (0, y_b + int(float(_g(ts, "reflection_gap", 4)) * scale_h)))
            layers.append(refl)
    layers.append(text_layer)

    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for layer in layers:
        out = Image.alpha_composite(out, layer)
    rgba = np.asarray(out, dtype=np.uint8)
    bgr = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2BGR)
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    if a_in == "fade":
        alpha *= p_in
    if a_out == "fade":
        alpha *= p_out
    if flip_h:
        bgr, alpha = cv2.flip(bgr, 1), cv2.flip(alpha, 1)
    if flip_v:
        bgr, alpha = cv2.flip(bgr, 0), cv2.flip(alpha, 0)

    with _CACHE_LOCK:
        _CACHE[key] = (bgr, alpha)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return bgr, alpha


def alpha_bounds(alpha: np.ndarray, thresh: float = 0.02) -> Optional[Tuple[int, int, int, int]]:
    """Bounding box (x0, y0, x1, y1) of visible pixels, or None if empty."""
    ys, xs = np.where(alpha > thresh)
    if xs.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
