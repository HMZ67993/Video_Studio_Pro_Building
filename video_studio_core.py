# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Headless Local Video Editing & Rendering Engine (100% Local Processing)
"""

import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import threading
import uuid
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from video_studio_text import alpha_bounds, render_text_layer

ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

RESOLUTION_PRESETS: Dict[str, float] = {
    "4K (2160p)": 2.0,
    "1080p (Full HD)": 1.0,
    "720p (HD)": 2.0 / 3.0,
    "540p (Proxy)": 0.5,
}

SPEED_CURVE_PRESETS: Dict[str, List[Tuple[float, float]]] = {
    "constant": [(0.0, 1.0), (1.0, 1.0)],
    "montage": [(0.0, 0.5), (0.35, 2.5), (0.7, 2.5), (1.0, 0.6)],
    "hero": [(0.0, 2.0), (0.45, 2.2), (0.55, 0.25), (1.0, 0.3)],
    "jump_cut": [(0.0, 1.0), (0.4, 4.0), (0.6, 4.0), (1.0, 1.0)],
}

EQUALIZER_PRESETS: Dict[str, List[Tuple[int, int]]] = {
    "flat": [(100, 0), (350, 0), (1000, 0), (3500, 0), (10000, 0)],
    "voice": [(100, -4), (350, 2), (1000, 4), (3500, 3), (10000, 1)],
    "bass": [(100, 6), (350, 4), (1000, 0), (3500, -1), (10000, 0)],
    "treble": [(100, -1), (350, 0), (1000, 1), (3500, 4), (10000, 6)],
}


@dataclass
class Keyframe:
    time_offset: float
    value: float
    easing: str = "linear"


@dataclass
class ColorGradeSettings:
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    sharpness: float = 0.0
    temperature: float = 0.0
    tint: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0
    lut_path: str = ""


@dataclass
class ChromaKeySettings:
    enabled: bool = False
    key_color_hex: str = "#00FF00"
    similarity: float = 0.25
    blend: float = 0.10


@dataclass
class MaskSettings:
    shape: str = "none"
    feather: float = 10.0
    invert: bool = False


@dataclass
class TextStyleSettings:
    text: str = "نص جديد / New Text"
    font_family: str = "Segoe UI"
    font_size: int = 48
    bold: bool = True
    italic: bool = False
    underline: bool = False
    align: str = "center"
    letter_spacing: float = 0.0
    line_spacing: float = 1.0
    text_color_hex: str = "#FFFFFF"
    text_opacity: float = 100.0
    stroke_color_hex: str = "#000000"
    stroke_width: int = 3
    shadow_enabled: bool = False
    shadow_color_hex: str = "#000000"
    shadow_dx: float = 4.0
    shadow_dy: float = 4.0
    shadow_blur: float = 6.0
    shadow_opacity: float = 70.0
    glow_enabled: bool = False
    glow_color_hex: str = "#00D2E6"
    glow_radius: float = 12.0
    bg_enabled: bool = False
    bg_color_hex: str = "#000000"
    bg_opacity: float = 75.0
    bg_padding: float = 14.0
    bg_radius: float = 10.0
    reflection_enabled: bool = False
    reflection_opacity: float = 40.0
    reflection_gap: float = 4.0
    animation_in: str = "none"
    animation_out: str = "none"
    animation_duration: float = 0.5


@dataclass
class TimelineClip:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str = "Clip"
    clip_type: str = "video"
    source_path: str = ""
    proxy_path: str = ""
    timeline_start: float = 0.0
    duration: float = 5.0
    source_in: float = 0.0
    source_out: float = 5.0
    pos_x: float = 0.0
    pos_y: float = 0.0
    scale: float = 100.0
    rotation: float = 0.0
    opacity: float = 100.0
    flip_h: bool = False
    flip_v: bool = False
    crop_left: float = 0.0
    crop_right: float = 0.0
    crop_top: float = 0.0
    crop_bottom: float = 0.0
    blend_mode: str = "normal"
    stabilize: bool = False
    speed: float = 1.0
    keep_pitch: bool = True
    reverse: bool = False
    speed_curve: str = "constant"
    is_freeze_frame: bool = False
    volume_db: float = 0.0
    muted: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0
    pitch_semitones: float = 0.0
    eq_preset: str = "flat"
    waveform_peaks: List[float] = field(default_factory=list)
    visual_effect: str = "none"
    effect_intensity: float = 100.0
    transition_in: str = "none"
    transition_duration: float = 0.5
    color: ColorGradeSettings = field(default_factory=ColorGradeSettings)
    chroma: ChromaKeySettings = field(default_factory=ChromaKeySettings)
    mask: MaskSettings = field(default_factory=MaskSettings)
    text_style: TextStyleSettings = field(default_factory=TextStyleSettings)
    keyframes: Dict[str, List[Keyframe]] = field(default_factory=dict)
    ai_metadata: Dict[str, Any] = field(default_factory=dict)
    anim_in: str = "none"        # entrance animation for visual clips (fade, zoom_in, slide_left, ...)
    anim_out: str = "none"       # exit animation
    anim_loop: str = "none"      # looping animation while visible (pulse, swing, float, spin, ...)
    anim_duration: float = 0.5   # seconds for the in / out animations

    @property
    def timeline_end(self) -> float:
        return self.timeline_start + max(0.05, self.duration)


@dataclass
class TimelineTrack:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Track 1"
    track_type: str = "video"
    muted: bool = False
    hidden: bool = False
    locked: bool = False
    clips: List[TimelineClip] = field(default_factory=list)


def track_accepts(track_type: str, clip_type: str) -> bool:
    """Which clip kinds may live on which kind of track (stickers also stay valid on old video tracks)."""
    if track_type == "video":
        return clip_type in ("video", "image", "sticker")
    if track_type == "sticker":
        return clip_type == "sticker"
    return track_type == clip_type


@dataclass
class TimelineMarker:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:6])
    time_sec: float = 0.0
    label: str = "Marker"
    color_hex: str = "#F59E0B"


def apply_easing(t: float, mode: str = "linear") -> float:
    t = max(0.0, min(1.0, float(t)))
    if mode == "ease_in":
        return t * t
    if mode == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if mode == "ease_in_out":
        return 3.0 * t * t - 2.0 * t * t * t
    return t


def interpolate_keyframes(keyframes: List[Keyframe], local_time: float, default_val: float) -> float:
    if not keyframes:
        return default_val
    sorted_kfs = sorted(keyframes, key=lambda k: k.time_offset)
    if local_time <= sorted_kfs[0].time_offset:
        return sorted_kfs[0].value
    if local_time >= sorted_kfs[-1].time_offset:
        return sorted_kfs[-1].value
    for i in range(len(sorted_kfs) - 1):
        k0 = sorted_kfs[i]
        k1 = sorted_kfs[i + 1]
        if k0.time_offset <= local_time <= k1.time_offset:
            span = k1.time_offset - k0.time_offset
            if span <= 1e-6:
                return k1.value
            raw_t = (local_time - k0.time_offset) / span
            eased_t = apply_easing(raw_t, k0.easing)
            return k0.value + (k1.value - k0.value) * eased_t
    return default_val


def evaluate_clip_property(clip: "TimelineClip", prop_name: str, local_time: float, default: float) -> float:
    """Evaluate any numeric clip property, including nested color-grade fields."""
    return interpolate_keyframes(clip.keyframes.get(prop_name, []), local_time, float(default))


def evaluate_speed_curve(curve_name: str, normalized_pos: float, base_speed: float = 1.0) -> float:
    points = SPEED_CURVE_PRESETS.get(curve_name, SPEED_CURVE_PRESETS["constant"])
    pos = max(0.0, min(1.0, float(normalized_pos)))
    for i in range(len(points) - 1):
        t0, v0 = points[i]
        t1, v1 = points[i + 1]
        if t0 <= pos <= t1:
            span = max(1e-6, t1 - t0)
            ratio = (pos - t0) / span
            return max(0.1, min(100.0, base_speed * (v0 + (v1 - v0) * ratio)))
    return max(0.1, min(100.0, base_speed))


def parse_cube_lut(cube_path: str) -> Optional[Tuple[int, np.ndarray]]:
    path = Path(cube_path)
    if not path.exists():
        return None
    size = 0
    rows: List[List[float]] = []
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("TITLE") or line.startswith("DOMAIN_"):
                continue
            if line.upper().startswith("LUT_3D_SIZE"):
                parts = line.split()
                if len(parts) >= 2:
                    size = int(parts[1])
                continue
            parts = line.split()
            if len(parts) == 3:
                rows.append([float(parts[0]), float(parts[1]), float(parts[2])])
        if size <= 1 or len(rows) != size * size * size:
            return None
        arr = np.array(rows, dtype=np.float32).reshape((size, size, size, 3))
        return size, arr
    except Exception:
        return None


def apply_cube_lut_to_frame(frame_bgr: np.ndarray, lut_size: int, lut_table: np.ndarray) -> np.ndarray:
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    idx = np.clip((rgb * (lut_size - 1)).round().astype(np.int32), 0, lut_size - 1)
    mapped_rgb = lut_table[idx[..., 2], idx[..., 1], idx[..., 0]]
    out_rgb = np.clip(mapped_rgb * 255.0, 0, 255).astype(np.uint8)
    return cv2.cvtColor(out_rgb, cv2.COLOR_RGB2BGR)


def _hex_to_bgr(hex_str: str) -> Tuple[int, int, int]:
    clean = (hex_str or "#00FF00").lstrip("#")
    if len(clean) != 6:
        return (0, 255, 0)
    try:
        return (int(clean[4:6], 16), int(clean[2:4], 16), int(clean[0:2], 16))
    except ValueError:
        return (0, 255, 0)


_MASK_CACHE: "OrderedDict[str, np.ndarray]" = OrderedDict()
_MASK_LOCK = threading.Lock()


def _load_mask(path: str) -> Optional[np.ndarray]:
    with _MASK_LOCK:
        hit = _MASK_CACHE.get(path)
        if hit is not None:
            _MASK_CACHE.move_to_end(path)
            return hit
    try:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    except Exception:
        img = None
    if img is None:
        return None
    arr = img.astype(np.float32) / 255.0
    with _MASK_LOCK:
        _MASK_CACHE[path] = arr
        while len(_MASK_CACHE) > 96:
            _MASK_CACHE.popitem(last=False)
    return arr


def cutout_alpha(clip: "TimelineClip", local_time: float, h: int, w: int) -> Optional[np.ndarray]:
    """Alpha (h, w) from the AI cutout masks stored in clip.ai_metadata['cutout'], or None."""
    meta = clip.ai_metadata.get("cutout")
    if not meta:
        return None
    if clip.clip_type == "image":
        src_t = 0.0
    else:
        eff = evaluate_speed_curve(clip.speed_curve, local_time / max(0.1, clip.duration), clip.speed)
        src_t = clip.source_in + local_time * eff
    idx = int(round((src_t - float(meta.get("start", 0.0))) * float(meta.get("fps", 1.0))))
    idx = max(0, min(int(meta.get("count", 1)) - 1, idx))
    m = _load_mask(os.path.join(str(meta.get("dir", "")), f"m{idx:05d}.png"))
    if m is None:
        return None
    # Refine mask edges: close tiny pinholes, preserve contours with an edge-aware
    # bilateral pass, then soften only the alpha boundary to avoid a cut-out halo.
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    m = cv2.bilateralFilter(m, 5, 24, 5)
    m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)
    alpha = np.clip((m.astype(np.float32) - 0.15) / 0.7, 0.0, 1.0)
    return cv2.GaussianBlur(alpha, (3, 3), 0.55)


def process_frame_effects(frame_bgr: np.ndarray, clip: TimelineClip, local_time: float = 0.0) -> Tuple[np.ndarray, np.ndarray]:
    h, w = frame_bgr.shape[:2]
    img = frame_bgr.copy()

    cl = max(0.0, min(0.45, clip.crop_left))
    cr = max(0.0, min(0.45, clip.crop_right))
    ct = max(0.0, min(0.45, clip.crop_top))
    cb = max(0.0, min(0.45, clip.crop_bottom))
    if cl > 0 or cr > 0 or ct > 0 or cb > 0:
        x1 = int(w * cl)
        x2 = max(x1 + 2, int(w * (1.0 - cr)))
        y1 = int(h * ct)
        y2 = max(y1 + 2, int(h * (1.0 - cb)))
        img = cv2.resize(img[y1:y2, x1:x2], (w, h), interpolation=cv2.INTER_LINEAR)

    if clip.flip_h and clip.flip_v:
        img = cv2.flip(img, -1)
    elif clip.flip_h:
        img = cv2.flip(img, 1)
    elif clip.flip_v:
        img = cv2.flip(img, 0)

    cg = copy.copy(clip.color)
    for _prop in ("brightness", "contrast", "saturation", "sharpness", "temperature", "tint", "highlights", "shadows"):
        setattr(cg, _prop, evaluate_clip_property(clip, f"color.{_prop}", local_time, getattr(cg, _prop)))
    if (
        abs(cg.brightness) > 0.1
        or abs(cg.contrast) > 0.1
        or abs(cg.temperature) > 0.1
        or abs(cg.tint) > 0.1
        or abs(cg.highlights) > 0.1
        or abs(cg.shadows) > 0.1
    ):
        f = img.astype(np.float32)
        alpha_c = 1.0 + (cg.contrast / 100.0)
        beta_b = cg.brightness * 1.8
        f = (f - 127.5) * alpha_c + 127.5 + beta_b
        if abs(cg.temperature) > 0.1:
            f[..., 2] += cg.temperature * 0.6
            f[..., 0] -= cg.temperature * 0.6
        if abs(cg.tint) > 0.1:
            f[..., 1] -= cg.tint * 0.5
        if abs(cg.shadows) > 0.1 or abs(cg.highlights) > 0.1:
            lum = np.mean(f, axis=2, keepdims=True) / 255.0
            f += (1.0 - lum) * (cg.shadows * 0.6) + lum * (cg.highlights * 0.6)
        img = np.clip(f, 0, 255).astype(np.uint8)

    if abs(cg.saturation) > 0.1:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + cg.saturation / 100.0), 0, 255)
        img = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

    if cg.sharpness > 0.5:
        blurred = cv2.GaussianBlur(img, (0, 0), 2.0)
        amount = cg.sharpness / 50.0
        img = cv2.addWeighted(img, 1.0 + amount, blurred, -amount, 0)

    if cg.lut_path:
        parsed_lut = parse_cube_lut(cg.lut_path)
        if parsed_lut is not None:
            img = apply_cube_lut_to_frame(img, parsed_lut[0], parsed_lut[1])

    _effect_base = img.copy()
    fx = clip.visual_effect
    if fx == "vintage_bw":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    elif fx == "warm_film":
        f = img.astype(np.float32)
        f[..., 2] = np.clip(f[..., 2] * 1.12 + 8, 0, 255)
        f[..., 0] = np.clip(f[..., 0] * 0.88, 0, 255)
        img = f.astype(np.uint8)
    elif fx == "cyber_teal":
        f = img.astype(np.float32)
        lum = np.mean(f, axis=2)
        shadows_mask = lum < 128
        f[shadows_mask, 0] = np.clip(f[shadows_mask, 0] * 1.2 + 12, 0, 255)
        f[~shadows_mask, 2] = np.clip(f[~shadows_mask, 2] * 1.15 + 10, 0, 255)
        img = f.astype(np.uint8)
    elif fx == "vhs_glitch":
        shift = max(2, int(w * 0.012))
        b, g, r = cv2.split(img)
        img = cv2.merge([np.roll(b, -shift, axis=1), g, np.roll(r, shift, axis=1)])
    elif fx == "motion_blur":
        ksize = 9
        kernel = np.zeros((ksize, ksize), dtype=np.float32)
        kernel[int((ksize - 1) / 2), :] = np.ones(ksize, dtype=np.float32) / ksize
        img = cv2.filter2D(img, -1, kernel)
    elif fx == "camera_shake":
        dx = int(math.sin(local_time * 28.0) * 10.0)
        dy = int(math.cos(local_time * 34.0) * 8.0)
        m = np.float32([[1, 0, dx], [0, 1, dy]])
        img = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)
    elif fx == "vignette":
        yy, xx = np.ogrid[:h, :w]
        cx, cy = w / 2.0, h / 2.0
        dist = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
        vig = np.clip(1.0 - 0.55 * (dist ** 2), 0.2, 1.0).astype(np.float32)
        img = (img.astype(np.float32) * vig[..., None]).astype(np.uint8)

    elif fx == "gaussian_blur":
        img = cv2.GaussianBlur(img, (0, 0), 2.0 + 10.0 * max(0.0, min(1.0, clip.effect_intensity / 100.0)))
    elif fx == "pixelate":
        factor = max(2, int(3 + 25 * max(0.0, min(1.0, clip.effect_intensity / 100.0))))
        small = cv2.resize(img, (max(1, w // factor), max(1, h // factor)), interpolation=cv2.INTER_AREA)
        img = cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    elif fx == "invert":
        img = 255 - img
    elif fx == "sepia":
        kernel = np.array([[0.272, 0.534, 0.131], [0.349, 0.686, 0.168], [0.393, 0.769, 0.189]], dtype=np.float32)
        img = np.clip(cv2.transform(img, kernel), 0, 255).astype(np.uint8)
    elif fx == "negative_film":
        img = 255 - img
        img = cv2.convertScaleAbs(img, alpha=0.92, beta=8)

    _intensity = max(0.0, min(100.0, evaluate_clip_property(clip, "effect_intensity", local_time, clip.effect_intensity))) / 100.0
    if fx != "none" and _intensity < 0.999:
        img = cv2.addWeighted(_effect_base, 1.0 - _intensity, img, _intensity, 0)

    cut_alpha = cutout_alpha(clip, local_time, h, w)
    if cut_alpha is not None:
        cl2, cr2, ct2, cb2 = cl, cr, ct, cb
        if cl2 > 0 or cr2 > 0 or ct2 > 0 or cb2 > 0:
            x1 = int(w * cl2)
            x2 = max(x1 + 2, int(w * (1.0 - cr2)))
            y1 = int(h * ct2)
            y2 = max(y1 + 2, int(h * (1.0 - cb2)))
            cut_alpha = cv2.resize(cut_alpha[y1:y2, x1:x2], (w, h), interpolation=cv2.INTER_LINEAR)
        if clip.flip_h:
            cut_alpha = cv2.flip(cut_alpha, 1)
        if clip.flip_v:
            cut_alpha = cv2.flip(cut_alpha, 0)

    # Note: Chroma Key is evaluated on the raw/un-graded color difference so grading/LUTs don't shift green screen hue
    alpha = np.ones((h, w), dtype=np.float32)
    if clip.chroma.enabled:
        key_bgr = np.array(_hex_to_bgr(clip.chroma.key_color_hex), dtype=np.float32)
        diff = np.linalg.norm(frame_bgr.astype(np.float32) - key_bgr[None, None, :], axis=2) / 441.67
        sim = max(0.01, clip.chroma.similarity)
        blend = max(0.005, clip.chroma.blend)
        chroma_alpha = np.clip((diff - sim) / blend, 0.0, 1.0)
        alpha *= chroma_alpha

    if cut_alpha is not None:
        alpha *= cut_alpha

    if clip.mask.shape != "none":
        mask_arr = np.zeros((h, w), dtype=np.float32)
        if clip.mask.shape == "rect":
            cv2.rectangle(mask_arr, (int(w * 0.15), int(h * 0.15)), (int(w * 0.85), int(h * 0.85)), 1.0, -1)
        elif clip.mask.shape == "circle":
            cv2.circle(mask_arr, (w // 2, h // 2), int(min(w, h) * 0.38), 1.0, -1)
        elif clip.mask.shape == "linear":
            mask_arr[: h // 2, :] = 1.0
        if clip.mask.invert:
            mask_arr = 1.0 - mask_arr
        feather_px = int(max(0.0, clip.mask.feather))
        if feather_px > 0:
            k = feather_px * 2 + 1
            mask_arr = cv2.GaussianBlur(mask_arr, (k, k), 0)
        alpha *= mask_arr

    op_val = interpolate_keyframes(clip.keyframes.get("opacity", []), local_time, clip.opacity)
    alpha *= max(0.0, min(1.0, op_val / 100.0))
    return img, alpha


def render_text_clip_to_rgba(clip: TimelineClip, width: int, height: int, local_t: Optional[float] = None) -> Tuple[np.ndarray, np.ndarray]:
    """Render a text clip layer (position/scale/rotation are applied later by the compositor)."""
    bgr, alpha = render_text_layer(
        clip.text_style, width, height, local_t=local_t, duration=clip.duration, flip_h=clip.flip_h, flip_v=clip.flip_v
    )
    return bgr, alpha * (clip.opacity / 100.0)


def blend_layers(base_bgr: np.ndarray, top_bgr: np.ndarray, alpha: np.ndarray, mode: str = "normal") -> np.ndarray:
    """Composite `top` over `base`, touching only the bounding box where `alpha` is non-zero.

    Stickers and text cover a small part of the canvas, so blending the whole frame in float32 for every
    layer (the old behaviour) was the main cost of preview playback and export. The result is identical, but
    `base_bgr` is modified in place and returned: callers must use the return value (the canvas is never shared).
    """
    rows = np.flatnonzero(alpha.max(axis=1) > 0.0)
    if rows.size == 0:
        return base_bgr
    cols = np.flatnonzero(alpha.max(axis=0) > 0.0)
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    a_roi = alpha[y0:y1, x0:x1]
    t_roi = top_bgr[y0:y1, x0:x1]
    if mode in ("normal", "") and float(a_roi.min()) >= 0.999:
        base_bgr[y0:y1, x0:x1] = t_roi  # fully opaque layer: nothing of the base shows through
        return base_bgr
    b = base_bgr[y0:y1, x0:x1].astype(np.float32) / 255.0
    t = t_roi.astype(np.float32) / 255.0
    a = np.clip(a_roi[..., None], 0.0, 1.0)
    if mode == "multiply":
        comp = b * t
    elif mode == "screen":
        comp = 1.0 - (1.0 - b) * (1.0 - t)
    elif mode == "overlay":
        comp = np.where(b < 0.5, 2.0 * b * t, 1.0 - 2.0 * (1.0 - b) * (1.0 - t))
    elif mode == "darken":
        comp = np.minimum(b, t)
    elif mode == "lighten":
        comp = np.maximum(b, t)
    else:
        comp = t
    out = b * (1.0 - a) + comp * a
    base_bgr[y0:y1, x0:x1] = np.clip(out * 255.0, 0, 255).astype(np.uint8)
    return base_bgr


# ----------------------------------------------------------------------------- clip animations (CapCut-style In / Out / Loop)
ANIM_IN_KEYS = ("none", "fade", "zoom_in", "zoom_out", "slide_left", "slide_right", "slide_up", "slide_down", "spin", "pop", "bounce")
ANIM_OUT_KEYS = ("none", "fade", "zoom_in", "zoom_out", "slide_left", "slide_right", "slide_up", "slide_down", "spin", "pop", "bounce")
ANIM_LOOP_KEYS = ("none", "pulse", "swing", "float", "spin", "shake", "blink")


def _ease_out_back(t: float) -> float:
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def _ease_out_bounce(t: float) -> float:
    n1, d1 = 7.5625, 2.75
    if t < 1 / d1:
        return n1 * t * t
    if t < 2 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def clip_animation_state(clip: "TimelineClip", local_t: float, w: int, h: int) -> Tuple[float, float, float, float, float]:
    """(dx_px, dy_px, scale_multiplier, rotation_deg, alpha_multiplier) produced by the clip's In / Out / Loop animations."""
    a_in, a_out, a_loop = clip.anim_in, clip.anim_out, clip.anim_loop
    if a_in == "none" and a_out == "none" and a_loop == "none":
        return 0.0, 0.0, 1.0, 0.0, 1.0
    dur = max(0.05, clip.duration)
    d = max(0.05, min(float(clip.anim_duration), dur / 2.0))
    dx = dy = rot = 0.0
    sc = al = 1.0
    if a_in != "none" and local_t < d:
        t = max(0.0, min(1.0, local_t / d))
        q = 1.0 - (1.0 - t) ** 3  # ease-out
        inv = 1.0 - q
        if a_in == "fade":
            al *= q
        elif a_in == "zoom_in":
            sc *= 0.3 + 0.7 * q
            al *= q
        elif a_in == "zoom_out":
            sc *= 1.6 - 0.6 * q
            al *= q
        elif a_in == "slide_left":
            dx += inv * w * 0.45
            al *= min(1.0, q * 2.5)
        elif a_in == "slide_right":
            dx -= inv * w * 0.45
            al *= min(1.0, q * 2.5)
        elif a_in == "slide_up":
            dy += inv * h * 0.45
            al *= min(1.0, q * 2.5)
        elif a_in == "slide_down":
            dy -= inv * h * 0.45
            al *= min(1.0, q * 2.5)
        elif a_in == "spin":
            rot -= inv * 180.0
            sc *= 0.4 + 0.6 * q
            al *= q
        elif a_in == "pop":
            sc *= max(0.01, _ease_out_back(t))
            al *= min(1.0, t * 3.0)
        elif a_in == "bounce":
            dy -= (1.0 - _ease_out_bounce(t)) * h * 0.35
            al *= min(1.0, t * 4.0)
    rem = dur - local_t
    if a_out != "none" and rem < d:
        t = max(0.0, min(1.0, 1.0 - rem / d))
        e = t * t  # ease-in
        if a_out == "fade":
            al *= 1.0 - e
        elif a_out == "zoom_in":
            sc *= 1.0 + 0.6 * e
            al *= 1.0 - e
        elif a_out == "zoom_out":
            sc *= 1.0 - 0.7 * e
            al *= 1.0 - e
        elif a_out == "slide_left":
            dx -= e * w * 0.45
            al *= 1.0 - max(0.0, e - 0.6) * 2.5
        elif a_out == "slide_right":
            dx += e * w * 0.45
            al *= 1.0 - max(0.0, e - 0.6) * 2.5
        elif a_out == "slide_up":
            dy -= e * h * 0.45
            al *= 1.0 - max(0.0, e - 0.6) * 2.5
        elif a_out == "slide_down":
            dy += e * h * 0.45
            al *= 1.0 - max(0.0, e - 0.6) * 2.5
        elif a_out == "spin":
            rot += e * 180.0
            sc *= 1.0 - 0.6 * e
            al *= 1.0 - e
        elif a_out == "pop":
            sc *= max(0.01, 1.0 - e)
            al *= 1.0 - max(0.0, e - 0.5) * 2.0
        elif a_out == "bounce":
            dy += e * h * 0.25
            al *= 1.0 - e
    if a_loop != "none":
        if a_loop == "pulse":
            sc *= 1.0 + 0.07 * math.sin(local_t * 2.0 * math.pi / 0.8)
        elif a_loop == "swing":
            rot += 8.0 * math.sin(local_t * 2.0 * math.pi / 1.2)
        elif a_loop == "float":
            dy += h * 0.02 * math.sin(local_t * 2.0 * math.pi / 1.6)
        elif a_loop == "spin":
            rot += 360.0 * (local_t / 2.0)
        elif a_loop == "shake":
            dx += w * 0.008 * math.sin(local_t * 2.0 * math.pi * 9.0)
        elif a_loop == "blink":
            al *= 0.3 + 0.7 * abs(math.cos(local_t * math.pi / 0.6))
    return dx, dy, max(0.01, sc), rot, max(0.0, min(1.0, al))


def _srt_time_to_seconds(t_str: str) -> float:
    t_str = t_str.strip().replace(",", ".")
    parts = t_str.split(":")
    if len(parts) != 3:
        return 0.0
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])


def _seconds_to_srt_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    hrs = int(sec // 3600)
    mins = int((sec % 3600) // 60)
    secs = int(sec % 60)
    millis = int(round((sec - int(sec)) * 1000))
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def parse_srt_content(srt_text: str) -> List[TimelineClip]:
    clips: List[TimelineClip] = []
    blocks = re.split(r"\n\s*\n", (srt_text or "").strip())
    for block in blocks:
        lines = [ln.strip() for ln in block.strip().splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        time_line_idx = 0
        for idx, ln in enumerate(lines):
            if "-->" in ln:
                time_line_idx = idx
                break
        if "-->" not in lines[time_line_idx]:
            continue
        start_s, end_s = lines[time_line_idx].split("-->", 1)
        t_start = _srt_time_to_seconds(start_s)
        t_end = max(t_start + 0.5, _srt_time_to_seconds(end_s))
        text_body = "\n".join(lines[time_line_idx + 1 :])
        clips.append(
            TimelineClip(
                name=text_body[:24] or "Subtitle",
                clip_type="text",
                timeline_start=t_start,
                duration=round(t_end - t_start, 3),
                text_style=TextStyleSettings(text=text_body, font_size=44),
            )
        )
    return clips


def export_clips_to_srt(clips: List[TimelineClip]) -> str:
    text_clips = sorted([c for c in clips if c.clip_type == "text"], key=lambda c: c.timeline_start)
    out_blocks: List[str] = []
    for i, c in enumerate(text_clips, start=1):
        t0 = _seconds_to_srt_time(c.timeline_start)
        t1 = _seconds_to_srt_time(c.timeline_end)
        out_blocks.append(f"{i}\n{t0} --> {t1}\n{c.text_style.text.strip()}")
    return "\n\n".join(out_blocks) + ("\n" if out_blocks else "")


def export_clips_to_vtt(clips: List[TimelineClip]) -> str:
    """Export timeline text clips as WebVTT subtitles."""
    text_clips = sorted((c for c in clips if c.clip_type == "text"), key=lambda c: c.timeline_start)
    def stamp(sec: float) -> str:
        ms = int(round(max(0.0, sec) * 1000.0))
        hh, rem = divmod(ms, 3_600_000)
        mm, rem = divmod(rem, 60_000)
        ss, msec = divmod(rem, 1000)
        return f"{hh:02d}:{mm:02d}:{ss:02d}.{msec:03d}"
    blocks = ["WEBVTT"]
    for c in text_clips:
        blocks.append(f"{stamp(c.timeline_start)} --> {stamp(c.timeline_end)}\n{c.text_style.text.strip()}")
    return "\n\n".join(blocks) + "\n"


SUBTITLE_STYLE_PRESETS = {
    "classic": {"font_size": 44, "bold": False, "stroke_width": 3, "bg_enabled": False, "align": "center"},
    "bold_box": {"font_size": 48, "bold": True, "stroke_width": 2, "bg_enabled": True, "bg_opacity": 78, "align": "center"},
    "social": {"font_size": 58, "bold": True, "stroke_width": 4, "glow_enabled": True, "align": "center"},
    "minimal": {"font_size": 38, "bold": False, "stroke_width": 0, "align": "center"},
}


def generate_synthetic_or_real_waveform(source_path: str, num_samples: int = 80) -> List[float]:
    if source_path and os.path.exists(source_path) and shutil.which("ffmpeg"):
        try:
            cmd = ["ffmpeg", "-nostdin", "-v", "error", "-i", source_path, "-ac", "1", "-ar", "1000", "-f", "s16le", "-"]
            proc = subprocess.run(cmd, capture_output=True, timeout=4)
            if proc.returncode == 0 and len(proc.stdout) >= 4:
                pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
                chunks = np.array_split(np.abs(pcm), num_samples)
                peaks = [float(np.mean(ch)) / 32768.0 if len(ch) else 0.1 for ch in chunks]
                max_p = max(peaks) if peaks else 1.0
                if max_p > 1e-4:
                    return [round(max(0.08, min(1.0, p / max_p)), 3) for p in peaks]
        except Exception:
            pass
    seed = sum(ord(c) for c in (source_path or "clip"))
    return [round(0.2 + 0.7 * abs(math.sin((i + seed) * 0.45) * math.cos(i * 0.19)), 3) for i in range(num_samples)]


def build_ffmpeg_clip_filters(clip: TimelineClip) -> Tuple[List[str], List[str]]:
    v_filters: List[str] = []
    a_filters: List[str] = []
    if clip.flip_h:
        v_filters.append("hflip")
    if clip.flip_v:
        v_filters.append("vflip")
    cg = clip.color
    if abs(cg.brightness) > 0.1 or abs(cg.contrast) > 0.1 or abs(cg.saturation) > 0.1:
        b = round(cg.brightness / 100.0, 3)
        c = round(1.0 + cg.contrast / 100.0, 3)
        s = round(1.0 + cg.saturation / 100.0, 3)
        v_filters.append(f"eq=brightness={b}:contrast={c}:saturation={s}")
    if cg.lut_path and os.path.exists(cg.lut_path):
        safe_lut = cg.lut_path.replace("\\", "/")
        v_filters.append(f"lut3d=file='{safe_lut}'")
    if clip.chroma.enabled:
        col = clip.chroma.key_color_hex.lstrip("#")
        v_filters.append(f"chromakey=0x{col}:{clip.chroma.similarity:.2f}:{clip.chroma.blend:.2f}")
    if clip.reverse:
        v_filters.append("reverse")
        a_filters.append("areverse")
    if abs(clip.speed - 1.0) > 0.01:
        pts_mult = round(1.0 / max(0.1, min(100.0, clip.speed)), 4)
        v_filters.append(f"setpts={pts_mult}*PTS")
        spd = max(0.5, min(2.0, clip.speed))
        a_filters.append(f"atempo={spd:.3f}")
    if abs(clip.volume_db) > 0.1:
        a_filters.append(f"volume={clip.volume_db:.1f}dB")
    if clip.fade_in > 0.05:
        a_filters.append(f"afade=t=in:st=0:d={clip.fade_in:.2f}")
    if clip.fade_out > 0.05 and clip.duration > clip.fade_out:
        st = max(0.0, clip.duration - clip.fade_out)
        a_filters.append(f"afade=t=out:st={st:.2f}:d={clip.fade_out:.2f}")
    if abs(clip.pitch_semitones) > 0.1:
        factor = round(2.0 ** (clip.pitch_semitones / 12.0), 4)
        a_filters.append(f"asetrate=44100*{factor},aresample=44100")
    if clip.eq_preset in EQUALIZER_PRESETS and clip.eq_preset != "flat":
        for freq, gain in EQUALIZER_PRESETS[clip.eq_preset]:
            if gain != 0:
                a_filters.append(f"equalizer=f={freq}:width_type=o:width=2:g={gain}")
    return v_filters, a_filters


class _UndoGroup:
    def __init__(self, project: "VideoStudioProject"):
        self.project = project

    def __enter__(self) -> "VideoStudioProject":
        self.project.push_undo_snapshot()
        self.project._group_depth = getattr(self.project, "_group_depth", 0) + 1
        return self.project

    def __exit__(self, *exc: Any) -> None:
        self.project._group_depth = max(0, getattr(self.project, "_group_depth", 1) - 1)



class _VideoReaderPool:
    """Keeps a few cv2.VideoCapture objects open per thread and reads sequentially when frames are requested in order.
    Opening + seeking a capture for every frame (the old behaviour) made preview and export very slow."""

    SEQ_WINDOW = 8

    def __init__(self, max_open: int = 6):
        self.max_open = max_open
        self.caps: "OrderedDict[str, List[Any]]" = OrderedDict()

    def read(self, path: str, src_t: float) -> Optional[np.ndarray]:
        ent = self.caps.get(path)
        if ent is None:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                return None
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            if fps < 1 or fps > 480:
                fps = 30.0
            ent = [cap, -10**9, fps, None]
            self.caps[path] = ent
            while len(self.caps) > self.max_open:
                _, old = self.caps.popitem(last=False)
                old[0].release()
        else:
            self.caps.move_to_end(path)
        cap, last, fps, last_frame = ent
        idx = max(0, int(round(src_t * fps)))
        if idx == last and last_frame is not None:
            return last_frame
        frame = None
        ok = False
        if 0 < idx - last <= self.SEQ_WINDOW:
            for _ in range(idx - last):
                ok, frame = cap.read()
                if not ok:
                    break
        else:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
        if not ok or frame is None:
            ent[1], ent[3] = -10**9, None
            return None
        ent[1], ent[3] = idx, frame
        return frame

    def close(self) -> None:
        for ent in self.caps.values():
            try:
                ent[0].release()
            except Exception:
                pass
        self.caps.clear()


_tls = threading.local()


def _reader_pool() -> _VideoReaderPool:
    pool = getattr(_tls, "pool", None)
    if pool is None:
        pool = _tls.pool = _VideoReaderPool()
    return pool


def close_reader_pool() -> None:
    """Release the current thread's open video files (call when an export/preview worker finishes)."""
    pool = getattr(_tls, "pool", None)
    if pool is not None:
        pool.close()


_IMG_CACHE: "OrderedDict[Tuple[str, float], np.ndarray]" = OrderedDict()
_IMG_CACHE_LOCK = threading.Lock()


def _load_image_cached(path: str, flags: int = cv2.IMREAD_COLOR) -> Optional[np.ndarray]:
    try:
        key = (path + f"|{flags}", os.path.getmtime(path))
    except OSError:
        return None
    with _IMG_CACHE_LOCK:
        if key in _IMG_CACHE:
            _IMG_CACHE.move_to_end(key)
            return _IMG_CACHE[key]
    try:
        data = np.fromfile(path, dtype=np.uint8)  # imread() fails on non-ASCII Windows paths; fromfile+imdecode does not
        img = cv2.imdecode(data, flags)
    except Exception:
        img = None
    if img is not None:
        with _IMG_CACHE_LOCK:
            _IMG_CACHE[key] = img
            while len(_IMG_CACHE) > 24:
                _IMG_CACHE.popitem(last=False)
    return img


def probe_media_duration(path: str, ffmpeg: Optional[str] = None, default: float = 5.0) -> float:
    """Real duration in seconds of a video/audio file (images and unknown files -> `default`)."""
    try:
        ext = Path(path).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
            return default
        if ext == ".gif":
            data = load_sticker_frames(path)
            return max(0.5, sum(data[1])) if data else default
        if ext == ".wav":
            import wave

            with wave.open(path, "rb") as wf:
                if wf.getframerate() > 0:
                    return max(0.1, wf.getnframes() / float(wf.getframerate()))
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            n = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
            cap.release()
            if fps > 1 and n > 0:
                return max(0.1, n / fps)
        if ffmpeg:
            import subprocess as _sp

            flags = 0x08000000 if os.name == "nt" else 0
            res = _sp.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True, timeout=30, creationflags=flags)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", (res.stderr + res.stdout).decode("utf-8", errors="replace"))
            if m:
                return max(0.1, int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)))
    except Exception:
        pass
    return default


STICKER_BASE_FRACTION = 0.38   # a 100% sticker spans this fraction of the canvas's shorter side
_STICKER_CACHE: "OrderedDict[Tuple[str, float], Tuple[List[np.ndarray], List[float]]]" = OrderedDict()
_STICKER_LOCK = threading.Lock()
MAX_STICKER_FRAMES = 240
MAX_STICKER_SIDE = 640


def load_sticker_frames(path: str) -> Optional[Tuple[List[np.ndarray], List[float]]]:
    """Decode PNG / WebP / GIF (animated or not) to BGRA uint8 frames + per-frame durations (seconds). Cached."""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    with _STICKER_LOCK:
        if key in _STICKER_CACHE:
            _STICKER_CACHE.move_to_end(key)
            return _STICKER_CACHE[key]
    frames: List[np.ndarray] = []
    durs: List[float] = []
    try:
        from PIL import ImageSequence

        with Image.open(path) as im:
            n_total = getattr(im, "n_frames", 1)
            stride = max(1, int(math.ceil(n_total / float(MAX_STICKER_FRAMES))))
            for i, fr in enumerate(ImageSequence.Iterator(im)):
                if i % stride:
                    continue
                rgba = fr.convert("RGBA")
                if max(rgba.size) > MAX_STICKER_SIDE:
                    k = MAX_STICKER_SIDE / float(max(rgba.size))
                    rgba = rgba.resize((max(1, int(rgba.width * k)), max(1, int(rgba.height * k))), Image.LANCZOS)
                arr = np.asarray(rgba)
                frames.append(cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA))
                durs.append(max(0.02, float(fr.info.get("duration", 100)) / 1000.0 * stride))
    except Exception:
        return None
    if not frames:
        return None
    res = (frames, durs)
    with _STICKER_LOCK:
        _STICKER_CACHE[key] = res
        while len(_STICKER_CACHE) > 12:
            _STICKER_CACHE.popitem(last=False)
    return res


def sticker_frame_at(frames: List[np.ndarray], durs: List[float], t: float) -> np.ndarray:
    """Frame shown at time t (looping)."""
    if len(frames) == 1:
        return frames[0]
    total = sum(durs)
    t = t % total if total > 0 else 0.0
    acc = 0.0
    for fr, d in zip(frames, durs):
        acc += d
        if t < acc:
            return fr
    return frames[-1]


def sticker_rect(frame_shape: Tuple[int, ...], canvas_w: int, canvas_h: int) -> Tuple[int, int, int, int]:
    """(x0, y0, x1, y1) of a sticker centered on the canvas at 100% scale."""
    fh, fw = frame_shape[:2]
    k = (min(canvas_w, canvas_h) * STICKER_BASE_FRACTION) / float(max(fw, fh))
    sw, sh = max(2, int(fw * k)), max(2, int(fh * k))
    x0, y0 = (canvas_w - sw) // 2, (canvas_h - sh) // 2
    return x0, y0, x0 + sw, y0 + sh


def render_sticker_layer(clip: "TimelineClip", local_t: float, w: int, h: int) -> Tuple[np.ndarray, np.ndarray]:
    """Canvas-sized (bgr, alpha) with the sticker centered; falls back to an empty layer if unreadable."""
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.float32)
    data = load_sticker_frames(clip.source_path) if clip.source_path else None
    if data is None:
        return bgr, alpha
    frame = sticker_frame_at(data[0], data[1], local_t)
    x0, y0, x1, y1 = sticker_rect(frame.shape, w, h)
    small = cv2.resize(frame, (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA if frame.shape[1] > (x1 - x0) else cv2.INTER_LINEAR)
    bgr[y0:y1, x0:x1] = small[:, :, :3]
    alpha[y0:y1, x0:x1] = small[:, :, 3].astype(np.float32) / 255.0
    img, fx_alpha = process_frame_effects(bgr, clip, local_time=local_t)
    return img, fx_alpha * alpha


def generate_thumbnail(path: str, t: float, height: int = 48) -> Optional[np.ndarray]:
    """Small BGR thumbnail of an image or of a video frame at source time `t` (None if unreadable). Thread-safe."""
    if not path or not os.path.exists(path):
        return None
    ext = Path(path).suffix.lower()
    if ext in (".gif", ".webp", ".png"):
        data = load_sticker_frames(path)  # keeps transparency; shown over a checker-like gray
        if data is None:
            return None
        fr = sticker_frame_at(data[0], data[1], t)
        bg = np.full((fr.shape[0], fr.shape[1], 3), 60, dtype=np.float32)
        a = fr[:, :, 3:4].astype(np.float32) / 255.0
        img = (fr[:, :, :3].astype(np.float32) * a + bg * (1 - a)).astype(np.uint8)
    elif ext in (".jpg", ".jpeg", ".bmp"):
        img = _load_image_cached(path)
    else:
        img = _reader_pool().read(path, max(0.0, t))
    if img is None or img.size == 0:
        return None
    hh, ww = img.shape[:2]
    return cv2.resize(img, (max(8, int(ww * height / max(1, hh))), height), interpolation=cv2.INTER_AREA)


class VideoStudioProject:
    def __init__(self, name: str = "Untitled Project", aspect_ratio: str = "16:9", fps: int = 30):
        self.name = name
        self.aspect_ratio = aspect_ratio if aspect_ratio in ASPECT_RATIOS else "16:9"
        self.fps = fps
        self.playhead_sec: float = 0.0
        self.snapping_enabled: bool = True
        self.auto_ducking: bool = False
        self.ducking_amount_db: float = 12.0
        self.snap_threshold_sec: float = 0.20
        self.markers: List[TimelineMarker] = []
        self.tracks: List[TimelineTrack] = [
            TimelineTrack(name="Video 1", track_type="video"),
            TimelineTrack(name="Text 1", track_type="text"),
            TimelineTrack(name="Audio 1", track_type="audio"),
        ]
        self._undo_stack: List[str] = []
        self._redo_stack: List[str] = []
        # Runtime-only path; never serialized into project files.
        self.stabilization_cache_dir: Optional[Path] = None

    @property
    def canvas_size(self) -> Tuple[int, int]:
        return ASPECT_RATIOS.get(self.aspect_ratio, (1920, 1080))

    def total_duration(self) -> float:
        max_end = 5.0
        for trk in self.tracks:
            for c in trk.clips:
                if c.timeline_end > max_end:
                    max_end = c.timeline_end
        return round(max_end, 3)

    def undo_group(self) -> "_UndoGroup":
        """Context manager: many edits inside create a single undo step."""
        return _UndoGroup(self)

    def push_undo_snapshot(self) -> None:
        if getattr(self, "_group_depth", 0) > 0:
            return
        self._undo_stack.append(self._snapshot_string())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _snapshot_string(self) -> str:
        """Compact JSON (no indentation) for undo/redo: several times faster than the pretty file format."""
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"))

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot_string())
        prev_json = self._undo_stack.pop()
        self.load_from_json_string(prev_json, clear_history=False)
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot_string())
        next_json = self._redo_stack.pop()
        self.load_from_json_string(next_json, clear_history=False)
        return True

    def add_track(self, track_type: str = "video", name: str = "") -> TimelineTrack:
        self.push_undo_snapshot()
        count = sum(1 for t in self.tracks if t.track_type == track_type) + 1
        label = name or f"{track_type.capitalize()} {count}"
        trk = TimelineTrack(name=label, track_type=track_type)
        # Keep compositing order predictable: base video, sticker overlays, text overlays, then audio.
        # New video tracks go before sticker overlays; new sticker tracks go before text overlays.
        if track_type == "audio":
            self.tracks.append(trk)
        elif track_type == "video":
            index = next((i for i, t in enumerate(self.tracks) if t.track_type in ("sticker", "text", "audio")), len(self.tracks))
            self.tracks.insert(index, trk)
        elif track_type == "sticker":
            index = next((i for i, t in enumerate(self.tracks) if t.track_type in ("text", "audio")), len(self.tracks))
            self.tracks.insert(index, trk)
        elif track_type == "text":
            index = next((i for i, t in enumerate(self.tracks) if t.track_type == "audio"), len(self.tracks))
            self.tracks.insert(index, trk)
        else:
            index = next((i for i, t in enumerate(self.tracks) if t.track_type == "audio"), len(self.tracks))
            self.tracks.insert(index, trk)
        return trk

    def find_sticker_track(self, start: float, end: float) -> TimelineTrack:
        """An unlocked sticker track that is free in [start, end) - an existing one if possible, otherwise a new one."""
        for trk in reversed(self.tracks):
            if trk.track_type == "sticker" and not trk.locked and not any(c.timeline_start < end and c.timeline_end > start for c in trk.clips):
                return trk
        return self.add_track("sticker")

    def close_gaps(self, track_id: str) -> bool:
        """Slide the clips of a track left so there are no empty gaps (CapCut's 'track magnet')."""
        trk = self.find_track(track_id)
        if trk is None or trk.locked or not trk.clips:
            return False
        self.push_undo_snapshot()
        cursor = 0.0
        for c in sorted(trk.clips, key=lambda x: x.timeline_start):
            c.timeline_start = round(cursor, 3)
            cursor = c.timeline_end
        trk.clips.sort(key=lambda x: x.timeline_start)
        return True

    def find_clip(self, clip_id: str) -> Optional[Tuple[TimelineTrack, TimelineClip]]:
        for trk in self.tracks:
            for c in trk.clips:
                if c.id == clip_id:
                    return trk, c
        return None

    def create_ab_transition(self, outgoing_clip_id: str, incoming_clip_id: str,
                             duration: float, transition: str) -> bool:
        """Create a real same-track A/B overlap using available incoming source handles.

        The incoming clip is extended to the left by moving its source in-point earlier;
        its original timeline end is preserved. No source frames are fabricated.
        """
        left = self.find_clip(outgoing_clip_id)
        right = self.find_clip(incoming_clip_id)
        if not left or not right:
            return False
        track_a, outgoing = left
        track_b, incoming = right
        if track_a is not track_b or track_a.locked or outgoing.id == incoming.id:
            return False
        if outgoing.clip_type not in ("video", "image") or incoming.clip_type not in ("video", "image"):
            return False
        if outgoing.reverse or incoming.reverse or incoming.speed_curve != "constant":
            return False
        if abs(outgoing.timeline_end - incoming.timeline_start) > 0.08:
            return False
        speed = max(0.05, float(incoming.speed or 1.0))
        overlap = min(max(0.1, float(duration)), max(0.0, incoming.source_in / speed), max(0.0, outgoing.duration - 0.1))
        if overlap < 0.1:
            return False
        self.push_undo_snapshot()
        incoming.timeline_start = round(incoming.timeline_start - overlap, 3)
        incoming.source_in = max(0.0, round(incoming.source_in - overlap * speed, 3))
        incoming.duration = round(incoming.duration + overlap, 3)
        incoming.transition_in = str(transition or "crossfade")
        incoming.transition_duration = round(overlap, 3)
        track_a.clips.sort(key=lambda item: item.timeline_start)
        return True

    def compute_snap_time(self, candidate_time: float, exclude_clip_id: str = "") -> float:
        if not self.snapping_enabled:
            return max(0.0, round(candidate_time, 3))
        snap_points: List[float] = [0.0, self.playhead_sec]
        for m in self.markers:
            snap_points.append(m.time_sec)
        for trk in self.tracks:
            for c in trk.clips:
                if c.id == exclude_clip_id:
                    continue
                snap_points.append(c.timeline_start)
                snap_points.append(c.timeline_end)
        best = candidate_time
        best_dist = self.snap_threshold_sec
        for pt in snap_points:
            dist = abs(candidate_time - pt)
            if dist <= best_dist:
                best_dist = dist
                best = pt
        return max(0.0, round(best, 3))

    def add_clip_to_track(self, track_id: str, clip: TimelineClip) -> bool:
        for trk in self.tracks:
            if trk.id == track_id:
                if trk.locked:
                    return False
                self.push_undo_snapshot()
                if not clip.waveform_peaks and clip.clip_type in ("video", "audio"):
                    clip.waveform_peaks = generate_synthetic_or_real_waveform(clip.source_path)
                trk.clips.append(clip)
                trk.clips.sort(key=lambda x: x.timeline_start)
                return True
        return False

    def split_clip_at(self, clip_id: str, split_time: Optional[float] = None) -> Optional[Tuple[TimelineClip, TimelineClip]]:
        found = self.find_clip(clip_id)
        if not found:
            return None
        trk, clip = found
        if trk.locked:
            return None
        t = self.playhead_sec if split_time is None else split_time
        if t <= clip.timeline_start + 0.1 or t >= clip.timeline_end - 0.1:
            return None
        self.push_undo_snapshot()
        first_dur = round(t - clip.timeline_start, 3)
        second_dur = round(clip.duration - first_dur, 3)
        second_clip = copy.deepcopy(clip)
        second_clip.id = uuid.uuid4().hex[:10]
        second_clip.name = f"{clip.name} (2)"
        second_clip.timeline_start = round(t, 3)
        second_clip.duration = second_dur
        second_clip.source_in = round(clip.source_in + first_dur * clip.speed, 3)
        clip.duration = first_dur
        clip.source_out = round(clip.source_in + first_dur * clip.speed, 3)
        trk.clips.append(second_clip)
        trk.clips.sort(key=lambda x: x.timeline_start)
        return clip, second_clip

    def delete_clip(self, clip_id: str) -> bool:
        found = self.find_clip(clip_id)
        if not found:
            return False
        trk, clip = found
        if trk.locked:
            return False
        self.push_undo_snapshot()
        trk.clips.remove(clip)
        return True

    # ------------------------------------------------------------------
    # Timeline editing helpers (duplicate / trim / ripple / tracks / speed)
    # ------------------------------------------------------------------
    def find_track(self, track_id: str) -> Optional[TimelineTrack]:
        return next((t for t in self.tracks if t.id == track_id), None)

    def duplicate_clip(self, clip_id: str) -> Optional[TimelineClip]:
        found = self.find_clip(clip_id)
        if not found:
            return None
        trk, clip = found
        if trk.locked:
            return None
        self.push_undo_snapshot()
        dup = copy.deepcopy(clip)
        dup.id = uuid.uuid4().hex[:10]
        dup.name = f"{clip.name} (copy)"
        dup.timeline_start = round(clip.timeline_end, 3)
        trk.clips.append(dup)
        trk.clips.sort(key=lambda x: x.timeline_start)
        return dup

    def paste_clip(self, clip: TimelineClip, track_id: Optional[str], start: float) -> Optional[TimelineClip]:
        """Insert a deep copy of `clip` at `start` on the given track (or the first compatible unlocked track)."""
        trk = self.find_track(track_id) if track_id else None
        if trk is None or trk.locked or not track_accepts(trk.track_type, clip.clip_type):
            trk = next((t for t in self.tracks if track_accepts(t.track_type, clip.clip_type) and not t.locked and t.track_type != "video"), None) \
                or next((t for t in self.tracks if track_accepts(t.track_type, clip.clip_type) and not t.locked), None)
        if trk is None:
            return None
        self.push_undo_snapshot()
        new = copy.deepcopy(clip)
        new.id = uuid.uuid4().hex[:10]
        new.timeline_start = round(max(0.0, start), 3)
        trk.clips.append(new)
        trk.clips.sort(key=lambda x: x.timeline_start)
        return new

    def trim_clip(self, clip_id: str, new_start: Optional[float] = None, new_end: Optional[float] = None, min_duration: float = 0.1) -> bool:
        """Trim the clip's head and/or tail on the timeline; source in/out follow the clip speed."""
        found = self.find_clip(clip_id)
        if not found:
            return False
        trk, clip = found
        if trk.locked:
            return False
        end = clip.timeline_end
        start = clip.timeline_start
        if new_start is not None:
            start = max(0.0, min(new_start, end - min_duration))
        if new_end is not None:
            end = max(start + min_duration, new_end)
        d_head = start - clip.timeline_start
        if abs(d_head) < 1e-6 and abs(end - clip.timeline_end) < 1e-6:
            return False
        clip.source_in = round(max(0.0, clip.source_in + d_head * clip.speed), 3)
        clip.timeline_start = round(start, 3)
        clip.duration = round(end - start, 3)
        if clip.clip_type in ("video", "audio"):
            clip.source_out = round(clip.source_in + clip.duration * clip.speed, 3)
        trk.clips.sort(key=lambda x: x.timeline_start)
        return True

    def remove_timeline_range(self, start_sec: float, end_sec: float) -> bool:
        """Remove a time range from every unlocked track and ripple all later material.

        Used by transcript-based editing: deleting a caption sentence removes the matching
        interval across video, audio, text and overlays while preserving synchronization.
        """
        start = max(0.0, float(start_sec))
        end = max(start, float(end_sec))
        gap = end - start
        if gap < 0.05:
            return False
        if any(trk.locked and any(c.timeline_end > start for c in trk.clips) for trk in self.tracks):
            return False  # never ripple only part of a locked timeline and silently break sync
        if not any(not trk.locked and any(c.timeline_start < end and c.timeline_end > start for c in trk.clips) for trk in self.tracks):
            return False
        self.push_undo_snapshot()
        for trk in self.tracks:
            if trk.locked:
                continue
            rebuilt: List[TimelineClip] = []
            for clip in trk.clips:
                old_start, old_end = clip.timeline_start, clip.timeline_end
                if old_end <= start + 1e-6:
                    rebuilt.append(clip)
                    continue
                if old_start >= end - 1e-6:
                    clip.timeline_start = round(old_start - gap, 3)
                    rebuilt.append(clip)
                    continue
                # The clip overlaps the removed interval. Keep its left and/or right remainder.
                original = copy.deepcopy(clip)
                if clip.clip_type in ("video", "audio") and (clip.reverse or clip.speed_curve != "constant"):
                    return False  # do not misalign source-time mapping on reverse/speed-ramped clips
                left_duration = max(0.0, start - old_start)
                right_duration = max(0.0, old_end - end)
                speed = max(0.0, float(original.speed or 1.0))
                if left_duration >= 0.05:
                    clip.duration = round(left_duration, 3)
                    if clip.clip_type not in ("text", "sticker") and not clip.is_freeze_frame:
                        if clip.reverse:
                            # Reverse playback addresses frames from source_out backwards.
                            clip.source_in = original.source_in
                        else:
                            clip.source_out = min(original.source_out, original.source_in + left_duration * speed)
                    rebuilt.append(clip)
                if right_duration >= 0.05:
                    right = original
                    right.id = uuid.uuid4().hex[:10]
                    right.timeline_start = round(start, 3)
                    right.duration = round(right_duration, 3)
                    source_offset = max(0.0, end - old_start) * speed
                    if right.clip_type not in ("text", "sticker") and not right.is_freeze_frame:
                        if right.reverse:
                            right.source_out = max(right.source_in + 0.05, original.source_out - source_offset)
                        else:
                            right.source_in = min(original.source_out - 0.05, original.source_in + source_offset)
                    for prop, frames in list(right.keyframes.items()):
                        right.keyframes[prop] = [Keyframe(max(0.0, k.time_offset - max(0.0, end-old_start)), k.value, k.easing)
                                                 for k in frames if k.time_offset >= max(0.0, end-old_start)]
                    rebuilt.append(right)
            trk.clips = sorted(rebuilt, key=lambda c: c.timeline_start)
        kept_markers = []
        for marker in self.markers:
            if marker.time_sec < start:
                kept_markers.append(marker)
            elif marker.time_sec >= end:
                marker.time_sec = round(marker.time_sec-gap, 3)
                kept_markers.append(marker)
        self.markers = kept_markers
        self.playhead_sec = min(self.playhead_sec, max(0.0, self.total_duration()))
        return True

    def remove_transcript_segment(self, caption_clip_id: str) -> bool:
        """Cut the video/audio timeline interval represented by an AI transcript caption."""
        found = self.find_clip(caption_clip_id)
        if not found:
            return False
        _track, caption = found
        meta = caption.ai_metadata or {}
        source_id = meta.get("transcript_source_clip_id")
        if not source_id:
            return False
        source_found = self.find_clip(str(source_id))
        if not source_found or source_found[0].locked:
            return False
        return self.remove_timeline_range(float(meta.get("transcript_timeline_start", caption.timeline_start)),
                                          float(meta.get("transcript_timeline_end", caption.timeline_end)))

    def ripple_delete_clip(self, clip_id: str) -> bool:
        found = self.find_clip(clip_id)
        if not found:
            return False
        trk, clip = found
        if trk.locked:
            return False
        self.push_undo_snapshot()
        gap_start, gap = clip.timeline_start, clip.duration
        trk.clips.remove(clip)
        for other in trk.clips:
            if other.timeline_start >= gap_start:
                other.timeline_start = round(max(0.0, other.timeline_start - gap), 3)
        return True

    def move_clip(self, clip_id: str, new_start: float, track_id: Optional[str] = None) -> bool:
        found = self.find_clip(clip_id)
        if not found:
            return False
        trk, clip = found
        if trk.locked:
            return False
        target = self.find_track(track_id) if track_id else trk
        if target is None or target.locked:
            return False
        if target is not trk and not track_accepts(target.track_type, clip.clip_type):
            return False
        clip.timeline_start = round(max(0.0, new_start), 3)
        if target is not trk:
            trk.clips.remove(clip)
            target.clips.append(clip)
            target.clips.sort(key=lambda x: x.timeline_start)
        return True

    def set_clip_speed(self, clip_id: str, speed: float) -> bool:
        """Change speed and rescale the timeline duration so the same source range is used."""
        found = self.find_clip(clip_id)
        if not found:
            return False
        trk, clip = found
        speed = max(0.1, min(100.0, float(speed)))
        if trk.locked or clip.clip_type == "text" or abs(speed - clip.speed) < 1e-6:
            return False
        self.push_undo_snapshot()
        src_len = clip.duration * max(0.1, clip.speed)
        clip.speed = speed
        clip.duration = round(max(0.1, src_len / speed), 3)
        return True

    def delete_track(self, track_id: str) -> bool:
        trk = self.find_track(track_id)
        if trk is None or trk.locked or len(self.tracks) <= 1:
            return False
        self.push_undo_snapshot()
        self.tracks.remove(trk)
        return True

    def rename_track(self, track_id: str, name: str) -> bool:
        trk = self.find_track(track_id)
        if trk is None or not name.strip():
            return False
        self.push_undo_snapshot()
        trk.name = name.strip()[:40]
        return True

    def move_track(self, track_id: str, direction: int) -> bool:
        trk = self.find_track(track_id)
        if trk is None:
            return False
        i = self.tracks.index(trk)
        j = i + (1 if direction > 0 else -1)
        if not 0 <= j < len(self.tracks):
            return False
        self.push_undo_snapshot()
        self.tracks[i], self.tracks[j] = self.tracks[j], self.tracks[i]
        return True

    def set_track_flag(self, track_id: str, flag: str, value: bool) -> bool:
        trk = self.find_track(track_id)
        if trk is None or flag not in ("muted", "hidden", "locked"):
            return False
        self.push_undo_snapshot()
        setattr(trk, flag, bool(value))
        return True

    def clear_markers(self) -> None:
        self.push_undo_snapshot()
        self.markers.clear()

    # ------------------------------------------------------------------
    # Geometry: bounds & hit-testing (used by the preview for click-to-select)
    # ------------------------------------------------------------------
    def clip_canvas_bounds(self, clip_id: str, time_sec: Optional[float] = None) -> Optional[Tuple[float, float, float, float]]:
        """Axis-aligned bounds (x0, y0, x1, y1) of the clip on the base canvas (pos/scale/rotation applied)."""
        found = self.find_clip(clip_id)
        if not found:
            return None
        _, clip = found
        base_w, base_h = self.canvas_size
        t = self.playhead_sec if time_sec is None else time_sec
        local_t = max(0.0, t - clip.timeline_start)
        if clip.clip_type == "text":
            _, alpha = render_text_layer(clip.text_style, base_w // 2, base_h // 2)
            box = alpha_bounds(alpha)
            if box is None:
                return None
            x0, y0, x1, y1 = (v * 2.0 for v in box)
        elif clip.clip_type == "sticker":
            data = load_sticker_frames(clip.source_path) if clip.source_path else None
            if data is None:
                return None
            x0, y0, x1, y1 = (float(v) for v in sticker_rect(data[0][0].shape, base_w, base_h))
        else:
            x0, y0, x1, y1 = 0.0, 0.0, float(base_w), float(base_h)
        px = interpolate_keyframes(clip.keyframes.get("pos_x", []), local_t, clip.pos_x)
        py = interpolate_keyframes(clip.keyframes.get("pos_y", []), local_t, clip.pos_y)
        sc = max(0.05, interpolate_keyframes(clip.keyframes.get("scale", []), local_t, clip.scale) / 100.0)
        rot = math.radians(-interpolate_keyframes(clip.keyframes.get("rotation", []), local_t, clip.rotation))
        cx, cy = base_w / 2.0, base_h / 2.0
        xs: List[float] = []
        ys: List[float] = []
        for (x, y) in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            dx, dy = (x - cx) * sc, (y - cy) * sc
            xs.append(cx + dx * math.cos(rot) - dy * math.sin(rot) + px)
            ys.append(cy + dx * math.sin(rot) + dy * math.cos(rot) + py)
        return min(xs), min(ys), max(xs), max(ys)

    def clip_at_point(self, x: float, y: float, time_sec: Optional[float] = None) -> Optional[str]:
        """Topmost visible (non-audio) clip under a base-canvas point at `time_sec`; later tracks are on top."""
        t = self.playhead_sec if time_sec is None else time_sec
        for trk in reversed(self.tracks):
            if trk.hidden or trk.track_type == "audio":
                continue
            for clip in reversed(trk.clips):
                if not (clip.timeline_start <= t <= clip.timeline_end):
                    continue
                b = self.clip_canvas_bounds(clip.id, t)
                if b and b[0] <= x <= b[2] and b[1] <= y <= b[3]:
                    return clip.id
        return None

    def freeze_frame_at(self, clip_id: str, freeze_time: Optional[float] = None, freeze_duration: float = 2.0) -> Optional[TimelineClip]:
        found = self.find_clip(clip_id)
        if not found:
            return None
        trk, clip = found
        if trk.locked or clip.clip_type != "video":
            return None
        t = self.playhead_sec if freeze_time is None else freeze_time
        t = max(clip.timeline_start, min(clip.timeline_end, t))
        self.push_undo_snapshot()
        frozen = copy.deepcopy(clip)
        frozen.id = uuid.uuid4().hex[:10]
        frozen.name = f"{clip.name} [Freeze]"
        frozen.is_freeze_frame = True
        frozen.timeline_start = round(t, 3)
        frozen.duration = freeze_duration
        frozen.speed = 0.0
        trk.clips.append(frozen)
        trk.clips.sort(key=lambda x: x.timeline_start)
        return frozen

    def detach_audio_from_clip(self, clip_id: str) -> Optional[TimelineClip]:
        found = self.find_clip(clip_id)
        if not found:
            return None
        trk, clip = found
        if trk.locked or clip.clip_type != "video":
            return None
        self.push_undo_snapshot()
        audio_track = next((t for t in self.tracks if t.track_type == "audio" and not t.locked), None)
        if audio_track is None:
            audio_track = TimelineTrack(name="Audio Extracted", track_type="audio")
            self.tracks.append(audio_track)
        audio_clip = TimelineClip(
            name=f"{clip.name} (Audio)",
            clip_type="audio",
            source_path=clip.source_path,
            timeline_start=clip.timeline_start,
            duration=clip.duration,
            source_in=clip.source_in,
            source_out=clip.source_out,
            volume_db=clip.volume_db,
            fade_in=clip.fade_in,
            fade_out=clip.fade_out,
            pitch_semitones=clip.pitch_semitones,
            eq_preset=clip.eq_preset,
            waveform_peaks=list(clip.waveform_peaks),
        )
        clip.muted = True
        audio_track.clips.append(audio_clip)
        audio_track.clips.sort(key=lambda x: x.timeline_start)
        return audio_clip

    def add_keyframe(self, clip_id: str, prop_name: str, time_offset: float, value: float, easing: str = "linear") -> bool:
        found = self.find_clip(clip_id)
        if not found:
            return False
        trk, clip = found
        if trk.locked:
            return False
        self.push_undo_snapshot()
        kfs = clip.keyframes.setdefault(prop_name, [])
        kfs = [k for k in kfs if abs(k.time_offset - time_offset) > 0.02]
        kfs.append(Keyframe(time_offset=round(max(0.0, time_offset), 3), value=float(value), easing=easing))
        kfs.sort(key=lambda k: k.time_offset)
        clip.keyframes[prop_name] = kfs
        return True

    def render_composite_frame(self, time_sec: float, preview_scale: float = 1.0, use_proxy: bool = False) -> np.ndarray:
        base_w, base_h = self.canvas_size
        w = max(64, int(base_w * preview_scale))
        h = max(64, int(base_h * preview_scale))
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        canvas[:] = (16, 18, 22)

        for trk in list(self.tracks):  # copies: a background preview thread must not trip over UI-thread edits
            if trk.hidden or trk.track_type == "audio":
                continue
            for clip in list(trk.clips):
                if not (clip.timeline_start <= time_sec <= clip.timeline_end):
                    continue
                local_t = time_sec - clip.timeline_start
                if clip.clip_type == "text":
                    top_bgr, alpha = render_text_clip_to_rgba(clip, w, h, local_t=local_t)
                elif clip.clip_type == "sticker":
                    top_bgr, alpha = render_sticker_layer(clip, local_t, w, h)
                else:
                    raw_bgr = self._read_clip_source_frame(clip, local_t, w, h, use_proxy=use_proxy)
                    top_bgr, alpha = process_frame_effects(raw_bgr, clip, local_time=local_t)

                px = interpolate_keyframes(clip.keyframes.get("pos_x", []), local_t, clip.pos_x) * preview_scale
                py = interpolate_keyframes(clip.keyframes.get("pos_y", []), local_t, clip.pos_y) * preview_scale
                sc = interpolate_keyframes(clip.keyframes.get("scale", []), local_t, clip.scale) / 100.0
                rot = interpolate_keyframes(clip.keyframes.get("rotation", []), local_t, clip.rotation)

                if clip.anim_in != "none" or clip.anim_out != "none" or clip.anim_loop != "none":
                    adx, ady, asc, arot, aal = clip_animation_state(clip, local_t, w, h)
                    px += adx
                    py += ady
                    sc *= asc
                    rot += arot
                    if aal < 0.999:
                        alpha = alpha * aal

                if clip.transition_in != "none" and clip.transition_duration > 0.05 and local_t < clip.transition_duration:
                    tr_prog = max(0.0, min(1.0, local_t / clip.transition_duration))
                    if clip.transition_in in ("crossfade", "fade_black"):
                        alpha = alpha * tr_prog
                    elif clip.transition_in == "wipe_left":
                        cutoff = int(w * tr_prog)
                        alpha[:, cutoff:] = 0.0
                    elif clip.transition_in == "slide":
                        px += (1.0 - tr_prog) * (-w * 0.5)
                    elif clip.transition_in == "zoom_in":
                        sc *= 0.4 + 0.6 * tr_prog
                        alpha = alpha * tr_prog
                    elif clip.transition_in == "wipe_right":
                        alpha[:, :int(w * (1.0 - tr_prog))] = 0.0
                    elif clip.transition_in == "wipe_up":
                        alpha[int(h * (1.0 - tr_prog)):, :] = 0.0
                    elif clip.transition_in == "wipe_down":
                        alpha[:int(h * tr_prog), :] = 0.0
                    elif clip.transition_in == "circle_reveal":
                        yy, xx = np.ogrid[:h, :w]
                        radius = math.hypot(w, h) * tr_prog
                        alpha[((xx-w/2)**2 + (yy-h/2)**2) > radius**2] = 0.0
                    elif clip.transition_in == "diamond":
                        yy, xx = np.ogrid[:h, :w]
                        dist = np.abs(xx-w/2)/(w/2) + np.abs(yy-h/2)/(h/2)
                        alpha[dist > 2.0 * tr_prog] = 0.0
                    elif clip.transition_in == "blinds":
                        band = max(1, int(h / 12))
                        yy = np.arange(h)
                        rows = ((yy % (band*2) >= band) | ((yy % (band*2)) > band * tr_prog))
                        alpha[rows, :] = 0.0
                    elif clip.transition_in == "checkerboard":
                        yy, xx = np.indices((h, w))
                        cell = max(8, min(w, h)//12)
                        reveal = ((xx//cell + yy//cell) % 2) == 0
                        alpha[~reveal] = 0.0
                        alpha[reveal] *= min(1.0, tr_prog * 2)
                    elif clip.transition_in == "push_left":
                        px += (1.0 - tr_prog) * w
                    elif clip.transition_in == "push_right":
                        px -= (1.0 - tr_prog) * w
                    elif clip.transition_in == "push_up":
                        py += (1.0 - tr_prog) * h
                    elif clip.transition_in == "push_down":
                        py -= (1.0 - tr_prog) * h
                    elif clip.transition_in == "rotate_in":
                        rot += (1.0 - tr_prog) * 90.0
                        sc *= 0.65 + 0.35 * tr_prog
                        alpha *= tr_prog
                    elif clip.transition_in == "blur_in":
                        k = max(1, int((1.0-tr_prog)*31)//2*2+1)
                        top_bgr = cv2.GaussianBlur(top_bgr, (k, k), 0)
                        alpha *= tr_prog
                    elif clip.transition_in == "flash":
                        alpha *= tr_prog
                        if tr_prog < 0.25:
                            top_bgr = cv2.addWeighted(top_bgr, 1-tr_prog*2, np.full_like(top_bgr, 255), tr_prog*2, 0)

                if abs(px) > 0.5 or abs(py) > 0.5 or abs(sc - 1.0) > 0.01 or abs(rot) > 0.1:
                    mat = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -rot, max(0.05, sc))
                    mat[0, 2] += px
                    mat[1, 2] += py
                    top_bgr = cv2.warpAffine(top_bgr, mat, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
                    alpha = cv2.warpAffine(alpha, mat, (w, h), borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)

                canvas = blend_layers(canvas, top_bgr, alpha, mode=clip.blend_mode)
        return canvas

    def _read_clip_source_frame(self, clip: TimelineClip, local_t: float, target_w: int, target_h: int, use_proxy: bool = False) -> np.ndarray:
        # Proxies are strictly a preview optimization. Final export always reads the
        # original source to avoid silently exporting 540p proxy footage.
        path = (clip.proxy_path if (use_proxy and clip.proxy_path and os.path.exists(clip.proxy_path))
                else clip.source_path)
        if path and os.path.exists(path):
            ext = Path(path).suffix.lower()
            if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                img = _load_image_cached(path)
                if img is not None:
                    return cv2.resize(img, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
            elif ext not in (".gif",):
                norm_pos = local_t / max(0.1, clip.duration)
                eff_speed = evaluate_speed_curve(clip.speed_curve, norm_pos, clip.speed)
                src_t = clip.source_in if clip.is_freeze_frame else (clip.source_in + local_t * eff_speed)
                if clip.reverse:
                    src_t = max(0.0, clip.source_out - local_t * eff_speed)
                frame = _reader_pool().read(path, src_t)
                if frame is not None:
                    if clip.stabilize:
                        try:
                            from video_studio_stabilization import apply_stabilization_frame
                            frame = apply_stabilization_frame(frame, clip.source_path, src_t, self.stabilization_cache_dir)
                        except Exception:
                            # Stabilization is an optional enhancement; a missing or
                            # invalid cache must never prevent ordinary editing/export.
                            pass
                    reframe = (clip.ai_metadata or {}).get("auto_reframe")
                    if isinstance(reframe, dict) and reframe.get("enabled") and reframe.get("samples"):
                        samples = reframe.get("samples", [])
                        centers = [(float(row[0]), float(row[1]), float(row[2])) for row in samples if len(row) >= 3]
                        if centers:
                            centers.sort(key=lambda row: row[0])
                            if src_t <= centers[0][0]:
                                cx, cy = centers[0][1], centers[0][2]
                            elif src_t >= centers[-1][0]:
                                cx, cy = centers[-1][1], centers[-1][2]
                            else:
                                cx, cy = 0.5, 0.5
                                for a, b in zip(centers[:-1], centers[1:]):
                                    if a[0] <= src_t <= b[0]:
                                        q = (src_t-a[0]) / max(1e-6, b[0]-a[0])
                                        cx, cy = a[1] + (b[1]-a[1])*q, a[2] + (b[2]-a[2])*q
                                        break
                            fh, fw = frame.shape[:2]
                            target_ratio = target_w / max(1, target_h)
                            src_ratio = fw / max(1, fh)
                            if src_ratio > target_ratio:
                                crop_w = max(2, int(fh * target_ratio))
                                x0 = int(max(0, min(fw-crop_w, cx*fw-crop_w/2)))
                                frame = frame[:, x0:x0+crop_w]
                            else:
                                crop_h = max(2, int(fw / target_ratio))
                                y0 = int(max(0, min(fh-crop_h, cy*fh-crop_h/2)))
                                frame = frame[y0:y0+crop_h, :]
                    return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_LINEAR)

        frame = np.zeros((target_h, target_w, 3), dtype=np.uint8)
        yy = np.linspace(35, 145, target_h, dtype=np.uint8)[:, None]
        xx = np.linspace(40, 180, target_w, dtype=np.uint8)[None, :]
        frame[..., 0] = yy
        frame[..., 1] = np.clip((yy // 2 + xx // 3), 0, 255)
        frame[..., 2] = xx
        cv2.putText(
            frame,
            f"{clip.name} ({local_t:.2f}s)",
            (int(target_w * 0.08), int(target_h * 0.5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            max(0.6, target_h / 650.0),
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        return frame

    def generate_proxy_for_clip(
        self, clip_id: str, output_dir: Path, ffmpeg_path: Optional[str] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Optional[Path]:
        found = self.find_clip(clip_id)
        if not found:
            return None
        _, clip = found
        if not clip.source_path or not os.path.exists(clip.source_path):
            return None
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            source = Path(clip.source_path).resolve()
            source_stat = source.stat()
            source_fingerprint = hashlib.sha256(
                f"{source}|{source_stat.st_size}|{source_stat.st_mtime_ns}".encode("utf-8", errors="surrogatepass")
            ).hexdigest()[:12]
        except OSError:
            source_fingerprint = "unknown"
        proxy_file = output_dir / f"proxy_{clip.id}_{source_fingerprint}.mp4"
        if proxy_file.is_file() and proxy_file.stat().st_size > 1024:
            clip.proxy_path = str(proxy_file)
            self.last_proxy_error = ""
            return proxy_file
        ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg:
            return None
        # Video-only proxy: preview audio is mixed separately from the original
        # source. Never substitute a proxy in the final export.
        temp_file = output_dir / f"proxy_{clip.id}_{source_fingerprint}_{uuid.uuid4().hex[:8]}.partial.mp4"
        cmd = [
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-i", clip.source_path,
            "-vf", "scale=w='min(960,iw)':h='min(540,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-movflags", "+faststart", str(temp_file),
        ]
        flags = 0x08000000 if os.name == "nt" else 0
        try:
            # A temporary file captures diagnostics without a PIPE that could fill
            # while the worker polls the child process.
            with tempfile.TemporaryFile() as error_log:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=error_log, creationflags=flags)
                while proc.poll() is None:
                    if cancel_check and cancel_check():
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        return None
                    try:
                        proc.wait(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        continue
                error_log.seek(0)
                stderr = error_log.read()
            if proc.returncode != 0 or not temp_file.exists() or temp_file.stat().st_size < 1024:
                self.last_proxy_error = stderr.decode("utf-8", errors="replace")[-1200:] or f"FFmpeg exited with code {proc.returncode}"
                return None
            os.replace(temp_file, proxy_file)
            clip.proxy_path = str(proxy_file)
            if progress_callback:
                progress_callback(100)
            self.last_proxy_error = ""
            return proxy_file
        except Exception as exc:
            self.last_proxy_error = f"{type(exc).__name__}: {exc}"
            return None
        finally:
            try:
                temp_file.unlink(missing_ok=True)
            except OSError:
                pass

    def clone_for_export(self) -> "VideoStudioProject":
        """Independent copy so the UI can keep editing while a background export renders."""
        clone = VideoStudioProject(name=self.name, aspect_ratio=self.aspect_ratio, fps=self.fps)
        clone.load_from_json_string(self.to_json_string(), clear_history=True)
        clone.stabilization_cache_dir = self.stabilization_cache_dir
        return clone

    last_export_info: Dict[str, Any] = {}

    def export_project(
        self,
        output_path: str,
        resolution_label: str = "1080p (Full HD)",
        fps: int = 30,
        progress_callback: Optional[Callable[[int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        quality: str = "balanced",
        use_gpu: bool = False,
        ffmpeg_path: Optional[str] = None,
    ) -> bool:
        """Render the timeline. With FFmpeg: one pass H.264 + mixed AAC audio. Without: silent MP4 via OpenCV.
        Details of what happened are left in `self.last_export_info` (audio: mixed | none | skipped_no_ffmpeg)."""
        self.last_export_info = {"audio": "none", "encoder": "", "error": ""}
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        scale = RESOLUTION_PRESETS.get(resolution_label, 1.0)
        dur = max(0.5, self.total_duration())
        total_frames = max(1, int(dur * fps))
        ext = out_file.suffix.lower()
        try:
            if ext in (".wav", ".mp3"):
                return self._export_audio_only(out_file, dur, progress_callback, cancel_check, ffmpeg_path)
            if ext == ".gif":
                return self._export_gif(out_file, fps, total_frames, progress_callback, cancel_check)
            base_w, base_h = self.canvas_size
            w = max(128, int(base_w * scale) // 2 * 2)
            h = max(128, int(base_h * scale) // 2 * 2)
            if ffmpeg_path:
                return self._export_with_ffmpeg(out_file, ffmpeg_path, w, h, scale, fps, dur, total_frames, quality, use_gpu, progress_callback, cancel_check)
            return self._export_cv2_silent(out_file, w, h, scale, fps, total_frames, progress_callback, cancel_check)
        finally:
            close_reader_pool()

    # ---- helpers ----------------------------------------------------------------
    def _frame_for_export(self, idx: int, fps: int, scale: float, w: int, h: int) -> np.ndarray:
        frame = self.render_composite_frame(idx / float(fps), preview_scale=scale)
        if frame.shape[1] != w or frame.shape[0] != h:
            frame = cv2.resize(frame, (w, h))
        return np.ascontiguousarray(frame)

    def _export_gif(self, out_file: Path, fps: int, total_frames: int, progress_callback: Optional[Callable[[int], None]], cancel_check: Optional[Callable[[], bool]]) -> bool:
        frames_rgb: List[Image.Image] = []
        step = max(1, total_frames // 30)
        for idx in range(0, total_frames, step):
            if cancel_check and cancel_check():
                return False
            bgr = self.render_composite_frame(idx / float(fps), preview_scale=0.35)
            frames_rgb.append(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)))
            if progress_callback:
                progress_callback(int((idx + 1) * 100 / total_frames))
        if frames_rgb:
            frames_rgb[0].save(str(out_file), save_all=True, append_images=frames_rgb[1:], duration=int(1000 / max(1, fps // step)), loop=0)
        if progress_callback:
            progress_callback(100)
        return out_file.exists()

    def _export_cv2_silent(self, out_file: Path, w: int, h: int, scale: float, fps: int, total_frames: int, progress_callback: Optional[Callable[[int], None]], cancel_check: Optional[Callable[[], bool]]) -> bool:
        writer = cv2.VideoWriter(str(out_file), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (w, h))
        if not writer.isOpened():
            self.last_export_info["error"] = "cannot_open_writer"
            return False
        has_sound = bool(self._audible_sources())
        for idx in range(total_frames):
            if cancel_check and cancel_check():
                writer.release()
                out_file.unlink(missing_ok=True)
                return False
            writer.write(self._frame_for_export(idx, fps, scale, w, h))
            if progress_callback:
                progress_callback(int((idx + 1) * 100 / total_frames))
        writer.release()
        self.last_export_info.update(audio="skipped_no_ffmpeg" if has_sound else "none", encoder="mp4v")
        return out_file.exists() and out_file.stat().st_size > 0

    def _audible_sources(self) -> List[Any]:
        from video_studio_ffmpeg import audible_clips

        return [c for c in audible_clips(self) if os.path.exists(c.source_path)]

    def _export_with_ffmpeg(self, out_file: Path, ffmpeg: str, w: int, h: int, scale: float, fps: int, dur: float, total_frames: int, quality: str, use_gpu: bool, progress_callback: Optional[Callable[[int], None]], cancel_check: Optional[Callable[[], bool]]) -> bool:
        import tempfile

        from video_studio_ffmpeg import build_audio_mix, detect_nvenc, video_encoder_args

        mix = build_audio_mix(self, ffmpeg, dur, first_input_index=1)
        nvenc = detect_nvenc(ffmpeg) if use_gpu else False
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
        if mix:
            cmd += mix["inputs"] + ["-filter_complex", mix["filter"], "-map", "0:v", "-map", mix["label"],
                                    "-c:a", "aac", "-b:a", "192k", "-ar", "44100"]
        else:
            cmd += ["-map", "0:v", "-an"]
        cmd += video_encoder_args(quality, use_gpu, nvenc)
        if out_file.suffix.lower() in (".mp4", ".mov"):
            cmd += ["-movflags", "+faststart"]
        cmd += ["-t", f"{dur:.3f}", str(out_file)]
        err_log = tempfile.TemporaryFile()
        flags = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=err_log, creationflags=flags)
        cancelled = False
        broken = False
        try:
            for idx in range(total_frames):
                if cancel_check and cancel_check():
                    cancelled = True
                    break
                try:
                    proc.stdin.write(self._frame_for_export(idx, fps, scale, w, h).tobytes())
                except (BrokenPipeError, OSError):
                    broken = True
                    break
                if progress_callback:
                    progress_callback(min(99, int((idx + 1) * 100 / total_frames)))
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass
            if cancelled:
                proc.kill()
            rc = proc.wait()
        if cancelled:
            out_file.unlink(missing_ok=True)
            err_log.close()
            return False
        if broken or rc != 0:
            err_log.seek(0)
            self.last_export_info["error"] = err_log.read().decode("utf-8", errors="replace")[-1500:] or f"ffmpeg exit {rc}"
            err_log.close()
            out_file.unlink(missing_ok=True)
            return False
        err_log.close()
        self.last_export_info.update(audio="mixed" if mix else "none", encoder="h264_nvenc" if (use_gpu and nvenc) else "libx264")
        if progress_callback:
            progress_callback(100)
        return out_file.exists() and out_file.stat().st_size > 0

    def _export_audio_only(
        self,
        out_file: Path,
        duration_sec: float,
        progress_callback: Optional[Callable[[int], None]],
        cancel_check: Optional[Callable[[], bool]],
        ffmpeg_path: Optional[str] = None,
    ) -> bool:
        """Mix all audible clips into WAV/MP3. Requires FFmpeg (we no longer write a silent file and call it success)."""
        from video_studio_ffmpeg import build_audio_mix

        if not ffmpeg_path:
            self.last_export_info["error"] = "ffmpeg_required"
            return False
        mix = build_audio_mix(self, ffmpeg_path, duration_sec, first_input_index=0)
        if cancel_check and cancel_check():
            return False
        if mix is None:
            self.last_export_info["error"] = "no_audio"
            return False
        codec = ["-c:a", "libmp3lame", "-b:a", "192k"] if out_file.suffix.lower() == ".mp3" else ["-c:a", "pcm_s16le"]
        cmd = [ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error", "-nostdin", *mix["inputs"], "-filter_complex", mix["filter"],
               "-map", mix["label"], *codec, "-t", f"{duration_sec:.3f}", str(out_file)]
        flags = 0x08000000 if os.name == "nt" else 0
        res = subprocess.run(cmd, capture_output=True, creationflags=flags)
        if res.returncode != 0:
            self.last_export_info["error"] = res.stderr.decode("utf-8", errors="replace")[-1500:]
            out_file.unlink(missing_ok=True)
            return False
        self.last_export_info["audio"] = "mixed"
        if progress_callback:
            progress_callback(100)
        return out_file.exists()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "aspect_ratio": self.aspect_ratio,
            "fps": self.fps,
            "playhead_sec": self.playhead_sec,
            "snapping_enabled": self.snapping_enabled,
            "auto_ducking": self.auto_ducking,
            "ducking_amount_db": self.ducking_amount_db,
            "markers": [asdict(m) for m in self.markers],
            "tracks": [asdict(t) for t in self.tracks],
        }

    def to_json_string(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save_project_file(self, file_path: str) -> None:
        Path(file_path).write_text(self.to_json_string(), encoding="utf-8")

    def load_from_json_string(self, json_str: str, clear_history: bool = True) -> None:
        data = json.loads(json_str)
        self.name = data.get("name", "Untitled Project")
        self.aspect_ratio = data.get("aspect_ratio", "16:9")
        self.fps = int(data.get("fps", 30))
        self.playhead_sec = float(data.get("playhead_sec", 0.0))
        self.snapping_enabled = bool(data.get("snapping_enabled", True))
        self.auto_ducking = bool(data.get("auto_ducking", False))
        self.ducking_amount_db = float(data.get("ducking_amount_db", 12.0))
        self.markers = [TimelineMarker(**m) for m in data.get("markers", [])]
        loaded_tracks: List[TimelineTrack] = []
        for t_dict in data.get("tracks", []):
            clips_raw = t_dict.pop("clips", [])
            trk = TimelineTrack(**t_dict)
            for c_dict in clips_raw:
                color_d = c_dict.pop("color", {})
                chroma_d = c_dict.pop("chroma", {})
                mask_d = c_dict.pop("mask", {})
                text_d = c_dict.pop("text_style", {})
                kfs_d = c_dict.pop("keyframes", {})
                clip = TimelineClip(
                    **c_dict,
                    color=ColorGradeSettings(**color_d),
                    chroma=ChromaKeySettings(**chroma_d),
                    mask=MaskSettings(**mask_d),
                    text_style=TextStyleSettings(**text_d),
                    keyframes={
                        prop: [Keyframe(**kf) for kf in kf_list]
                        for prop, kf_list in kfs_d.items()
                    },
                )
                trk.clips.append(clip)
            loaded_tracks.append(trk)
        self.tracks = loaded_tracks
        if clear_history:
            self._undo_stack.clear()
            self._redo_stack.clear()

    def load_project_file(self, file_path: str) -> None:
        self.load_from_json_string(Path(file_path).read_text(encoding="utf-8"), clear_history=True)
