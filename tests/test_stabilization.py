import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from video_studio_stabilization import (
    _load_cache,
    analyze_video_stabilization,
    apply_stabilization_frame,
    is_stabilization_ready,
    stabilization_cache_path,
)


class TestVideoStabilization(unittest.TestCase):
    def _make_shaky_clip(self, path: Path, frames: int = 48) -> None:
        width, height = 320, 240
        rng = np.random.default_rng(17)
        background = np.zeros((height, width, 3), dtype=np.uint8)
        for _ in range(140):
            x, y = int(rng.integers(5, width - 5)), int(rng.integers(5, height - 5))
            color = tuple(int(v) for v in rng.integers(70, 255, size=3))
            cv2.circle(background, (x, y), int(rng.integers(2, 7)), color, -1)
        for x in range(20, width, 40):
            cv2.line(background, (x, 0), (x, height - 1), (100, 100, 100), 1)
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20.0, (width, height))
        if not writer.isOpened():
            self.skipTest("OpenCV MJPG VideoWriter is unavailable in this environment")
        try:
            for i in range(frames):
                dx = int(round(7 * np.sin(i * 0.28)))
                dy = int(round(5 * np.cos(i * 0.21)))
                matrix = np.float32([[1, 0, dx], [0, 1, dy]])
                frame = cv2.warpAffine(background, matrix, (width, height), borderMode=cv2.BORDER_REFLECT)
                writer.write(frame)
        finally:
            writer.release()


    @staticmethod
    def _mean_adjacent_feature_motion(frames):
        values = []
        for before, after in zip(frames, frames[1:]):
            prev = cv2.cvtColor(before, cv2.COLOR_BGR2GRAY)
            curr = cv2.cvtColor(after, cv2.COLOR_BGR2GRAY)
            points = cv2.goodFeaturesToTrack(prev, maxCorners=300, qualityLevel=0.01, minDistance=12)
            if points is None or len(points) < 8:
                continue
            moved, status, _ = cv2.calcOpticalFlowPyrLK(prev, curr, points, None)
            if moved is None or status is None:
                continue
            valid = status.reshape(-1) == 1
            displacement = moved[valid].reshape(-1, 2) - points[valid].reshape(-1, 2)
            if len(displacement):
                values.append(float(np.median(np.linalg.norm(displacement, axis=1))))
        return float(np.mean(values)) if values else 0.0

    def test_analyzer_writes_reusable_cache_and_corrects_frames(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "shaky.avi"
            cache_dir = root / "cache"
            self._make_shaky_clip(source)

            capture = cv2.VideoCapture(str(source))
            ok, first = capture.read()
            self.assertTrue(ok)
            original_frames = [first]
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                original_frames.append(frame)
            capture.release()
            # The public function must be a no-op until the analysis cache exists.
            unchanged = apply_stabilization_frame(first, str(source), 0.5, cache_dir)
            self.assertTrue(np.array_equal(first, unchanged))

            progress = []
            cache_path = stabilization_cache_path(str(source), cache_dir)
            result = analyze_video_stabilization(
                str(source), cache_path, progress_callback=progress.append, smoothing_radius=8,
            )

            self.assertEqual(result, cache_path)
            self.assertTrue(is_stabilization_ready(str(source), cache_dir))
            self.assertTrue(cache_path.is_file())
            self.assertEqual(progress[-1], 100)

            cached = _load_cache(str(source), cache_dir)
            self.assertIsNotNone(cached)
            corrections, fps, zoom = cached
            self.assertEqual(len(corrections), 48)
            self.assertGreater(fps, 0)
            self.assertGreater(zoom, 1.0)  # actual shake creates a measured crop; static footage would stay at 1.0
            self.assertLessEqual(zoom, 1.16)
            self.assertGreater(float(np.max(np.abs(corrections))), 0.001)

            corrected = apply_stabilization_frame(first, str(source), 0.5, cache_dir)
            self.assertEqual(corrected.shape, first.shape)
            self.assertEqual(corrected.dtype, first.dtype)
            self.assertFalse(np.array_equal(corrected, first))

            corrected_frames = [
                apply_stabilization_frame(frame, str(source), index / fps, cache_dir)
                for index, frame in enumerate(original_frames)
            ]
            raw_motion = self._mean_adjacent_feature_motion(original_frames)
            stabilized_motion = self._mean_adjacent_feature_motion(corrected_frames)
            self.assertGreater(raw_motion, 0.5)
            self.assertLess(stabilized_motion, raw_motion * 0.75)

            # A second analyzer call reuses the existing cache instead of rewriting it.
            before = cache_path.stat().st_mtime_ns
            again = analyze_video_stabilization(str(source), cache_path)
            self.assertEqual(again, cache_path)
            self.assertEqual(cache_path.stat().st_mtime_ns, before)

    def test_cancelled_analysis_does_not_publish_partial_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "shaky.avi"
            cache_path = root / "cache" / "cache.npz"
            self._make_shaky_clip(source, frames=12)
            result = analyze_video_stabilization(str(source), cache_path, cancel_check=lambda: True)
            self.assertIsNone(result)
            self.assertFalse(cache_path.exists())

    def test_missing_source_is_reported_without_exception(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "missing.mp4"
            self.assertIsNone(analyze_video_stabilization(str(missing)))
            self.assertFalse(is_stabilization_ready(str(missing)))


if __name__ == "__main__":
    unittest.main()
