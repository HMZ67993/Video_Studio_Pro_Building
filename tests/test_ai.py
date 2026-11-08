# -*- coding: utf-8 -*-
"""Real tests for the AI/analysis tools (synthetic signals/videos, real ffmpeg when present)."""
import os
import shutil
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

import video_studio_plugins as ap  # noqa: E402
from video_studio_core import TimelineClip, VideoStudioProject, process_frame_effects  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
RATE = 22050


def click_track(bpm: float, seconds: float, rate: int = RATE) -> np.ndarray:
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.003, int(seconds * rate)).astype(np.float32)
    period = 60.0 / bpm
    t = 0.3
    burst = (np.hanning(900) * rng.normal(0, 0.7, 900)).astype(np.float32)
    while t < seconds - 0.2:
        i = int(t * rate)
        x[i:i + 900] += burst[: len(x[i:i + 900])]
        t += period
    return np.clip(x, -1, 1)


def write_wav(path: Path, x: np.ndarray, rate: int) -> None:
    ap.write_wav_mono(path, x, rate)


class TestBeats(unittest.TestCase):
    def test_tempo_and_grid(self):
        for bpm in (100.0, 128.0):
            info = ap.detect_beats(click_track(bpm, 24.0), RATE)
            self.assertIsNotNone(info)
            self.assertAlmostEqual(info["bpm"], bpm, delta=2.5)
            period = 60.0 / bpm
            truth = [0.3 + k * period for k in range(int(20 / period))]
            hits = sum(1 for t in truth if min(abs(b - t) for b in info["beats"]) < 0.06)
            self.assertGreaterEqual(hits / len(truth), 0.9)

    def test_noise_has_no_rhythm(self):
        x = np.random.default_rng(3).normal(0, 0.1, RATE * 12).astype(np.float32)
        info = ap.detect_beats(x, RATE)
        # white noise must not produce a confident beat grid
        self.assertTrue(info is None or info["confidence"] < 0.3)

    def test_too_short(self):
        self.assertIsNone(ap.detect_beats(np.zeros(1000, np.float32), RATE))


class TestDenoise(unittest.TestCase):
    def test_reduces_steady_noise_keeps_tone(self):
        rate = 44100
        rng = np.random.default_rng(5)
        n = rate * 6
        t = np.arange(n) / rate
        noise = rng.normal(0, 0.03, n).astype(np.float32)
        tone = (0.4 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        tone[: rate * 2] = 0  # first 2 s: noise only
        x = noise + tone
        y = ap.denoise_audio(x, rate, 18.0)
        self.assertEqual(len(y), len(x))
        rms = lambda a: float(np.sqrt(np.mean(a ** 2)))  # noqa: E731
        before, after = rms(x[:rate * 2]), rms(y[:rate * 2])
        self.assertLess(after, before * 0.5)  # >= 6 dB quieter on noise-only part
        seg_in, seg_out = rms(x[rate * 3:rate * 5]), rms(y[rate * 3:rate * 5])
        self.assertGreater(seg_out, seg_in * 0.7)  # tone mostly kept

    def test_cancel(self):
        with self.assertRaises(ap.AIError):
            ap.denoise_audio(np.zeros(44100 * 5, np.float32) + 0.01, 44100, cancel=lambda: True)


def make_scene_video(path: Path) -> None:
    w, h, fps = 160, 90, 10
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    colors = [(200, 40, 40), (40, 200, 40), (40, 40, 200)]
    rng = np.random.default_rng(2)
    for ci, col in enumerate(colors):
        for f in range(30):  # 3 s each
            fr = np.zeros((h, w, 3), np.uint8)
            fr[:] = col
            cv2.circle(fr, (20 + f * 3, 45), 12 + ci * 4, (255, 255, 255), -1)
            fr = np.clip(fr.astype(int) + rng.integers(-6, 6, fr.shape), 0, 255).astype(np.uint8)
            vw.write(fr)
    vw.release()


class TestScenes(unittest.TestCase):
    def test_detects_two_cuts_and_splits(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "scenes.mp4"
            make_scene_video(v)
            cuts = ap.detect_scene_cuts(str(v), 0.0, 9.0)
            self.assertEqual(len(cuts), 2, cuts)
            self.assertAlmostEqual(cuts[0], 3.0, delta=0.4)
            self.assertAlmostEqual(cuts[1], 6.0, delta=0.4)
            proj = VideoStudioProject()
            clip = TimelineClip(name="v", clip_type="video", source_path=str(v), duration=9.0, source_out=9.0)
            proj.add_clip_to_track(proj.tracks[0].id, clip)
            res = ap.AutoSceneSplitPlugin(models_dir=Path(d)).execute(proj, clip, {})
            self.assertTrue(res["ok"])
            self.assertEqual(res["splits"], 2)
            self.assertEqual(len(proj.tracks[0].clips), 3)
            self.assertAlmostEqual(sum(c.duration for c in proj.tracks[0].clips), 9.0, delta=0.05)

    def test_single_scene_reports_none(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "one.mp4"
            vw = cv2.VideoWriter(str(v), cv2.VideoWriter_fourcc(*"mp4v"), 10, (160, 90))
            for _ in range(40):
                vw.write(np.full((90, 160, 3), 90, np.uint8))
            vw.release()
            proj = VideoStudioProject()
            clip = TimelineClip(name="v", clip_type="video", source_path=str(v), duration=4.0, source_out=4.0)
            proj.add_clip_to_track(proj.tracks[0].id, clip)
            res = ap.AutoSceneSplitPlugin(models_dir=Path(d)).execute(proj, clip, {})
            self.assertFalse(res["ok"])
            self.assertEqual(res["reason"], "no_scenes")


@unittest.skipUnless(FFMPEG, "ffmpeg not available")
class TestPluginsWithFfmpeg(unittest.TestCase):
    def test_beat_plugin_end_to_end_with_speed(self):
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "beat.wav"
            write_wav(wav, click_track(120.0, 16.0), RATE)
            proj = VideoStudioProject()
            atrack = proj.add_track("audio", "A")
            clip = TimelineClip(name="m", clip_type="audio", source_path=str(wav), timeline_start=2.0, duration=16.0, source_out=16.0)
            proj.add_clip_to_track(atrack.id, clip)
            plug = ap.AutoBeatDetectionPlugin(models_dir=Path(d))
            res = plug.execute(proj, clip, {"ffmpeg": FFMPEG})
            self.assertTrue(res["ok"], res)
            self.assertAlmostEqual(res["bpm"], 120.0, delta=2.5)
            times = [m.time_sec for m in proj.markers]
            self.assertTrue(all(2.0 <= t <= 18.0 for t in times))
            # first click is at source 0.3 s -> timeline 2.3 s
            self.assertLess(min(abs(t - 2.3) for t in times), 0.06)
            # running again replaces, never duplicates
            plug.execute(proj, clip, {"ffmpeg": FFMPEG})
            self.assertEqual(len(proj.markers), len(times))

    def test_beat_needs_ffmpeg(self):
        proj = VideoStudioProject()
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "a.wav"
            write_wav(wav, click_track(120.0, 8.0), RATE)
            clip = TimelineClip(name="m", clip_type="audio", source_path=str(wav), duration=8.0)
            proj.add_clip_to_track(proj.add_track("audio", "A").id, clip)
            res = ap.AutoBeatDetectionPlugin(models_dir=Path(d)).execute(proj, clip, {})
            self.assertEqual(res["reason"], "no_ffmpeg")

    def test_noise_plugin_replaces_source(self):
        with tempfile.TemporaryDirectory() as d:
            rate = 44100
            n = rate * 5
            t = np.arange(n) / rate
            x = (np.random.default_rng(9).normal(0, 0.03, n) + np.where(t > 1.5, 0.4 * np.sin(2 * np.pi * 300 * t), 0)).astype(np.float32)
            wav = Path(d) / "n.wav"
            write_wav(wav, x, rate)
            proj = VideoStudioProject()
            clip = TimelineClip(name="n", clip_type="audio", source_path=str(wav), duration=5.0, source_out=5.0)
            proj.add_clip_to_track(proj.add_track("audio", "A").id, clip)
            res = ap.AudioNoiseReductionPlugin(models_dir=Path(d)).execute(proj, clip, {"ffmpeg": FFMPEG, "work_dir": d})
            self.assertTrue(res["ok"], res)
            self.assertTrue(clip.source_path.endswith(".wav") and "denoised_" in clip.source_path)
            self.assertAlmostEqual(clip.duration, 5.0, delta=0.05)
            with wave.open(clip.source_path) as w:
                self.assertEqual(w.getframerate(), 44100)


class TestCaptions(unittest.TestCase):
    def test_split_caption(self):
        lines = ap.split_caption("one two three four five six seven eight nine ten eleven twelve thirteen", 20)
        self.assertTrue(all(len(x) <= 20 for x in lines))
        self.assertEqual(" ".join(lines), "one two three four five six seven eight nine ten eleven twelve thirteen")

    def test_captions_to_timeline(self):
        proj = VideoStudioProject()
        clip = TimelineClip(name="v", clip_type="video", timeline_start=5.0, duration=10.0, source_out=10.0)
        proj.add_clip_to_track(proj.tracks[0].id, clip)
        segs = [{"start": 0.5, "end": 2.5, "text": "مرحبا بكم"}, {"start": 3.0, "end": 6.0, "text": "this is a rather long caption line that must wrap into two lines"}]
        res = ap.captions_to_timeline(proj, clip, segs)
        self.assertTrue(res["ok"])
        trk = next(t for t in proj.tracks if t.name == "AI Subtitles")
        self.assertEqual(trk.track_type, "text")
        self.assertEqual(len(trk.clips), res["generated_captions"])
        self.assertAlmostEqual(trk.clips[0].timeline_start, 5.5, delta=0.01)
        # second run reuses the same track
        ap.captions_to_timeline(proj, clip, segs)
        self.assertEqual(len([t for t in proj.tracks if t.name == "AI Subtitles"]), 1)

    def test_whisper_missing_dependency_is_honest(self):
        with tempfile.TemporaryDirectory() as d:
            plug = ap.WhisperAutoCaptionsPlugin(models_dir=Path(d))
            try:
                import faster_whisper  # noqa: F401
                self.skipTest("faster-whisper installed")
            except Exception:
                pass
            self.assertTrue(plug.dependency_error().startswith("missing_dependency"))
            proj = VideoStudioProject()
            clip = TimelineClip(name="a", clip_type="audio", source_path=__file__, duration=3.0)
            proj.add_clip_to_track(proj.add_track("audio", "A").id, clip)
            res = plug.execute(proj, clip, {"ffmpeg": FFMPEG or "ffmpeg"})
            self.assertFalse(res["ok"])


class FakeInput:
    name = "in"
    shape = [1, 3, 320, 320]


class FakeSession:
    """Behaves like an onnxruntime session: 'person' = left half of the frame."""

    def get_inputs(self):
        return [FakeInput()]

    def run(self, _outs, feed):
        m = np.zeros((1, 1, 320, 320), np.float32)
        m[..., :160] = 1.0
        return [m]


class TestCutout(unittest.TestCase):
    def test_masks_for_image_and_render(self):
        with tempfile.TemporaryDirectory() as d:
            img_path = Path(d) / "p.png"
            cv2.imwrite(str(img_path), np.full((120, 200, 3), 180, np.uint8))
            meta = ap.write_masks(FakeSession(), str(img_path), 0.0, 1.0, Path(d) / "masks", True)
            self.assertEqual(meta["count"], 1)
            clip = TimelineClip(name="p", clip_type="image", source_path=str(img_path), duration=3.0)
            clip.ai_metadata["cutout"] = meta
            frame = np.full((120, 200, 3), 180, np.uint8)
            _bgr, alpha = process_frame_effects(frame, clip, 0.0)
            self.assertGreater(alpha[60, 20], 0.95)   # left = person
            self.assertLess(alpha[60, 180], 0.05)     # right = background
            clip.flip_h = True
            _bgr, alpha2 = process_frame_effects(frame, clip, 0.0)
            self.assertGreater(alpha2[60, 180], 0.95)  # mask follows the flip

    def test_masks_for_video_with_smoothing(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d) / "v.mp4"
            vw = cv2.VideoWriter(str(v), cv2.VideoWriter_fourcc(*"mp4v"), 30, (160, 90))
            for _ in range(60):
                vw.write(np.full((90, 160, 3), 100, np.uint8))
            vw.release()
            meta = ap.write_masks(FakeSession(), str(v), 0.0, 2.0, Path(d) / "m", False)
            self.assertAlmostEqual(meta["fps"], 15.0, delta=0.5)
            self.assertGreaterEqual(meta["count"], 28)
            self.assertEqual(len(list((Path(d) / "m").glob("m*.png"))), meta["count"])

    def test_plugin_states(self):
        with tempfile.TemporaryDirectory() as d:
            plug = ap.AutoCutoutPlugin(models_dir=Path(d))
            self.assertFalse(plug.is_installed())
            (Path(d) / "ai_models").mkdir(exist_ok=True)
            res = plug.execute(VideoStudioProject(), TimelineClip(name="x", clip_type="video", source_path=__file__), {})
            self.assertFalse(res["ok"])
            self.assertIn(res["reason"], ("wrong_clip_type", "missing_dependency", "model_missing"))

    def test_download_rejects_http_and_small(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ap.AIError):
                ap.download_file("http://example.com/x.onnx", Path(d) / "x.onnx", 10)


if __name__ == "__main__":
    unittest.main()
