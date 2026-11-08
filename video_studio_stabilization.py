# -*- coding: utf-8 -*-
"""OpenCV feature-based video stabilization with a persistent per-source cache.

The analyzer stores normalized camera-motion corrections rather than re-encoding the
source.  Rendering can therefore apply stabilization to original frames at full
resolution during both preview and final export.
"""
from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Optional

import cv2
import numpy as np

ALGORITHM_VERSION = 1
ANALYSIS_MAX_WIDTH = 640
SMOOTHING_RADIUS = 18
_CACHE_LOCK = threading.RLock()
_CACHE: "OrderedDict[str, tuple[int, np.ndarray, float, float]]" = OrderedDict()
_CACHE_MAX = 12


def _default_cache_dir() -> Path:
    root = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(root) / "HMZVideoStudioPro" / "stabilization"


def source_fingerprint(source_path: str) -> str:
    p = Path(source_path).expanduser().resolve()
    st = p.stat()
    raw = f"{p}|{st.st_size}|{st.st_mtime_ns}|{ALGORITHM_VERSION}"
    return hashlib.sha256(raw.encode("utf-8", errors="surrogatepass")).hexdigest()


def stabilization_cache_path(source_path: str, cache_dir: Optional[Path] = None) -> Path:
    return (Path(cache_dir) if cache_dir is not None else _default_cache_dir()) / f"{source_fingerprint(source_path)}.npz"


def is_stabilization_ready(source_path: str, cache_dir: Optional[Path] = None) -> bool:
    try:
        path = stabilization_cache_path(source_path, cache_dir)
        if not path.is_file() or path.stat().st_size < 128:
            return False
        with np.load(path, allow_pickle=False) as data:
            return int(data["version"][0]) == ALGORITHM_VERSION and len(data["corrections"]) > 1
    except Exception:
        return False


def _smooth(values: np.ndarray, radius: int) -> np.ndarray:
    if len(values) < 3 or radius <= 0:
        return values.copy()
    radius = min(radius, max(1, (len(values) - 1) // 2))
    kernel = np.ones(2 * radius + 1, dtype=np.float64)
    kernel /= kernel.sum()
    padded = np.pad(values, (radius, radius), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def analyze_video_stabilization(
    source_path: str,
    cache_path: Optional[Path] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    smoothing_radius: int = SMOOTHING_RADIUS,
) -> Optional[Path]:
    """Analyze camera movement and atomically save normalized corrections.

    Returns the cache path, or None for unsupported/invalid media. This function is
    deliberately headless so it can run in a worker thread and be tested directly.
    """
    source = Path(source_path)
    if not source.is_file():
        return None
    target = Path(cache_path) if cache_path else stabilization_cache_path(str(source))
    if is_stabilization_ready(str(source), target.parent) and target.exists():
        return target

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        cap.release()
        return None
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        if not np.isfinite(fps) or fps < 1 or fps > 480:
            fps = 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        source_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        source_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        ok, first = cap.read()
        if not ok or first is None or source_w < 32 or source_h < 32:
            return None
        analysis_scale = min(1.0, ANALYSIS_MAX_WIDTH / float(source_w))
        analysis_w = max(32, int(round(source_w * analysis_scale)))
        analysis_h = max(32, int(round(source_h * analysis_scale)))
        prev = cv2.cvtColor(cv2.resize(first, (analysis_w, analysis_h)), cv2.COLOR_BGR2GRAY)

        motions = [[0.0, 0.0, 0.0]]
        processed = 1
        while True:
            if cancel_check and cancel_check():
                return None
            ok, frame = cap.read()
            if not ok or frame is None:
                break
            gray = cv2.cvtColor(cv2.resize(frame, (analysis_w, analysis_h)), cv2.COLOR_BGR2GRAY)
            points = cv2.goodFeaturesToTrack(
                prev, maxCorners=300, qualityLevel=0.01, minDistance=12, blockSize=3,
            )
            dx = dy = angle = 0.0
            if points is not None and len(points) >= 8:
                moved, status, _err = cv2.calcOpticalFlowPyrLK(
                    prev, gray, points, None,
                    winSize=(21, 21), maxLevel=3,
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
                )
                if moved is not None and status is not None:
                    good_old = points[status.reshape(-1) == 1].reshape(-1, 2)
                    good_new = moved[status.reshape(-1) == 1].reshape(-1, 2)
                    if len(good_old) >= 8:
                        affine, inliers = cv2.estimateAffinePartial2D(
                            good_old, good_new, method=cv2.RANSAC,
                            ransacReprojThreshold=2.5, maxIters=250,
                            confidence=0.99, refineIters=10,
                        )
                        if affine is not None and inliers is not None and int(inliers.sum()) >= 6:
                            dx = float(affine[0, 2])
                            dy = float(affine[1, 2])
                            angle = float(np.degrees(np.arctan2(affine[1, 0], affine[0, 0])))
            motions.append([dx, dy, angle])
            prev = gray
            processed += 1
            if progress_callback and frame_count > 0 and processed % 8 == 0:
                progress_callback(min(95, int(processed * 95 / frame_count)))

        if len(motions) < 2:
            return None
        motion = np.asarray(motions, dtype=np.float64)
        trajectory = np.cumsum(motion, axis=0)
        smooth = np.column_stack([_smooth(trajectory[:, i], smoothing_radius) for i in range(3)])
        correction = smooth - trajectory
        # Store displacement as a fraction of the source dimensions. That lets the
        # same correction work on a 25%-scale preview or a full-resolution export.
        correction[:, 0] /= float(analysis_w)
        correction[:, 1] /= float(analysis_h)
        # Guard against pathological optical-flow jumps; these are almost always
        # scene cuts or a feature-tracking failure, not real camera motion.
        correction[:, 0] = np.clip(correction[:, 0], -0.18, 0.18)
        correction[:, 1] = np.clip(correction[:, 1], -0.18, 0.18)
        correction[:, 2] = np.clip(correction[:, 2], -12.0, 12.0)
        max_shift = float(np.max(np.sqrt(correction[:, 0] ** 2 + correction[:, 1] ** 2)))
        zoom = float(min(1.16, max(1.0, 1.0 + max_shift * 1.35)))

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.stem + ".tmp.npz")
        try:
            np.savez_compressed(
                tmp,
                version=np.asarray([ALGORITHM_VERSION], dtype=np.int32),
                fps=np.asarray([fps], dtype=np.float64),
                frame_count=np.asarray([len(correction)], dtype=np.int64),
                source_width=np.asarray([source_w], dtype=np.int32),
                source_height=np.asarray([source_h], dtype=np.int32),
                zoom=np.asarray([zoom], dtype=np.float32),
                corrections=correction.astype(np.float32),
            )
            os.replace(tmp, target)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        if progress_callback:
            progress_callback(100)
        with _CACHE_LOCK:
            _CACHE.pop(str(target), None)
        return target
    finally:
        cap.release()


def _load_cache(source_path: str, cache_dir: Optional[Path] = None) -> Optional[tuple[np.ndarray, float, float]]:
    try:
        target = stabilization_cache_path(source_path, cache_dir)
        stat = target.stat()
        key = str(target)
        with _CACHE_LOCK:
            entry = _CACHE.get(key)
            if entry and entry[0] == stat.st_mtime_ns:
                _CACHE.move_to_end(key)
                return entry[1], entry[2], entry[3]
        with np.load(target, allow_pickle=False) as data:
            if int(data["version"][0]) != ALGORITHM_VERSION:
                return None
            corrections = np.asarray(data["corrections"], dtype=np.float32)
            fps = float(data["fps"][0])
            zoom = float(data["zoom"][0])
        with _CACHE_LOCK:
            _CACHE[key] = (stat.st_mtime_ns, corrections, fps, zoom)
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
        return corrections, fps, zoom
    except Exception:
        return None


def apply_stabilization_frame(
    frame: np.ndarray, source_path: str, source_time_sec: float, cache_dir: Optional[Path] = None,
) -> np.ndarray:
    """Apply the cached transform for the requested source timestamp; no-op until ready."""
    if frame is None or not source_path:
        return frame
    cached = _load_cache(source_path, cache_dir)
    if cached is None:
        return frame
    corrections, fps, zoom = cached
    if len(corrections) == 0:
        return frame
    idx_float = max(0.0, source_time_sec) * fps
    idx0 = min(len(corrections) - 1, int(idx_float))
    idx1 = min(len(corrections) - 1, idx0 + 1)
    frac = max(0.0, min(1.0, idx_float - idx0))
    corr = corrections[idx0] * (1.0 - frac) + corrections[idx1] * frac
    h, w = frame.shape[:2]
    dx = float(corr[0]) * w
    dy = float(corr[1]) * h
    angle = float(corr[2])
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle, zoom)
    matrix[0, 2] += dx
    matrix[1, 2] += dy
    return cv2.warpAffine(
        frame, matrix, (w, h), flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
