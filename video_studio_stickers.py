# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — built-in sticker library.

Every sticker is an ORIGINAL vector-style drawing generated in code with Pillow (4x supersampled for smooth
edges), so there are no third-party assets and no licensing obligations. Static stickers are saved as PNG and
animated ones as animated WebP (GIF fallback) with real alpha. Files are created on demand in the app data folder.
"""

import math
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, features

SIZE = 256
SS = 4  # supersampling factor
ANIM_FRAMES = 24
ANIM_SS = 3  # animated stickers render 24 frames, so a slightly lower supersampling keeps 'Add' snappy
ANIM_MS = 50

Draw = Callable[[ImageDraw.ImageDraw, int, float, Tuple[int, int, int]], None]  # (draw, S, phase 0..1, rgb)


def _hex_rgb(h: str) -> Tuple[int, int, int]:
    h = (h or "#FFFFFF").lstrip("#")
    if len(h) != 6:
        return (255, 255, 255)
    try:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return (255, 255, 255)


def _darker(rgb: Tuple[int, int, int], k: float = 0.55) -> Tuple[int, int, int]:
    return tuple(int(c * k) for c in rgb)  # type: ignore[return-value]


def _star_points(cx: float, cy: float, r_out: float, r_in: float, n: int = 5, rot: float = -math.pi / 2) -> List[Tuple[float, float]]:
    pts = []
    for i in range(n * 2):
        r = r_out if i % 2 == 0 else r_in
        a = rot + i * math.pi / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# ----------------------------------------------------------------------------- static drawings
def d_arrow(d, S, p, c):
    w = S
    d.polygon([(0.12 * w, 0.38 * w), (0.55 * w, 0.38 * w), (0.55 * w, 0.2 * w), (0.9 * w, 0.5 * w), (0.55 * w, 0.8 * w), (0.55 * w, 0.62 * w), (0.12 * w, 0.62 * w)], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.025 * w))


def d_arrow_curved(d, S, p, c):
    w = S
    d.arc([0.12 * w, 0.18 * w, 0.82 * w, 0.88 * w], start=200, end=345, fill=c + (255,), width=int(0.09 * w))
    d.polygon([(0.78 * w, 0.38 * w), (0.97 * w, 0.62 * w), (0.62 * w, 0.62 * w)], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.02 * w))


def d_star(d, S, p, c):
    d.polygon(_star_points(S / 2, S * 0.54, S * 0.46, S * 0.19), fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * S))


def d_heart(d, S, p, c):
    w = S
    pts = []
    for i in range(0, 360, 4):
        t = math.radians(i)
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((w / 2 + x * w * 0.027, w * 0.46 - y * w * 0.027))
    d.polygon(pts, fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))


def d_ring(d, S, p, c):
    m = 0.09 * S
    d.ellipse([m, m, S - m, S - m], outline=c + (255,), width=int(0.08 * S))


def d_check(d, S, p, c):
    w = S
    d.ellipse([0.06 * w, 0.06 * w, 0.94 * w, 0.94 * w], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.line([(0.27 * w, 0.52 * w), (0.43 * w, 0.68 * w), (0.74 * w, 0.34 * w)], fill=(255, 255, 255, 255), width=int(0.1 * w), joint="curve")


def d_cross(d, S, p, c):
    w = S
    d.ellipse([0.06 * w, 0.06 * w, 0.94 * w, 0.94 * w], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.line([(0.32 * w, 0.32 * w), (0.68 * w, 0.68 * w)], fill=(255, 255, 255, 255), width=int(0.1 * w))
    d.line([(0.68 * w, 0.32 * w), (0.32 * w, 0.68 * w)], fill=(255, 255, 255, 255), width=int(0.1 * w))


def d_bubble(d, S, p, c):
    w = S
    d.rounded_rectangle([0.06 * w, 0.12 * w, 0.94 * w, 0.68 * w], radius=0.16 * w, fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.polygon([(0.24 * w, 0.64 * w), (0.22 * w, 0.92 * w), (0.5 * w, 0.66 * w)], fill=c + (255,), outline=_darker(c) + (255,))
    for i in range(3):
        cx = 0.32 * w + i * 0.18 * w
        d.ellipse([cx - 0.04 * w, 0.37 * w, cx + 0.04 * w, 0.45 * w], fill=(255, 255, 255, 255))


def d_burst(d, S, p, c):
    d.polygon(_star_points(S / 2, S / 2, S * 0.48, S * 0.34, n=12), fill=c + (255,), outline=_darker(c) + (255,), width=int(0.025 * S))


def d_ribbon(d, S, p, c):
    w = S
    d.polygon([(0.04 * w, 0.32 * w), (0.96 * w, 0.32 * w), (0.9 * w, 0.5 * w), (0.96 * w, 0.68 * w), (0.04 * w, 0.68 * w), (0.1 * w, 0.5 * w)], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))


def d_underline(d, S, p, c):
    w = S
    pts = [(0.06 * w + i * 0.88 * w / 40, 0.5 * w + math.sin(i / 40 * 4 * math.pi) * 0.07 * w) for i in range(41)]
    d.line(pts, fill=c + (255,), width=int(0.07 * w), joint="curve")


def d_bracket_frame(d, S, p, c):
    w, t, L = S, int(0.06 * S), 0.28 * S
    for (x, y, sx, sy) in ((0.08, 0.08, 1, 1), (0.92, 0.08, -1, 1), (0.08, 0.92, 1, -1), (0.92, 0.92, -1, -1)):
        X, Y = x * w, y * w
        d.line([(X, Y + sy * L), (X, Y), (X + sx * L, Y)], fill=c + (255,), width=t, joint="curve")


# ----------------------------------------------------------------------------- animated drawings (phase 0..1, loops)
def a_pulse_ring(d, S, p, c):
    for k in (0.0, 0.5):
        q = (p + k) % 1.0
        r = S * (0.12 + 0.36 * q)
        a = int(255 * (1 - q))
        d.ellipse([S / 2 - r, S / 2 - r, S / 2 + r, S / 2 + r], outline=c + (a,), width=int(0.06 * S))
    d.ellipse([S * 0.44, S * 0.44, S * 0.56, S * 0.56], fill=c + (255,))


def a_bounce_arrow(d, S, p, c):
    off = abs(math.sin(p * math.pi)) * 0.18 * S
    w = S
    y = off
    d.polygon([(0.38 * w, 0.1 * w + y), (0.62 * w, 0.1 * w + y), (0.62 * w, 0.5 * w + y), (0.8 * w, 0.5 * w + y), (0.5 * w, 0.8 * w + y), (0.2 * w, 0.5 * w + y), (0.38 * w, 0.5 * w + y)], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.025 * w))


def a_heartbeat(d, S, p, c):
    k = 1.0 + 0.14 * max(0.0, math.sin(p * 2 * math.pi * 2)) 
    w = S
    pts = []
    for i in range(0, 360, 4):
        t = math.radians(i)
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((w / 2 + x * w * 0.027 * k, w * 0.46 - y * w * 0.027 * k))
    d.polygon(pts, fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))


def a_twinkle(d, S, p, c):
    for (cx, cy, r, ph) in ((0.5, 0.5, 0.34, 0.0), (0.2, 0.25, 0.14, 0.33), (0.8, 0.72, 0.17, 0.66)):
        s = 0.35 + 0.65 * (0.5 + 0.5 * math.sin((p + ph) * 2 * math.pi))
        R = r * S * s
        d.polygon(_star_points(cx * S, cy * S, R, R * 0.28, n=4, rot=-math.pi / 2), fill=c + (255,))


def a_spinner(d, S, p, c):
    for i in range(10):
        ang = (p * 2 * math.pi) - i * (2 * math.pi / 10)
        a = int(255 * (1 - i / 10))
        cx, cy = S / 2 + math.cos(ang) * S * 0.34, S / 2 + math.sin(ang) * S * 0.34
        r = S * 0.07
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c + (a,))


def a_confetti(d, S, p, c):
    cols = [c, (255, 205, 60), (80, 200, 255), (255, 90, 140), (120, 230, 120)]
    for i in range(22):
        ang = i * 2.399963
        dist = (0.12 + 0.34 * ((p + i * 0.037) % 1.0)) * S
        x, y = S / 2 + math.cos(ang) * dist, S / 2 + math.sin(ang) * dist + (dist / S) ** 2 * 0.35 * S
        a = int(255 * (1 - ((p + i * 0.037) % 1.0) ** 2))
        col = cols[i % len(cols)]
        s = S * 0.035
        rot = ang + p * 6
        pts = [(x + math.cos(rot + k * math.pi / 2) * s * 1.6, y + math.sin(rot + k * math.pi / 2) * s) for k in range(4)]
        d.polygon(pts, fill=col + (a,))


def a_dots(d, S, p, c):
    for i in range(3):
        y = S / 2 - abs(math.sin((p - i * 0.16) * math.pi)) * 0.18 * S if (p - i * 0.16) % 1.0 < 1.0 else S / 2
        x = S * (0.28 + i * 0.22)
        r = S * 0.075
        d.ellipse([x - r, y - r, x + r, y + r], fill=c + (255,))


def a_like_pop(d, S, p, c):
    k = 0.85 + 0.25 * math.sin(p * math.pi) ** 2
    w = S
    cx, cy = w / 2, w / 2
    def P(x, y):
        return (cx + (x - 0.5) * w * k, cy + (y - 0.5) * w * k)
    d.polygon([P(0.1, 0.45), P(0.3, 0.45), P(0.3, 0.86), P(0.1, 0.86)], fill=c + (255,))
    d.polygon([P(0.34, 0.45), P(0.5, 0.12), P(0.62, 0.16), P(0.58, 0.38), P(0.88, 0.38), P(0.9, 0.5), P(0.8, 0.84), P(0.34, 0.86)], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.02 * w))


# ----------------------------------------------------------------------------- more static drawings
def _rot_pts(pts: List[Tuple[float, float]], cx: float, cy: float, ang: float) -> List[Tuple[float, float]]:
    ca, sa = math.cos(ang), math.sin(ang)
    return [(cx + (x - cx) * ca - (y - cy) * sa, cy + (x - cx) * sa + (y - cy) * ca) for x, y in pts]


def _teardrop(cx: float, cy: float, r: float, tip: float, up: bool = True, n: int = 28) -> List[Tuple[float, float]]:
    """Round body (centre cx,cy radius r) with a pointed tip `tip` away from the centre (up or down)."""
    k = math.acos(max(-1.0, min(1.0, r / max(tip, r * 1.01))))
    base = -math.pi / 2 if up else math.pi / 2
    a0, a1 = base + k, base - k + 2 * math.pi
    pts = [(cx, cy - tip) if up else (cx, cy + tip)]
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def _mix(c: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return tuple(int(v + (255 - v) * t) for v in c)  # type: ignore[return-value]


def d_lightning(d, S, p, c):
    w = S
    pts = [(0.60, 0.05), (0.25, 0.55), (0.48, 0.55), (0.38, 0.95), (0.78, 0.42), (0.54, 0.42), (0.70, 0.05)]
    d.polygon([(x * w, y * w) for x, y in pts], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))


def d_flame(d, S, p, c, flick: float = 0.0):
    w = S
    f = flick
    tongues = [(0.30, 0.68, 0.15, 0.32 + 0.05 * f), (0.70, 0.66, 0.16, 0.36 - 0.05 * f), (0.5, 0.63, 0.27, 0.54 + 0.07 * f)]
    for grow in (0.022 * w, 0.0):  # dark rim first, then the fill on top so the union gets one clean outline
        col = _darker(c) if grow else c
        for cx, cy, r, tip in tongues:
            d.polygon(_teardrop(cx * w, cy * w, r * w + grow, tip * w + grow), fill=col + (255,))
    d.polygon(_teardrop(0.5 * w, 0.70 * w, 0.14 * w, (0.26 + 0.05 * f) * w), fill=_mix(c, 0.65) + (255,))


def d_crown(d, S, p, c):
    w = S
    pts = [(0.12, 0.78), (0.10, 0.30), (0.32, 0.52), (0.5, 0.18), (0.68, 0.52), (0.90, 0.30), (0.88, 0.78)]
    d.polygon([(x * w, y * w) for x, y in pts], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.rectangle([0.12 * w, 0.70 * w, 0.88 * w, 0.84 * w], fill=_darker(c, 0.8) + (255,), outline=_darker(c) + (255,), width=int(0.02 * w))
    for x, y in ((0.10, 0.30), (0.5, 0.18), (0.90, 0.30)):
        d.ellipse([(x - 0.05) * w, (y - 0.05) * w, (x + 0.05) * w, (y + 0.05) * w], fill=(255, 255, 255, 255))


def _note(d, S, c, ox=0.0, oy=0.0, k=1.0, a=255):
    w = S

    def P(x, y):
        return (0.5 * w + (x - 0.5) * w * k + ox * w, 0.5 * w + (y - 0.5) * w * k + oy * w)

    x0, y0 = P(0.2, 0.62)
    x1, y1 = P(0.48, 0.88)
    d.ellipse([x0, y0, x1, y1], fill=c + (a,))
    sx0, sy0 = P(0.42, 0.18)
    sx1, sy1 = P(0.5, 0.78)
    d.rectangle([sx0, sy0, sx1, sy1], fill=c + (a,))
    d.polygon([P(0.5, 0.18), P(0.8, 0.32), P(0.8, 0.5), P(0.5, 0.36)], fill=c + (a,))


def d_note(d, S, p, c):
    _note(d, S, c)


def d_bell(d, S, p, c, ang: float = 0.0):
    w = S
    pts: List[Tuple[float, float]] = []
    for i in range(0, 181, 6):
        t = math.radians(180 + i)
        pts.append((0.5 * w + 0.27 * w * math.cos(t), 0.42 * w + 0.30 * w * math.sin(t)))
    pts += [(0.80 * w, 0.72 * w), (0.92 * w, 0.80 * w), (0.08 * w, 0.80 * w), (0.20 * w, 0.72 * w)]
    top = (0.5 * w, 0.12 * w)
    clap = (0.5 * w, 0.88 * w)
    cx, cy = 0.5 * w, 0.12 * w  # pivot near the top
    pts = _rot_pts(pts, cx, cy, ang)
    d.polygon(pts, fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    kx, ky = _rot_pts([top], cx, cy, ang)[0]
    d.ellipse([kx - 0.05 * w, ky - 0.05 * w, kx + 0.05 * w, ky + 0.05 * w], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.02 * w))
    bx, by = _rot_pts([clap], cx, cy, ang * 1.4)[0]
    d.ellipse([bx - 0.07 * w, by - 0.07 * w, bx + 0.07 * w, by + 0.07 * w], fill=_darker(c, 0.8) + (255,))


def d_pin(d, S, p, c):
    w = S
    d.polygon(_teardrop(0.5 * w, 0.38 * w, 0.28 * w, 0.58 * w, up=False), fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.ellipse([0.4 * w, 0.28 * w, 0.6 * w, 0.48 * w], fill=(255, 255, 255, 255))


def d_play(d, S, p, c):
    w = S
    d.rounded_rectangle([0.06 * w, 0.2 * w, 0.94 * w, 0.8 * w], radius=0.16 * w, fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.polygon([(0.42 * w, 0.35 * w), (0.42 * w, 0.65 * w), (0.68 * w, 0.5 * w)], fill=(255, 255, 255, 255))


def d_moon(d, S, p, c):
    w = S
    d.ellipse([0.12 * w, 0.12 * w, 0.88 * w, 0.88 * w], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.ellipse([0.34 * w, 0.04 * w, 1.02 * w, 0.72 * w], fill=(0, 0, 0, 0))


def d_cloud(d, S, p, c):
    w = S
    shapes = [(0.14, 0.40, 0.46, 0.76), (0.28, 0.24, 0.62, 0.62), (0.46, 0.30, 0.82, 0.68), (0.6, 0.42, 0.92, 0.76)]
    grow = 0.025 * w
    for x0, y0, x1, y1 in shapes:
        d.ellipse([x0 * w - grow, y0 * w - grow, x1 * w + grow, y1 * w + grow], fill=_darker(c) + (255,))
    d.rectangle([0.28 * w - grow, 0.56 * w, 0.76 * w + grow, 0.78 * w + grow], fill=_darker(c) + (255,))
    for x0, y0, x1, y1 in shapes:
        d.ellipse([x0 * w, y0 * w, x1 * w, y1 * w], fill=c + (255,))
    d.rectangle([0.28 * w, 0.56 * w, 0.76 * w, 0.76 * w], fill=c + (255,))


def d_drop(d, S, p, c):
    w = S
    d.polygon(_teardrop(0.5 * w, 0.62 * w, 0.26 * w, 0.52 * w), fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.ellipse([0.37 * w, 0.58 * w, 0.45 * w, 0.72 * w], fill=_mix(c, 0.6) + (255,))


def d_exclam(d, S, p, c):
    w = S
    d.polygon(_star_points(0.5 * w, 0.5 * w, 0.48 * w, 0.40 * w, n=8, rot=-math.pi / 2 + math.pi / 8), fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    d.rounded_rectangle([0.45 * w, 0.22 * w, 0.55 * w, 0.58 * w], radius=0.05 * w, fill=(255, 255, 255, 255))
    d.ellipse([0.44 * w, 0.64 * w, 0.56 * w, 0.76 * w], fill=(255, 255, 255, 255))


def d_sparkle(d, S, p, c):
    d.polygon(_star_points(S / 2, S / 2, S * 0.46, S * 0.12, n=4), fill=c + (255,), outline=_darker(c) + (255,), width=int(0.02 * S))
    d.polygon(_star_points(S * 0.78, S * 0.24, S * 0.14, S * 0.04, n=4), fill=c + (255,))
    d.polygon(_star_points(S * 0.2, S * 0.78, S * 0.1, S * 0.03, n=4), fill=c + (255,))


def d_smile(d, S, p, c):
    w = S
    d.ellipse([0.06 * w, 0.06 * w, 0.94 * w, 0.94 * w], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))
    dark = _darker(c, 0.35) + (255,)
    d.ellipse([0.3 * w, 0.32 * w, 0.4 * w, 0.48 * w], fill=dark)
    d.ellipse([0.6 * w, 0.32 * w, 0.7 * w, 0.48 * w], fill=dark)
    d.arc([0.24 * w, 0.28 * w, 0.76 * w, 0.78 * w], start=25, end=155, fill=dark, width=int(0.05 * w))


# ----------------------------------------------------------------------------- more animated drawings
def a_sun_spin(d, S, p, c):
    w = S
    cx = cy = w / 2
    for i in range(12):
        ang = p * 2 * math.pi / 6 + i * math.pi / 6
        a0, a1 = 0.30 * w, 0.46 * w
        pts = _rot_pts([(cx - 0.035 * w, cy - a1), (cx + 0.035 * w, cy - a1), (cx + 0.02 * w, cy - a0), (cx - 0.02 * w, cy - a0)], cx, cy, ang)
        d.polygon(pts, fill=c + (255,))
    d.ellipse([cx - 0.23 * w, cy - 0.23 * w, cx + 0.23 * w, cy + 0.23 * w], fill=c + (255,), outline=_darker(c) + (255,), width=int(0.03 * w))


def a_bell_ring(d, S, p, c):
    ang = math.sin(p * 2 * math.pi * 3) * 0.32 * (1.0 - p) ** 0.5
    d_bell(d, S, p, c, ang)


def a_flame_flicker(d, S, p, c):
    d_flame(d, S, p, c, flick=math.sin(p * 2 * math.pi * 3) * 0.6 + math.sin(p * 2 * math.pi * 5) * 0.4)


def a_notes_float(d, S, p, c):
    for i, (ox, ph) in enumerate(((-0.18, 0.0), (0.16, 0.5))):
        q = (p + ph) % 1.0
        _note(d, S, c, ox=ox + math.sin(q * 2 * math.pi) * 0.04, oy=0.3 - q * 0.6, k=0.55, a=int(255 * min(1.0, q * 5) * (1 - q ** 3)))


def a_flash(d, S, p, c):
    k = 0.85 + 0.2 * max(0.0, math.sin(p * 2 * math.pi * 2)) ** 2
    a = int(255 * (0.55 + 0.45 * max(0.0, math.sin(p * 2 * math.pi * 2))))
    w = S
    pts = [(0.5 + (x - 0.5) * k, 0.5 + (y - 0.5) * k) for x, y in ((0.60, 0.05), (0.25, 0.55), (0.48, 0.55), (0.38, 0.95), (0.78, 0.42), (0.54, 0.42), (0.70, 0.05))]
    d.polygon([(x * w, y * w) for x, y in pts], fill=c + (a,), outline=_darker(c) + (a,), width=int(0.03 * w))


# id -> (name_ar, name_en, animated, draw_fn)
STICKERS: Dict[str, Tuple[str, str, bool, Draw]] = {
    "arrow": ("سهم", "Arrow", False, d_arrow),
    "arrow_curved": ("سهم منحني", "Curved arrow", False, d_arrow_curved),
    "star": ("نجمة", "Star", False, d_star),
    "heart": ("قلب", "Heart", False, d_heart),
    "ring": ("دائرة تمييز", "Highlight ring", False, d_ring),
    "check": ("صح", "Check", False, d_check),
    "cross": ("خطأ", "Cross", False, d_cross),
    "bubble": ("فقاعة كلام", "Speech bubble", False, d_bubble),
    "burst": ("انفجار", "Burst", False, d_burst),
    "ribbon": ("شريط", "Ribbon", False, d_ribbon),
    "underline": ("خط متموج", "Squiggle underline", False, d_underline),
    "frame": ("إطار تركيز", "Focus frame", False, d_bracket_frame),
    "pulse": ("نبضة (متحرك)", "Pulse (animated)", True, a_pulse_ring),
    "bounce": ("سهم قافز (متحرك)", "Bouncing arrow (animated)", True, a_bounce_arrow),
    "heartbeat": ("قلب نابض (متحرك)", "Heartbeat (animated)", True, a_heartbeat),
    "twinkle": ("لمعان (متحرك)", "Twinkle (animated)", True, a_twinkle),
    "spinner": ("تحميل (متحرك)", "Spinner (animated)", True, a_spinner),
    "confetti": ("قصاصات احتفال (متحرك)", "Confetti (animated)", True, a_confetti),
    "dots": ("نقاط قافزة (متحرك)", "Bouncing dots (animated)", True, a_dots),
    "like": ("إعجاب (متحرك)", "Like (animated)", True, a_like_pop),
    "lightning": ("صاعقة", "Lightning", False, d_lightning),
    "flame": ("نار", "Flame", False, d_flame),
    "crown": ("تاج", "Crown", False, d_crown),
    "note": ("نغمة موسيقية", "Music note", False, d_note),
    "bell": ("جرس", "Bell", False, d_bell),
    "pin": ("موقع", "Location pin", False, d_pin),
    "play": ("زر تشغيل", "Play button", False, d_play),
    "moon": ("هلال", "Crescent moon", False, d_moon),
    "cloud": ("سحابة", "Cloud", False, d_cloud),
    "drop": ("قطرة ماء", "Water drop", False, d_drop),
    "exclam": ("تنبيه", "Alert", False, d_exclam),
    "sparkle": ("بريق", "Sparkle", False, d_sparkle),
    "smile": ("وجه مبتسم", "Smiley", False, d_smile),
    "sun_spin": ("شمس دوّارة (متحرك)", "Spinning sun (animated)", True, a_sun_spin),
    "bell_ring": ("جرس يرنّ (متحرك)", "Ringing bell (animated)", True, a_bell_ring),
    "flame_flicker": ("نار متراقصة (متحرك)", "Flickering flame (animated)", True, a_flame_flicker),
    "notes_float": ("نغمات صاعدة (متحرك)", "Rising notes (animated)", True, a_notes_float),
    "flash": ("وميض (متحرك)", "Flash (animated)", True, a_flash),
}

COLORS = {"#FFD60A": ("أصفر", "Yellow"), "#FF3B5C": ("أحمر", "Red"), "#22C55E": ("أخضر", "Green"), "#00B7D4": ("سماوي", "Cyan"),
          "#A855F7": ("بنفسجي", "Purple"), "#FFFFFF": ("أبيض", "White"), "#FB923C": ("برتقالي", "Orange")}


def render_frame(sticker_id: str, phase: float, color_hex: str, size: int = SIZE, ss: int = SS) -> Image.Image:
    """One RGBA frame at size x size (supersampled by `ss` then downscaled for clean edges). Small sizes are cheap:
    the panel renders 44 px icons this way instead of paying for full 256 px frames."""
    _, _, _, fn = STICKERS[sticker_id]
    big = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
    fn(ImageDraw.Draw(big, "RGBA"), size * ss, phase, _hex_rgb(color_hex))
    return big.resize((size, size), Image.LANCZOS if size >= 128 else Image.BILINEAR if ss == 1 else Image.LANCZOS)


def sticker_display_name(sticker_id: str, lang: str) -> str:
    """Name of a built-in sticker in the UI language (Arabic in Arabic, English in English)."""
    entry = STICKERS.get(sticker_id)
    if entry is None:
        return sticker_id
    return entry[0] if lang == "ar" else entry[1]


def clip_display_name(clip, lang: str) -> str:
    """Timeline label of a clip: built-in stickers follow the UI language, everything else keeps its own name."""
    meta = getattr(clip, "ai_metadata", None) or {}
    sid = meta.get("sticker_id") if isinstance(meta, dict) else None
    if sid in STICKERS:
        return sticker_display_name(str(sid), lang).replace(" (متحرك)", "").replace(" (animated)", "")
    return str(getattr(clip, "name", ""))


def sticker_file(sticker_id: str, folder: Path, color_hex: str = "#FFD60A") -> Optional[Path]:
    """Create (once) and return the sticker file for this id + color. Animated -> .webp (or .gif fallback), static -> .png."""
    if sticker_id not in STICKERS:
        return None
    color_hex = color_hex if color_hex.startswith("#") and len(color_hex) == 7 else "#FFD60A"
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    animated = STICKERS[sticker_id][2]
    webp_ok = bool(features.check("webp"))
    ext = ".png" if not animated else (".webp" if webp_ok else ".gif")
    out = folder / f"{sticker_id}_{color_hex.lstrip('#').lower()}{ext}"
    if out.exists() and out.stat().st_size > 0:
        return out
    tmp = out.with_name(out.stem + ".tmp" + ext)
    try:
        if not animated:
            render_frame(sticker_id, 0.0, color_hex).save(tmp)
        else:
            frames = [render_frame(sticker_id, i / ANIM_FRAMES, color_hex, SIZE, ANIM_SS) for i in range(ANIM_FRAMES)]
            saved = False
            if ext == ".webp":
                try:
                    frames[0].save(tmp, save_all=True, append_images=frames[1:], duration=ANIM_MS, loop=0, lossless=True, format="WEBP")
                    saved = True
                except Exception:  # Pillow built without animated WebP -> GIF
                    tmp.unlink(missing_ok=True)
                    ext = ".gif"
                    out = out.with_suffix(".gif")
                    tmp = out.with_name(out.stem + ".tmp.gif")
            if not saved:
                pal = [f.convert("P", palette=Image.ADAPTIVE, colors=255) for f in frames]
                pal[0].save(tmp, save_all=True, append_images=pal[1:], duration=ANIM_MS, loop=0, disposal=2, transparency=0, format="GIF")
        tmp.replace(out)
    except Exception:
        tmp.unlink(missing_ok=True)
        return None
    return out
