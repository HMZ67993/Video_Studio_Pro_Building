# -*- coding: utf-8 -*-
"""
HMZ Video Studio Pro — Local AI / analysis tools.

Every tool here does real work on the user's machine (nothing is faked):

* Beat detection      — onset analysis (spectral flux) + tempo + beat grid, pure NumPy.
* Scene detection     — HSV histogram differences with OpenCV, then splits the clip.
* Noise reduction     — spectral gating (STFT), pure NumPy, writes a cleaned WAV.
* Auto captions       — faster-whisper (OPTIONAL dependency, model downloaded on demand).
* Smart cutout        — ONNX human-segmentation model (OPTIONAL dependency + on-demand model),
                        per-frame masks with temporal smoothing; applied by the renderer.

Each tool is split into ``analyze`` (heavy, thread-safe, never touches the project) and
``apply`` (fast, edits the project on the UI thread). ``execute`` runs both (used by tests).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from video_studio_core import TextStyleSettings, TimelineClip, TimelineMarker, VideoStudioProject, evaluate_speed_curve

Progress = Optional[Callable[[int], None]]
Cancel = Optional[Callable[[], bool]]


class AIError(Exception):
    """Raised with a short machine-readable reason (``args[0]``) and an optional detail."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def get_ai_models_dir(custom_dir: Optional[Path] = None) -> Path:
    """Return the canonical models directory; safe to call with either app root or models root.

    AIPluginRegistry historically passed its already-resolved ``ai_models`` directory
    into each plugin, which used to append ``ai_models`` a second time.  Accept both
    forms so registry and direct plugin construction resolve to the same location.
    """
    if custom_dir is not None:
        supplied = Path(custom_dir).expanduser()
        base = supplied if supplied.name.casefold() == "ai_models" else supplied / "ai_models"
    else:
        appdata = os.environ.get("APPDATA") or str(Path.home() / ".config")
        base = Path(appdata) / "HMZVideoStudioPro" / "ai_models"
    base.mkdir(parents=True, exist_ok=True)

    # Migrate data created by the old double-append bug without overwriting anything.
    legacy = base / "ai_models"
    if legacy.is_dir():
        try:
            for item in legacy.iterdir():
                destination = base / item.name
                if destination.exists():
                    continue
                try:
                    shutil.move(str(item), str(destination))
                except OSError:
                    # Keep the legacy item intact; a later run can retry the migration.
                    continue
            if not any(legacy.iterdir()):
                legacy.rmdir()
        except OSError:
            pass
    return base


def _tick(progress: Progress, value: float) -> None:
    if progress:
        progress(int(max(0, min(100, value))))


def _cancelled(cancel: Cancel) -> bool:
    return bool(cancel and cancel())


# ---------------------------------------------------------------------------
# DSP: beat detection
# ---------------------------------------------------------------------------
def onset_envelope(x: np.ndarray, rate: int, n_fft: int = 1024, hop: int = 512, cancel: Cancel = None) -> np.ndarray:
    """Spectral-flux onset strength per frame (frame rate = rate / hop)."""
    if len(x) < n_fft * 4:
        return np.zeros(0, dtype=np.float32)
    win = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (len(x) - n_fft) // hop
    out = np.zeros(n_frames, dtype=np.float32)
    prev: Optional[np.ndarray] = None
    block = 1500
    for a in range(0, n_frames, block):
        if _cancelled(cancel):
            raise AIError("cancelled")
        b = min(n_frames, a + block)
        idx = np.arange(n_fft)[None, :] + hop * np.arange(a, b)[:, None]
        mag = np.log1p(np.abs(np.fft.rfft(x[idx] * win, axis=1)) * 10.0).astype(np.float32)
        ext = mag if prev is None else np.vstack([prev[None, :], mag])
        flux = np.maximum(0.0, np.diff(ext, axis=0)).sum(axis=1)
        if prev is None:
            out[a + 1:b] = flux
        else:
            out[a:b] = flux
        prev = mag[-1].copy()
    return out


def estimate_beats(env: np.ndarray, frame_rate: float, bpm_min: float = 70.0, bpm_max: float = 180.0) -> Optional[Dict[str, Any]]:
    """Tempo (autocorrelation) + phase search -> evenly spaced beat grid. None if no clear rhythm."""
    if len(env) < frame_rate * 4:
        return None
    k = max(3, int(frame_rate * 0.5))
    local = np.convolve(env, np.ones(k) / k, mode="same")
    e = np.maximum(env - local, 0.0)
    if float(e.std()) < 1e-6:
        return None
    e = e / (e.max() + 1e-9)
    n = len(e)
    f = np.fft.rfft(e - e.mean(), 2 * n)
    ac = np.fft.irfft(f * np.conj(f))[:n]
    ac = ac / (ac[0] + 1e-9)
    lo = int(frame_rate * 60.0 / bpm_max)
    hi = min(n - 1, int(frame_rate * 60.0 / bpm_min))
    if hi <= lo + 2:
        return None
    lags = np.arange(lo, hi + 1)
    bpms = 60.0 * frame_rate / lags
    prior = np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.7) ** 2)  # mild preference for ~120 BPM
    score = ac[lo:hi + 1] * prior
    best = int(lags[int(np.argmax(score))])
    if float(ac[best]) < 0.08:
        return None
    # refine the (fractional) period and the phase with a grid score on the onset envelope
    best_total, best_period, best_phase = -1.0, float(best), 0.0
    for period in np.arange(best - 1.0, best + 1.001, 0.05):
        if period < 2:
            continue
        for phase in np.arange(0.0, period, max(0.5, period / 24.0)):
            pos = np.arange(phase, n - 1, period)
            idx = pos.astype(int)
            total = float(e[idx].sum() + e[np.minimum(idx + 1, n - 1)].sum() * 0.5 + e[np.maximum(idx - 1, 0)].sum() * 0.5) / len(idx)
            if total > best_total:
                best_total, best_period, best_phase = total, float(period), float(phase)
    times = [float(p / frame_rate) for p in np.arange(best_phase, n - 1, best_period)]
    return {"bpm": 60.0 * frame_rate / best_period, "beats": times, "confidence": float(ac[best])}


def detect_beats(samples: np.ndarray, rate: int, cancel: Cancel = None) -> Optional[Dict[str, Any]]:
    hop = 512
    env = onset_envelope(samples, rate, hop=hop, cancel=cancel)
    return estimate_beats(env, rate / hop)


# ---------------------------------------------------------------------------
# DSP: scene detection
# ---------------------------------------------------------------------------
def detect_gradual_transition_times(diffs: List[Tuple[float, float]], start: float, duration: float,
                                    min_scene: float = 0.8, min_run: int = 3) -> List[float]:
    """Detect sustained histogram change patterns (dissolves/fades), not just hard cuts."""
    if len(diffs) < min_run:
        return []
    values = [float(v) for _, v in diffs]
    candidates: List[float] = []
    i = 0
    while i < len(values):
        # Medium consecutive changes form a gradual transition; a single large spike is a hard cut.
        if 0.055 <= values[i] <= 0.42:
            j = i
            while j < len(values) and 0.055 <= values[j] <= 0.42:
                j += 1
            run = values[i:j]
            if len(run) >= min_run and sum(run) >= 0.55:
                mid = (i + j - 1) // 2
                t = float(diffs[mid][0])
                if t - start >= min_scene and start + duration - t >= min_scene:
                    if not candidates or t - candidates[-1] >= min_scene:
                        candidates.append(t)
            i = max(i + 1, j)
        else:
            i += 1
    return candidates


def detect_scene_cuts(
    video_path: str,
    start: float,
    duration: float,
    sample_fps: float = 6.0,
    min_scene: float = 0.8,
    progress: Progress = None,
    cancel: Cancel = None,
) -> List[float]:
    """Source-time positions (seconds) of hard cuts inside [start, start+duration]."""
    import cv2

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise AIError("decode_failed")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, int(round(fps / sample_fps)))
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        first = int(round(start * fps))
        last = first + int(duration * fps)
        diffs: List[Tuple[float, float]] = []
        prev_hist = None
        frame_no = first
        while frame_no < last:
            if _cancelled(cancel):
                raise AIError("cancelled")
            ok = cap.grab()
            if not ok:
                break
            if (frame_no - first) % step == 0:
                ok, fr = cap.retrieve()
                if not ok:
                    break
                small = cv2.resize(fr, (96, 54), interpolation=cv2.INTER_AREA)
                hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 4], [0, 180, 0, 256, 0, 256])
                cv2.normalize(hist, hist, 1.0, 0.0, cv2.NORM_L1)
                if prev_hist is not None:
                    d = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                    diffs.append((frame_no / fps, d))
                prev_hist = hist
                if (frame_no - first) % (step * 20) == 0:
                    _tick(progress, 100.0 * (frame_no - first) / max(1, last - first))
            frame_no += 1
    finally:
        cap.release()

    cuts: List[float] = []
    values = np.asarray([d for _, d in diffs], dtype=np.float32)
    for i, (t, d) in enumerate(diffs):
        # Robust local baseline: MAD adapts to noisy footage without treating every
        # camera pan as a cut. A hard cut is a single strong spike; gradual changes
        # are handled separately below as sustained runs.
        window = np.concatenate([values[max(0, i - 12):i], values[i + 1:i + 5]])
        base = float(np.median(window)) if window.size else 0.0
        mad = float(np.median(np.abs(window - base))) if window.size else 0.0
        threshold = max(0.40, base + max(0.14, 5.0 * mad))
        if d > threshold:
            if not cuts or t - cuts[-1] >= min_scene:
                if t - start >= min_scene and (start + duration) - t >= min_scene:
                    cuts.append(t)
    gradual = detect_gradual_transition_times(diffs, start, duration, min_scene=min_scene)
    for t in gradual:
        if all(abs(t-existing) >= min_scene for existing in cuts):
            cuts.append(t)
    return sorted(cuts)


# ---------------------------------------------------------------------------
# Local motion analysis helpers used by Auto Reframe and Motion Tracking
# ---------------------------------------------------------------------------
def track_salient_subject(video_path: str, start: float = 0.0, duration: Optional[float] = None,
                          sample_fps: float = 8.0, cancel: Cancel = None) -> List[Tuple[float, float, float]]:
    """Return (source_time, normalized_x, normalized_y) subject-centre samples.

    Uses OpenCV's built-in saliency when available and a contrast/edge fallback otherwise.
    This is deliberately model-free and local; review the generated path before applying it.
    """
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise AIError("decode_failed")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    end = start + (duration if duration is not None else (total / fps if total else 3600.0))
    step = max(1, int(round(fps / max(1.0, sample_fps))))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
    out: List[Tuple[float, float, float]] = []
    frame_no = int(start * fps)
    saliency_detector = None
    face_detector = None
    previous_center: Optional[Tuple[float, float]] = None
    try:
        try:
            saliency_detector = cv2.saliency.StaticSaliencySpectralResidual_create()
        except Exception:
            saliency_detector = None
        try:
            face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        except Exception:
            face_detector = None
        while frame_no / fps < end:
            if _cancelled(cancel):
                raise AIError("cancelled")
            ok = cap.grab()
            if not ok:
                break
            if (frame_no - int(start * fps)) % step == 0:
                ok, frame = cap.retrieve()
                if not ok:
                    break
                small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
                face_box = None
                if face_detector is not None and not face_detector.empty():
                    gray_face = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    faces = face_detector.detectMultiScale(gray_face, scaleFactor=1.1, minNeighbors=5, minSize=(12, 12))
                    if len(faces):
                        if previous_center is None:
                            chosen = max(faces, key=lambda b: b[2] * b[3])
                        else:
                            px, py = previous_center[0] * 159.0, previous_center[1] * 89.0
                            chosen = min(faces, key=lambda b: ((b[0]+b[2]/2-px)**2 + (b[1]+b[3]/2-py)**2) / max(64.0, b[2]*b[3]))
                        fx, fy, fw, fh = chosen
                        face_box = (fx + fw / 2.0, fy + fh / 2.0)
                sal = None
                if face_box is None and saliency_detector is not None:
                    try:
                        ok_sal, sal = saliency_detector.computeSaliency(small)
                        if not ok_sal:
                            sal = None
                    except Exception:
                        sal = None
                if face_box is not None:
                    cx, cy = face_box[0] / 159.0, face_box[1] / 89.0
                else:
                    if sal is None:
                        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                        sal = cv2.Canny(gray, 45, 110).astype(np.float32) / 255.0
                        sal = cv2.GaussianBlur(sal, (0, 0), 9)
                    # Prefer a local saliency window around the previous target to avoid
                    # switching to a bright background object between samples.
                    if previous_center is not None:
                        px, py = int(previous_center[0] * 159), int(previous_center[1] * 89)
                        local = np.zeros_like(sal, dtype=np.float32)
                        local[max(0,py-24):min(90,py+25), max(0,px-32):min(160,px+33)] = 1.0
                        sal = sal.astype(np.float32) * (0.25 + 0.75 * local)
                    _, _, _, maxloc = cv2.minMaxLoc(sal.astype(np.float32))
                    # Use a weighted local centroid around the saliency peak to reduce jitter.
                    x, y = maxloc
                    roi = sal[max(0,y-12):min(90,y+13), max(0,x-12):min(160,x+13)]
                    yy, xx = np.mgrid[max(0,y-12):min(90,y+13), max(0,x-12):min(160,x+13)]
                    weights = np.maximum(roi, 0) + 1e-4
                    cx = float((xx * weights).sum() / weights.sum()) / 159.0
                    cy = float((yy * weights).sum() / weights.sum()) / 89.0
                previous_center = (float(cx), float(cy))
                out.append((frame_no / fps, cx, cy))
            frame_no += 1
    finally:
        cap.release()
    return out


def smooth_tracking_path(samples: List[Tuple[float, float, float]], radius: int = 3) -> List[Tuple[float, float, float]]:
    """Robustly smooth normalized tracks, reject isolated jumps, and limit acceleration."""
    if not samples:
        return []
    radius = max(1, min(12, int(radius)))
    raw = np.asarray([[float(x), float(y)] for _t, x, y in samples], dtype=np.float32)
    med = np.empty_like(raw)
    for i in range(len(raw)):
        window = raw[max(0, i-radius):min(len(raw), i+radius+1)]
        med[i] = np.median(window, axis=0)
    out = []
    current = med[0].copy()
    velocity = np.zeros(2, dtype=np.float32)
    for i, (t, _x, _y) in enumerate(samples):
        target = med[i]
        delta = target - current
        # Cap a single sample jump; larger changes are usually detector switches.
        distance = float(np.linalg.norm(delta))
        if distance > 0.12:
            delta *= 0.12 / max(distance, 1e-6)
        velocity = 0.55 * velocity + 0.45 * delta
        current = np.clip(current + 0.72 * delta + 0.28 * velocity, 0.0, 1.0)
        out.append((float(t), float(current[0]), float(current[1])))
    return out


# ---------------------------------------------------------------------------
# DSP: noise reduction (spectral gating)
# ---------------------------------------------------------------------------
def denoise_audio(x: np.ndarray, rate: int, reduction_db: float = 18.0, cancel: Cancel = None, progress: Progress = None) -> np.ndarray:
    """Estimate the noise floor from the quietest frames and attenuate bins near/below it."""
    n_fft, hop = 1024, 256
    if len(x) < n_fft * 8:
        return x.copy()
    win = np.hanning(n_fft).astype(np.float32)
    pad = np.concatenate([np.zeros(n_fft, np.float32), x.astype(np.float32), np.zeros(n_fft * 2, np.float32)])
    n_frames = 1 + (len(pad) - n_fft) // hop
    block = 1200

    def mags(a: int, b: int) -> np.ndarray:
        idx = np.arange(n_fft)[None, :] + hop * np.arange(a, b)[:, None]
        return np.fft.rfft(pad[idx] * win, axis=1)

    energy = np.zeros(n_frames, np.float32)
    for a in range(0, n_frames, block):
        if _cancelled(cancel):
            raise AIError("cancelled")
        b = min(n_frames, a + block)
        idx = np.arange(n_fft)[None, :] + hop * np.arange(a, b)[:, None]
        energy[a:b] = np.sqrt(np.mean(pad[idx] ** 2, axis=1))
    quiet = np.argsort(energy)[: max(8, min(2000, n_frames // 10))]
    idx = np.arange(n_fft)[None, :] + hop * quiet[:, None]
    noise = np.mean(np.abs(np.fft.rfft(pad[idx] * win, axis=1)), axis=0) + 1e-9
    noise_hi = noise * 1.6  # margin above the average noise magnitude
    floor = 10.0 ** (-reduction_db / 20.0)

    out = np.zeros(len(pad), np.float32)
    norm = np.zeros(len(pad), np.float32)
    ctx = 3
    kern_t = np.array([0.2, 0.6, 0.2], np.float32)
    kern_f = np.array([0.25, 0.5, 0.25], np.float32)
    for a in range(0, n_frames, block):
        if _cancelled(cancel):
            raise AIError("cancelled")
        b = min(n_frames, a + block)
        ea, eb = max(0, a - ctx), min(n_frames, b + ctx)
        spec = mags(ea, eb)
        mag = np.abs(spec)
        gain = np.clip((mag - noise_hi[None, :]) / (mag + 1e-9), 0.0, 1.0)
        gain = np.maximum(gain, floor)
        # smooth in frequency and time to avoid "musical noise"
        gain = np.apply_along_axis(lambda v: np.convolve(v, kern_f, mode="same"), 1, gain)
        gp = np.pad(gain, ((1, 1), (0, 0)), mode="edge")
        gain = kern_t[0] * gp[:-2] + kern_t[1] * gp[1:-1] + kern_t[2] * gp[2:]
        sel = slice(a - ea, a - ea + (b - a))
        frames = np.fft.irfft(spec[sel] * gain[sel], n=n_fft, axis=1).astype(np.float32) * win
        for j in range(b - a):
            s = (a + j) * hop
            out[s:s + n_fft] += frames[j]
            norm[s:s + n_fft] += win * win
        _tick(progress, 100.0 * b / n_frames)
    out /= np.maximum(norm, 1e-6)
    res = out[n_fft:n_fft + len(x)]
    return np.clip(res, -1.0, 1.0).astype(np.float32)


def write_wav_mono(path: Path, samples: np.ndarray, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


# ---------------------------------------------------------------------------
# Captions helpers
# ---------------------------------------------------------------------------
def split_caption(text: str, max_chars: int = 42) -> List[str]:
    words = text.strip().split()
    lines: List[str] = []
    cur = ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > max_chars:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------------------------------------------------------------------------
# Plugin base
# ---------------------------------------------------------------------------
@dataclass
class AIPluginDescriptor:
    plugin_id: str
    name_ar: str
    name_en: str
    desc_ar: str
    desc_en: str
    category: str
    model_filename: str = ""
    approx_size_mb: int = 0
    needs_clip: str = ""  # "" = none, "audio" = audio or video clip, "video" = video/image clip


def _clip_span(clip: TimelineClip) -> Tuple[float, float]:
    """Source start and length (seconds of source) covered by the clip."""
    declared = float(clip.source_out) - float(clip.source_in)
    return clip.source_in, max(0.1, declared if declared > 0.05 else clip.duration * clip.speed)


def _source_offset_to_timeline(clip: TimelineClip, source_offset: float) -> float:
    """Map source-relative seconds (Whisper timestamps) into timeline seconds.

    A binary search over the integrated speed curve keeps captions aligned when a
    clip uses speed ramping; constant-speed clips retain the exact simple mapping.
    """
    target = max(0.0, float(source_offset))
    if clip.speed_curve == "constant":
        return min(max(0.0, clip.duration), target / max(0.05, float(clip.speed or 1.0)))
    duration = max(0.05, float(clip.duration))
    def source_at(t: float) -> float:
        steps = max(8, int(64 * t / duration))
        dt = t / steps if steps else 0.0
        total = 0.0
        for i in range(steps):
            mid = (i + 0.5) * dt
            total += evaluate_speed_curve(clip.speed_curve, mid / duration, clip.speed) * dt
        return total
    lo, hi = 0.0, duration
    for _ in range(28):
        mid = (lo + hi) * 0.5
        if source_at(mid) < target:
            lo = mid
        else:
            hi = mid
    return min(duration, (lo + hi) * 0.5)


class BaseAIPlugin:
    descriptor: AIPluginDescriptor

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = get_ai_models_dir(models_dir)

    # ---- environment -----------------------------------------------------
    def ensure_runtime(self, progress: Progress = None, cancel: Cancel = None) -> None:
        """Install and activate the optional native runtime when this plugin needs it."""
        return None

    def dependency_error(self) -> str:
        """'' when usable, otherwise a short code (e.g. 'missing_dependency:onnxruntime')."""
        return ""

    def is_installed(self) -> bool:
        return True

    def install_model(self, progress: Progress = None, cancel: Cancel = None) -> Optional[Path]:
        return None

    # ---- work ------------------------------------------------------------
    def analyze(self, clip: Optional[TimelineClip], params: Dict[str, Any], progress: Progress = None, cancel: Cancel = None) -> Dict[str, Any]:
        raise NotImplementedError

    def apply(self, project: VideoStudioProject, clip: Optional[TimelineClip], result: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    def execute(
        self,
        project: VideoStudioProject,
        clip: Optional[TimelineClip] = None,
        params: Optional[Dict[str, Any]] = None,
        progress: Progress = None,
        cancel: Cancel = None,
    ) -> Dict[str, Any]:
        try:
            res = self.analyze(clip, params or {}, progress, cancel)
            if not res.get("ok"):
                return res
            return self.apply(project, clip, res)
        except AIError as exc:
            return {"ok": False, "reason": exc.reason, "detail": exc.detail}

    # ---- shared checks -----------------------------------------------------
    def _need_clip(self, clip: Optional[TimelineClip], kinds: Tuple[str, ...]) -> None:
        if clip is None:
            raise AIError("no_clip")
        if clip.clip_type not in kinds or not clip.source_path or not os.path.exists(clip.source_path):
            raise AIError("wrong_clip_type")
        if clip.reverse:
            raise AIError("reverse_unsupported")

    @staticmethod
    def _ffmpeg(params: Dict[str, Any]) -> str:
        ff = params.get("ffmpeg")
        if not ff:
            raise AIError("no_ffmpeg")
        return str(ff)

    def _src_to_timeline(self, clip: TimelineClip, t_src: float) -> float:
        return clip.timeline_start + (t_src - clip.source_in) / max(0.05, clip.speed)


# ---------------------------------------------------------------------------
# 1) Beat detection
# ---------------------------------------------------------------------------
class AutoBeatDetectionPlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_beat_detection",
        name_ar="اكتشاف إيقاع الموسيقى ووضع علامات (Beat Markers)",
        name_en="Music Beat Detection & Markers",
        desc_ar="يحلل صوت المقطع المحدد (موسيقى أو فيديو به موسيقى) ويضع علامة على كل ضربة على التايم لاين لتقطع على الإيقاع. يعمل بدون تحميل نماذج. النتيجة جيدة مع الموسيقى ذات الإيقاع الواضح.",
        desc_en="Analyses the selected clip (music or a video with music) and drops a marker on every beat so you can cut on rhythm. No model download. Works best with a clear steady beat.",
        category="timeline",
        needs_clip="audio",
    )

    def analyze(self, clip, params, progress=None, cancel=None):
        from video_studio_ffmpeg import decode_pcm_mono

        self._need_clip(clip, ("audio", "video"))
        ff = self._ffmpeg(params)
        start, length = _clip_span(clip)
        _tick(progress, 5)
        x = decode_pcm_mono(ff, clip.source_path, rate=22050, max_seconds=1800.0, start=start, duration=length)
        if x is None:
            raise AIError("decode_failed")
        _tick(progress, 30)
        info = detect_beats(x, 22050, cancel)
        if info is None:
            raise AIError("no_rhythm")
        _tick(progress, 100)
        beats = [self._src_to_timeline(clip, start + t) for t in info["beats"]]
        beats = [b for b in beats if clip.timeline_start <= b <= clip.timeline_end]
        return {"ok": True, "bpm": round(info["bpm"], 1), "beats": beats, "confidence": info["confidence"]}

    def apply(self, project, clip, result):
        project.push_undo_snapshot()
        project.markers[:] = [m for m in project.markers if not m.label.startswith("Beat ")]
        for i, t in enumerate(result["beats"], 1):
            project.markers.append(TimelineMarker(time_sec=round(t, 3), label=f"Beat {i}", color_hex="#00D2E6"))
        project.markers.sort(key=lambda m: m.time_sec)
        return {"ok": True, "markers_added": len(result["beats"]), "bpm": result["bpm"]}


# ---------------------------------------------------------------------------
# 2) Scene detection
# ---------------------------------------------------------------------------
class AutoSceneSplitPlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_scene_split",
        name_ar="اكتشاف المشاهد وتقطيع المقطع تلقائياً",
        name_en="Scene Detection & Auto Split",
        desc_ar="يبحث عن القطعات الحادة (تغيّر اللقطة) داخل المقطع المحدد ويقسمه عندها. يعمل بدون تحميل نماذج. لا يلتقط الانتقالات التدريجية (fade) جيداً.",
        desc_en="Finds hard cuts inside the selected clip and splits it there. No model download. Gradual fades/dissolves are not detected reliably.",
        category="timeline",
        needs_clip="video",
    )

    def analyze(self, clip, params, progress=None, cancel=None):
        self._need_clip(clip, ("video",))
        start, length = _clip_span(clip)
        cuts = detect_scene_cuts(clip.source_path, start, length, progress=progress, cancel=cancel)
        if not cuts:
            raise AIError("no_scenes")
        return {"ok": True, "cuts": [self._src_to_timeline(clip, t) for t in cuts]}

    def apply(self, project, clip, result):
        cur = clip
        made = 0
        for t in sorted(result["cuts"], reverse=True):
            res = project.split_clip_at(cur.id, split_time=round(t, 3))
            if res:
                cur = res[0]
                made += 1
        return {"ok": made > 0, "reason": "" if made else "no_scenes", "splits": made}


# ---------------------------------------------------------------------------
# 3) Noise reduction
# ---------------------------------------------------------------------------
class AudioNoiseReductionPlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_noise_reduction",
        name_ar="تقليل ضوضاء الصوت (Noise Reduction)",
        name_en="Audio Noise Reduction",
        desc_ar="يقدّر مستوى الضوضاء الثابتة (هسهسة الميكروفون، مروحة، تكييف) من أهدأ أجزاء المقطع ثم يخفضها. يعمل بدون تحميل نماذج. فعّال مع الضوضاء الثابتة وليس مع الضوضاء المتغيرة أو الأصوات المتداخلة.",
        desc_en="Estimates steady noise (mic hiss, fan, AC) from the quietest parts of the clip and attenuates it. No model download. Effective on steady noise, not on changing noise or overlapping voices.",
        category="audio",
        needs_clip="audio",
    )

    def analyze(self, clip, params, progress=None, cancel=None):
        from video_studio_ffmpeg import decode_pcm_mono

        self._need_clip(clip, ("audio", "video"))
        ff = self._ffmpeg(params)
        work = Path(params.get("work_dir") or tempfile.gettempdir())
        start, length = _clip_span(clip)
        rate = 44100
        _tick(progress, 5)
        x = decode_pcm_mono(ff, clip.source_path, rate=rate, max_seconds=3600.0, start=start, duration=length)
        if x is None:
            raise AIError("decode_failed")
        y = denoise_audio(x, rate, float(params.get("reduction_db", 18.0)), cancel=cancel, progress=lambda v: _tick(progress, 10 + v * 0.85))
        out = work / f"denoised_{clip.id}_{abs(hash((clip.source_path, start, length))) % 10**8}.wav"
        write_wav_mono(out, y, rate)
        _tick(progress, 100)
        return {"ok": True, "wav": str(out), "length": len(y) / rate}

    def apply(self, project, clip, result):
        target = clip
        if clip.clip_type == "video":
            target = project.detach_audio_from_clip(clip.id)
            if target is None:
                return {"ok": False, "reason": "locked"}
        else:
            project.push_undo_snapshot()
        speed = target.speed
        target.source_path = result["wav"]
        target.source_in = 0.0
        target.source_out = round(result["length"], 3)
        target.duration = round(result["length"] / max(0.05, speed), 3)
        target.waveform_peaks = []
        target.ai_metadata["noise_reduced"] = True
        return {"ok": True, "clip_id": target.id}


# ---------------------------------------------------------------------------
# 4) Auto captions (faster-whisper, optional)
# ---------------------------------------------------------------------------
class WhisperAutoCaptionsPlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_whisper_captions",
        name_ar="الترجمة النصية التلقائية للكلام (Whisper)",
        name_en="Auto Captions (Whisper)",
        desc_ar="يحوّل الكلام في المقطع المحدد إلى مقاطع نص متزامنة على مسار «ترجمة AI». يدعم العربية والإنجليزية وغيرها. اختر حجم نموذج Whisper من الصغير والسريع إلى الكبير والأدق؛ يتم تنزيل المحرك والنموذج تلقائياً عند الطلب. راجع النص دائماً.",
        desc_en="Turns speech in the selected clip into synced text clips on an 'AI Subtitles' track. Choose a Whisper model from small/fast to large/more accurate. The runtime and selected model download on demand; always proofread.",
        category="text",
        model_filename="whisper",
        approx_size_mb=145,
        needs_clip="audio",
    )
    MODEL_SIZE = "base"
    MODEL_OPTIONS = {"tiny": 75, "base": 145, "small": 490, "medium": 1500, "large-v3": 3000}

    def __init__(self, models_dir: Optional[Path] = None):
        super().__init__(models_dir)
        self.model_size = self.MODEL_SIZE

    @property
    def model_dir(self) -> Path:
        return self.models_dir / f"whisper_{self.model_size}"

    def ensure_runtime(self, progress=None, cancel=None) -> None:
        from video_studio_ai_runtime import install_runtime
        install_runtime(progress, cancel)

    def dependency_error(self) -> str:
        try:
            from video_studio_ai_runtime import activate_runtime
            activate_runtime()
            import faster_whisper  # noqa: F401
            import ctranslate2  # noqa: F401
        except Exception as exc:
            # A compiled package can exist while its native CTranslate2 DLL is absent.
            # Preserve the loader detail so the user can distinguish a normal build
            # from a broken AI package instead of seeing a misleading generic message.
            detail = f"faster-whisper / ctranslate2 ({type(exc).__name__}: {exc})"
            return "missing_dependency:" + detail
        return ""

    def is_installed(self) -> bool:
        return self.model_dir.exists() and any(self.model_dir.rglob("model.bin"))

    def _load(self):
        err = self.dependency_error()
        if err:
            # Keep the actual import/DLL loader exception for the UI and crash diagnostics.
            _prefix, _sep, detail = err.partition(":")
            raise AIError("missing_dependency", detail or err)
        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise AIError("missing_dependency", f"{type(exc).__name__}: {exc}") from exc

        try:
            self.model_dir.mkdir(parents=True, exist_ok=True)
            return WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                download_root=str(self.model_dir),
            )
        except Exception as exc:
            raise AIError("model_failed", f"{type(exc).__name__}: {exc}") from exc

    def install_model(self, progress=None, cancel=None):
        _tick(progress, 10)
        self._load()  # downloads on first use
        _tick(progress, 100)
        return self.model_dir

    def analyze(self, clip, params, progress=None, cancel=None):
        from video_studio_ffmpeg import decode_pcm_mono

        self._need_clip(clip, ("audio", "video"))
        ff = self._ffmpeg(params)
        start, length = _clip_span(clip)
        x = decode_pcm_mono(ff, clip.source_path, rate=16000, max_seconds=7200.0, start=start, duration=length)
        if x is None:
            raise AIError("decode_failed")
        _tick(progress, 10)
        model = self._load()
        _tick(progress, 25)
        lang = params.get("language") or None
        segments, info = model.transcribe(x, language=lang, vad_filter=True, beam_size=5)
        out: List[Dict[str, Any]] = []
        total = max(0.1, len(x) / 16000.0)
        for seg in segments:
            if _cancelled(cancel):
                raise AIError("cancelled")
            text = (seg.text or "").strip()
            if text:
                out.append({"start": float(seg.start), "end": float(seg.end), "text": text})
            _tick(progress, 25 + 74.0 * min(1.0, float(seg.end) / total))
        if not out:
            raise AIError("no_speech")
        return {"ok": True, "segments": out, "language": getattr(info, "language", "")}

    def apply(self, project, clip, result):
        return captions_to_timeline(project, clip, result["segments"])


def captions_to_timeline(project: VideoStudioProject, clip: Optional[TimelineClip], segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create text clips (one per caption line) on an 'AI Subtitles' text track."""
    base = clip.timeline_start if clip else 0.0
    track = next((t for t in project.tracks if t.track_type == "text" and t.name == "AI Subtitles" and not t.locked), None)
    if track is None:
        track = project.add_track("text", "AI Subtitles")
    else:
        project.push_undo_snapshot()
    canvas_h = project.canvas_size[1]
    size = max(28, int(canvas_h * 0.055))
    added = 0
    for seg in segments:
        lines = split_caption(seg["text"])
        t0 = base + _source_offset_to_timeline(clip, seg["start"]) if clip else base + float(seg["start"])
        t1 = base + _source_offset_to_timeline(clip, seg["end"]) if clip else base + float(seg["end"])
        piece = (t1 - t0) / len(lines)
        for i, line in enumerate(lines):
            c = TimelineClip(
                name=f"AI Caption {added + 1}",
                clip_type="text",
                timeline_start=round(t0 + i * piece, 3),
                duration=max(0.4, round(piece, 3)),
                pos_y=canvas_h * 0.36,
                text_style=TextStyleSettings(text=line, font_size=size, stroke_width=3, bg_enabled=True, bg_opacity=55.0),
            )
            c.ai_metadata["caption"] = True
            if clip is not None:
                c.ai_metadata["transcript_source_clip_id"] = clip.id
                c.ai_metadata["transcript_timeline_start"] = round(t0, 3)
                c.ai_metadata["transcript_timeline_end"] = round(t1, 3)
            track.clips.append(c)
            added += 1
    track.clips.sort(key=lambda x: x.timeline_start)
    return {"ok": added > 0, "reason": "" if added else "no_speech", "generated_captions": added}


# ---------------------------------------------------------------------------
# 5) Smart cutout (ONNX, optional)
# ---------------------------------------------------------------------------
CUTOUT_MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"  # U2-Net (Apache-2.0)
CUTOUT_MODEL_FILE = "u2net_human_seg.onnx"
MASK_FPS = 15.0


def download_file(url: str, dest: Path, min_bytes: int, progress: Progress = None, cancel: Cancel = None) -> None:
    if not url.lower().startswith("https://"):
        raise AIError("download_failed", "https only")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HMZVideoStudioPro"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(part, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while True:
                if _cancelled(cancel):
                    raise AIError("cancelled")
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
                got += len(chunk)
                if total:
                    _tick(progress, 100.0 * got / total)
        if part.stat().st_size < min_bytes:
            raise AIError("download_failed", "file too small")
        os.replace(part, dest)
    except AIError:
        part.unlink(missing_ok=True)
        raise
    except Exception as exc:
        part.unlink(missing_ok=True)
        raise AIError("download_failed", str(exc))


def segment_frame(session: Any, frame_bgr: np.ndarray) -> np.ndarray:
    """Run a salient-object/human-segmentation ONNX model; returns float mask 0..1 at model size."""
    import cv2

    inp = session.get_inputs()[0]
    shp = inp.shape
    size = int(shp[2]) if isinstance(shp[2], int) and shp[2] > 0 else 320
    rgb = cv2.cvtColor(cv2.resize(frame_bgr, (size, size), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    blob = np.transpose(rgb, (2, 0, 1))[None].astype(np.float32)
    out = session.run(None, {inp.name: blob})[0]
    m = np.squeeze(out).astype(np.float32)
    if m.ndim != 2:
        m = m.reshape(size, size)
    if m.min() < -0.01 or m.max() > 1.01:
        m = 1.0 / (1.0 + np.exp(-m))
    return np.clip(m, 0.0, 1.0)


def write_masks(
    session: Any,
    video_path: str,
    start: float,
    duration: float,
    out_dir: Path,
    is_image: bool,
    progress: Progress = None,
    cancel: Cancel = None,
) -> Dict[str, Any]:
    import cv2

    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("m*.png"):
        old.unlink(missing_ok=True)

    def save(i: int, m: np.ndarray) -> None:
        ok, buf = cv2.imencode(".png", (m * 255.0).astype(np.uint8))
        if ok:
            buf.tofile(str(out_dir / f"m{i:05d}.png"))

    if is_image:
        data = np.fromfile(video_path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise AIError("decode_failed")
        save(0, segment_frame(session, img))
        return {"dir": str(out_dir), "fps": 1.0, "start": 0.0, "count": 1}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise AIError("decode_failed")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, int(round(fps / MASK_FPS)))
        eff_fps = fps / step
        cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
        total = max(1, int(duration * eff_fps))
        prev_mask: Optional[np.ndarray] = None
        prev_gray: Optional[np.ndarray] = None
        n = 0
        frame_no = 0
        while n < total:
            if _cancelled(cancel):
                raise AIError("cancelled")
            if not cap.grab():
                break
            if frame_no % step == 0:
                ok, fr = cap.retrieve()
                if not ok:
                    break
                m = segment_frame(session, fr)
                gray = cv2.cvtColor(cv2.resize(fr, (m.shape[1], m.shape[0])), cv2.COLOR_BGR2GRAY)
                # Warp the previous mask with optical flow before temporal blending;
                # blending unwarped masks creates visible trails on moving subjects.
                if prev_mask is not None and prev_gray is not None and prev_gray.shape == gray.shape:
                    flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                    yy, xx = np.mgrid[0:m.shape[0], 0:m.shape[1]].astype(np.float32)
                    warped = cv2.remap(prev_mask, xx-flow[..., 0], yy-flow[..., 1], cv2.INTER_LINEAR,
                                       borderMode=cv2.BORDER_REPLICATE)
                    m = 0.72 * m + 0.28 * warped
                # Edge-aware refinement where available, with a bilateral fallback.
                try:
                    if hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "guidedFilter"):
                        m = cv2.ximgproc.guidedFilter(gray, m.astype(np.float32), 5, 1e-3)
                    else:
                        m = cv2.bilateralFilter(m.astype(np.float32), 5, 0.08, 5)
                except Exception:
                    m = cv2.GaussianBlur(m.astype(np.float32), (3, 3), 0.6)
                m = cv2.morphologyEx(np.clip(m, 0.0, 1.0), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
                prev_mask = m.astype(np.float32)
                prev_gray = gray
                save(n, prev_mask)
                n += 1
                _tick(progress, 100.0 * n / total)
            frame_no += 1
    finally:
        cap.release()
    if n == 0:
        raise AIError("decode_failed")
    return {"dir": str(out_dir), "fps": eff_fps, "start": start, "count": n}


class AutoCutoutPlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_auto_cutout",
        name_ar="عزل الخلفية الذكي للأشخاص (Cutout)",
        name_en="Smart Person Cutout",
        desc_ar="يفصل الشخص عن الخلفية بدون شاشة خضراء باستخدام نموذج ONNX محلي (~170 MB يُحمَّل مرة واحدة). يعمل على الفيديو والصور. الجودة جيدة للقطات واضحة وإضاءة جيدة، لكن الحواف مع الشعر والحركة السريعة أقل دقة من خدمات السحابة. يُعالَج الفيديو بمعدل 15 قناع/ثانية ويحتاج وقتاً (يعتمد على جهازك).",
        desc_en="Separates a person from the background without a green screen using a local ONNX model (~170 MB, downloaded once). Works on video and images. Good on clear, well-lit shots; hair edges and fast motion are less precise than cloud services. Video is masked at 15 masks/second and takes time (depends on your PC).",
        category="video",
        model_filename=CUTOUT_MODEL_FILE,
        approx_size_mb=170,
        needs_clip="video",
    )

    def ensure_runtime(self, progress=None, cancel=None) -> None:
        from video_studio_ai_runtime import install_runtime
        install_runtime(progress, cancel)

    def dependency_error(self) -> str:
        try:
            from video_studio_ai_runtime import activate_runtime
            activate_runtime()
            import onnxruntime  # noqa: F401
        except Exception:
            return "missing_dependency:onnxruntime"
        return ""

    def is_installed(self) -> bool:
        return self.model_path.exists() and self.model_path.stat().st_size > 5_000_000

    @property
    def model_path(self) -> Path:
        return self.models_dir / CUTOUT_MODEL_FILE

    def install_model(self, progress=None, cancel=None):
        download_file(CUTOUT_MODEL_URL, self.model_path, 5_000_000, progress, cancel)
        return self.model_path

    def analyze(self, clip, params, progress=None, cancel=None):
        self._need_clip(clip, ("video", "image"))
        if self.dependency_error():
            raise AIError("missing_dependency", "onnxruntime")
        if not self.is_installed():
            raise AIError("model_missing")
        import onnxruntime as ort

        try:
            session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
        except Exception as exc:
            raise AIError("model_failed", str(exc))
        work = Path(params.get("work_dir") or tempfile.gettempdir())
        start, length = _clip_span(clip)
        meta = write_masks(session, clip.source_path, start, length, work / f"cutout_{clip.id}", clip.clip_type == "image", progress, cancel)
        return {"ok": True, "meta": meta}

    def apply(self, project, clip, result):
        project.push_undo_snapshot()
        clip.ai_metadata["cutout"] = result["meta"]
        return {"ok": True, "masks": result["meta"]["count"]}


# ---------------------------------------------------------------------------
def track_roi(video_path: str, start: float, duration: float, roi: Tuple[float, float, float, float],
              sample_fps: float = 8.0, cancel: Cancel = None) -> List[Tuple[float, float, float]]:
    """Track a normalized ROI with forward/backward-checked pyramidal flow.

    Uses a robust partial-affine transform when enough features survive, re-detects
    features in a bounded search window after temporary occlusion, and stops rather
    than emitting an unbounded drifting path when the target is truly lost.
    """
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise AIError("decode_failed")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
    if not np.isfinite(fps) or fps < 1.0:
        fps = 25.0
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000.0)
    ok, first = cap.read()
    if not ok or first is None:
        cap.release()
        raise AIError("decode_failed")
    h, w = first.shape[:2]
    x, y, rw, rh = roi
    x0, y0 = int(max(0, min(w-2, x*w))), int(max(0, min(h-2, y*h)))
    x1 = int(max(x0+2, min(w, (x+rw)*w)))
    y1 = int(max(y0+2, min(h, (y+rh)*h)))
    box_w, box_h = max(4, x1-x0), max(4, y1-y0)
    prev = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    center = np.array([(x0+x1)/2.0, (y0+y1)/2.0], dtype=np.float32)
    feature_mask = np.zeros((h, w), np.uint8)
    feature_mask[y0:y1, x0:x1] = 255
    points = cv2.goodFeaturesToTrack(prev, maxCorners=120, qualityLevel=.01, minDistance=4, mask=feature_mask)
    if points is None or len(points) < 3:
        cap.release()
        raise AIError("tracking_features_not_found")
    out = [(float(start), float(center[0]/w), float(center[1]/h))]
    step = max(1, int(round(fps/max(1.0, sample_fps))))
    velocity = np.zeros(2, dtype=np.float32)
    lost_frames = 0
    max_lost = max(1, int(fps * 0.65))
    frame_no = 1
    try:
        while frame_no / fps <= duration:
            if _cancelled(cancel):
                raise AIError("cancelled")
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            nxt, status_f, _ = cv2.calcOpticalFlowPyrLK(
                prev, gray, points, None, winSize=(21, 21), maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 25, 0.01))
            accepted_old = accepted_new = None
            if nxt is not None and status_f is not None:
                back, status_b, _ = cv2.calcOpticalFlowPyrLK(
                    gray, prev, nxt, None, winSize=(21, 21), maxLevel=3,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.02))
                if back is not None and status_b is not None:
                    fb = np.linalg.norm(points.reshape(-1, 2) - back.reshape(-1, 2), axis=1)
                    good = (status_f.reshape(-1) == 1) & (status_b.reshape(-1) == 1) & (fb < 1.6)
                    accepted_old = points.reshape(-1, 2)[good]
                    accepted_new = nxt.reshape(-1, 2)[good]

            tracked = False
            if accepted_new is not None and len(accepted_new) >= 4:
                affine, inliers = cv2.estimateAffinePartial2D(
                    accepted_old, accepted_new, method=cv2.RANSAC,
                    ransacReprojThreshold=3.0, maxIters=200, confidence=0.98, refineIters=8)
                if affine is not None and inliers is not None and int(inliers.sum()) >= 3:
                    new_center = cv2.transform(center.reshape(1, 1, 2), affine).reshape(2)
                else:
                    delta = np.median(accepted_new - accepted_old, axis=0)
                    new_center = center + delta
                velocity = 0.65 * velocity + 0.35 * (new_center - center)
                center = new_center.astype(np.float32)
                points = accepted_new.reshape(-1, 1, 2).astype(np.float32)
                lost_frames = 0
                tracked = True

            if not tracked:
                lost_frames += 1
                center = center + velocity
                # Reacquire corners in a generous but bounded window around the predicted box.
                radius_x, radius_y = int(box_w * 1.8), int(box_h * 1.8)
                cx, cy = int(center[0]), int(center[1])
                sx0, sy0 = max(0, cx-radius_x), max(0, cy-radius_y)
                sx1, sy1 = min(w, cx+radius_x), min(h, cy+radius_y)
                search = np.zeros((h, w), np.uint8)
                if sx1-sx0 >= 4 and sy1-sy0 >= 4:
                    search[sy0:sy1, sx0:sx1] = 255
                    detected = cv2.goodFeaturesToTrack(gray, maxCorners=100, qualityLevel=.012, minDistance=4, mask=search)
                else:
                    detected = None
                if detected is not None and len(detected) >= 4:
                    points = detected.astype(np.float32)
                    # Re-anchor to the strongest local feature cloud to recover from occlusion.
                    cloud = points.reshape(-1, 2)
                    center = np.median(cloud, axis=0).astype(np.float32)
                    lost_frames = 0
                elif lost_frames > max_lost:
                    break

            center[0] = np.clip(center[0], box_w/2, max(box_w/2, w-box_w/2))
            center[1] = np.clip(center[1], box_h/2, max(box_h/2, h-box_h/2))
            prev = gray
            if frame_no % step == 0:
                out.append((float(start + frame_no/fps), float(center[0]/w), float(center[1]/h)))
            frame_no += 1
    finally:
        cap.release()
    return out


class MotionTrackingPlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_motion_tracking",
        name_ar="تتبع الحركة وربط النص/الملصق", name_en="Motion Tracking — Attach Overlay",
        desc_ar="يتتبع منطقة تحددها بإحداثيات نسبية ويربط طبقة نص/ملصق بمركزها عبر إطارات مفتاحية.",
        desc_en="Tracks a user-specified normalized ROI and applies position keyframes to a selected text/sticker overlay.",
        category="timeline", needs_clip="video",
    )

    def analyze(self, clip, params, progress=None, cancel=None):
        self._need_clip(clip, ("video",))
        roi = params.get("roi", (0.25, 0.25, 0.25, 0.25))
        samples = track_roi(clip.source_path, clip.source_in, clip.duration, tuple(map(float, roi)),
                            sample_fps=float(params.get("sample_fps", 8.0)), cancel=cancel)
        if len(samples) < 2:
            raise AIError("tracking_failed")
        _tick(progress, 100)
        return {"ok": True, "samples": smooth_tracking_path(samples, 2),
                "target_overlay_id": str(params.get("target_overlay_id", ""))}

    def apply(self, project, clip, result):
        target_id = result.get("target_overlay_id")
        target = project.find_clip(target_id)[1] if target_id and project.find_clip(target_id) else None
        if target is None:
            project.push_undo_snapshot()
            clip.ai_metadata["motion_tracking"] = {"samples": result["samples"], "version": 1}
            return {"ok": True, "samples": len(result["samples"]), "stored_on_source": True}
        project.push_undo_snapshot()
        w, h = project.canvas_size
        speed = max(0.1, float(clip.speed or 1.0))
        target.keyframes["pos_x"] = [Keyframe(time_offset=max(0.0, clip.timeline_start + (t-clip.source_in)/speed - target.timeline_start), value=(x-.5)*w) for t,x,y in result["samples"]]
        target.keyframes["pos_y"] = [Keyframe(time_offset=max(0.0, clip.timeline_start + (t-clip.source_in)/speed - target.timeline_start), value=(y-.5)*h) for t,x,y in result["samples"]]
        return {"ok": True, "samples": len(result["samples"]), "target_overlay_id": target.id}


class AutoReframePlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_auto_reframe",
        name_ar="إعادة تأطير تلقائية (Auto Reframe)",
        name_en="Auto Reframe / Subject Follow",
        desc_ar="يتتبع مركز الاهتمام محليًا ويعيد قص الفيديو ليتناسب مع نسبة أبعاد المشروع مع متابعة الحركة.",
        desc_en="Tracks the salient subject locally and crops the source to the project aspect ratio while following its motion.",
        category="timeline",
        needs_clip="video",
    )

    def analyze(self, clip, params, progress=None, cancel=None):
        self._need_clip(clip, ("video",))
        start, length = _clip_span(clip)
        samples = track_salient_subject(clip.source_path, start, length,
                                        sample_fps=float(params.get("sample_fps", 6.0)), cancel=cancel)
        if len(samples) < 2:
            raise AIError("tracking_failed")
        samples = smooth_tracking_path(samples, radius=int(params.get("smooth_radius", 3)))
        _tick(progress, 100)
        return {"ok": True, "samples": samples}

    def apply(self, project, clip, result):
        project.push_undo_snapshot()
        clip.ai_metadata["auto_reframe"] = {"enabled": True, "samples": result["samples"], "version": 1}
        return {"ok": True, "samples": len(result["samples"])}


# Silence remover (CapCut-style "remove silence / dead air")
# ---------------------------------------------------------------------------
def detect_silences(samples: np.ndarray, rate: int, min_len: float = 0.45, pad: float = 0.06, floor_db: float = -55.0, rel_db: float = 28.0) -> List[Tuple[float, float]]:
    """(start, end) seconds of silent stretches. The threshold follows the clip's own loudness (so quiet and loud
    recordings both work), `min_len` ignores natural pauses and `pad` keeps a little air around the speech."""
    if samples is None or len(samples) < rate // 5:
        return []
    hop = max(1, int(rate * 0.02))
    n = len(samples) // hop
    if n < 3:
        return []
    frames = samples[: n * hop].reshape(n, hop).astype(np.float64)
    db = 20.0 * np.log10(np.sqrt((frames ** 2).mean(axis=1)) + 1e-9)
    thr = max(floor_db, float(np.percentile(db, 95)) - rel_db)
    quiet = db < thr
    spans: List[Tuple[float, float]] = []
    i = 0
    while i < n:
        if not quiet[i]:
            i += 1
            continue
        j = i
        while j < n and quiet[j]:
            j += 1
        a, b = i * hop / rate + pad, j * hop / rate - pad
        if b - a >= min_len:
            spans.append((round(a, 3), round(b, 3)))
        i = j
    return spans


class SilenceRemoverPlugin(BaseAIPlugin):
    descriptor = AIPluginDescriptor(
        plugin_id="ai_silence_remover",
        name_ar="حذف الصمت تلقائياً (Dead Air)",
        name_en="Silence Remover (Dead Air)",
        desc_ar="يكتشف فترات الصمت الطويلة في المقطع المحدد (كلام/بودكاست/فيديو) ويحذفها ويضم ما بعدها تلقائياً. يعمل بدون تحميل نماذج ويمكن التراجع بـ Ctrl+Z. إن كان الصوت مفصولاً عن الفيديو فطبّقه على مقطع الصوت.",
        desc_en="Finds long silent stretches in the selected clip (speech / podcast / video) and cuts them out, closing the gaps. No model download; undo with Ctrl+Z. If the audio is detached from the video, apply it to the audio clip.",
        category="timeline",
        needs_clip="audio",
    )

    def analyze(self, clip, params, progress=None, cancel=None):
        from video_studio_ffmpeg import decode_pcm_mono

        self._need_clip(clip, ("audio", "video"))
        ff = self._ffmpeg(params)
        start, length = _clip_span(clip)
        _tick(progress, 10)
        x = decode_pcm_mono(ff, clip.source_path, rate=16000, max_seconds=3600.0, start=start, duration=length)
        if x is None:
            raise AIError("decode_failed")
        _tick(progress, 70)
        spans = detect_silences(x, 16000)
        if not spans:
            raise AIError("no_silence")
        out = [(self._src_to_timeline(clip, start + a), self._src_to_timeline(clip, start + b)) for a, b in spans]
        _tick(progress, 100)
        return {"ok": True, "spans": out}

    def apply(self, project, clip, result):
        """Cut every silent span (latest first, so earlier times stay valid) and ripple the gap closed."""
        removed = 0
        project.push_undo_snapshot()
        cur_id = clip.id
        for a, b in sorted(result["spans"], reverse=True):
            found = project.find_clip(cur_id)
            if not found:
                break
            _t, cur = found
            a, b = max(a, cur.timeline_start), min(b, cur.timeline_end)
            if b - a < 0.1:
                continue
            doomed = None
            if b < cur.timeline_end - 0.05:
                res = project.split_clip_at(cur.id, split_time=round(b, 3))
                if not res:
                    continue
                cur = res[0]
            if a > cur.timeline_start + 0.05:
                res = project.split_clip_at(cur.id, split_time=round(a, 3))
                if not res:
                    continue
                cur, doomed = res[0], res[1]
            else:
                doomed = cur  # silence at the very start of what is left: drop that piece itself
            seam_time = doomed.timeline_start
            if project.ripple_delete_clip(doomed.id):
                removed += 1
                # Tiny 35 ms edge fades suppress clicks introduced by hard silence cuts.
                for trk in project.tracks:
                    if trk.track_type not in ("audio", "video"):
                        continue
                    previous = max((c for c in trk.clips if c.timeline_end <= seam_time + 0.02), key=lambda c: c.timeline_end, default=None)
                    following = min((c for c in trk.clips if c.timeline_start >= seam_time - 0.02), key=lambda c: c.timeline_start, default=None)
                    if previous is not None:
                        previous.fade_out = max(float(previous.fade_out), min(0.035, previous.duration / 3.0))
                    if following is not None:
                        following.fade_in = max(float(following.fade_in), min(0.035, following.duration / 3.0))
            cur_id = cur.id if doomed is not cur else cur_id
        return {"ok": removed > 0, "reason": "" if removed else "no_silence", "removed": removed}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class AIPluginRegistry:
    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = get_ai_models_dir(models_dir)
        self.work_dir = self.models_dir.parent / "ai_work"
        self._plugins: Dict[str, BaseAIPlugin] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        for cls in (
            AutoBeatDetectionPlugin,
            AutoSceneSplitPlugin,
            AudioNoiseReductionPlugin,
            SilenceRemoverPlugin,
            WhisperAutoCaptionsPlugin,
            AutoReframePlugin,
            MotionTrackingPlugin,
            AutoCutoutPlugin,
        ):
            instance = cls(models_dir=self.models_dir)
            self._plugins[instance.descriptor.plugin_id] = instance

    def register_plugin(self, plugin: BaseAIPlugin) -> None:
        self._plugins[plugin.descriptor.plugin_id] = plugin

    def list_plugins(self) -> List[BaseAIPlugin]:
        return list(self._plugins.values())

    def get_plugin(self, plugin_id: str) -> Optional[BaseAIPlugin]:
        return self._plugins.get(plugin_id)

    def params(self, ffmpeg: Optional[str]) -> Dict[str, Any]:
        self.work_dir.mkdir(parents=True, exist_ok=True)
        return {"ffmpeg": ffmpeg, "work_dir": str(self.work_dir)}
