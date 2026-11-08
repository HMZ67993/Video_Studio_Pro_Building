# -*- coding: utf-8 -*-
"""Sticker lane, sticker names/import, ROI blending and silence removal."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import video_studio as vs  # noqa: E402
from video_studio_core import TimelineClip, blend_layers  # noqa: E402
from video_studio_plugins import SilenceRemoverPlugin, detect_silences  # noqa: E402
from video_studio_stickers import sticker_file  # noqa: E402


def _reference_blend(base, top, alpha, mode="normal"):
    b, t = base.astype(np.float32) / 255.0, top.astype(np.float32) / 255.0
    a = np.clip(alpha[..., None], 0.0, 1.0)
    comp = {"multiply": b * t, "screen": 1 - (1 - b) * (1 - t)}.get(mode, t)
    return np.clip((b * (1 - a) + comp * a) * 255.0, 0, 255).astype(np.uint8)


class TestV2(unittest.TestCase):
    def test_blend_roi_matches_full_frame_math(self):
        rng = np.random.default_rng(1)
        base = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
        top = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
        alpha = np.zeros((60, 80), np.float32)
        alpha[10:30, 20:50] = rng.random((20, 30)).astype(np.float32)
        for mode in ("normal", "multiply", "screen"):
            got = blend_layers(base.copy(), top, alpha, mode)
            ref = _reference_blend(base, top, alpha, mode)
            self.assertLessEqual(int(np.abs(got.astype(int) - ref.astype(int)).max()), 1, mode)
        opaque = np.ones((60, 80), np.float32)
        self.assertTrue(np.array_equal(blend_layers(base.copy(), top, opaque), top))
        self.assertTrue(np.array_equal(blend_layers(base.copy(), top, np.zeros_like(alpha)), base))

    def test_stickers_share_one_visible_lane(self):
        with tempfile.TemporaryDirectory() as d:
            ctl = vs.StudioAppController(custom_data_dir=Path(d))
            a = sticker_file("star", ctl.stickers_dir(), "#FFD60A")
            b = sticker_file("heart", ctl.stickers_dir(), "#FF3B30")
            self.assertTrue(ctl.add_sticker_to_timeline(str(a), 0.0))
            self.assertTrue(ctl.add_sticker_to_timeline(str(b), 5.0))  # free slot: same lane
            lanes = [t for t in ctl.project.tracks if t.track_type == "sticker"]
            self.assertEqual(len(lanes), 1)
            self.assertEqual(len(lanes[0].clips), 2)
            kinds = [t.track_type for t in ctl.project.tracks]
            self.assertLess(kinds.index("sticker"), kinds.index("text"))  # overlays sit above video and below text
            self.assertTrue(ctl.add_sticker_to_timeline(str(b), 1.0))  # overlaps: second lane
            self.assertEqual(len([t for t in ctl.project.tracks if t.track_type == "sticker"]), 2)
            kinds = [t.track_type for t in ctl.project.tracks]
            self.assertEqual(kinds, ["video", "sticker", "sticker", "text", "audio"])

    def test_sticker_names_and_import(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as src:
            ctl = vs.StudioAppController(custom_data_dir=Path(d))
            f = Path(src) / "my_logo.png"
            f.write_bytes(Path(sticker_file("star", Path(src), "#FFD60A")).read_bytes())
            (Path(src) / "note.txt").write_text("x")
            names = ctl.import_sticker_files([str(f), str(Path(src) / "note.txt")])
            self.assertEqual(names, ["my_logo.png"])
            ctl.set_sticker_name("my_logo.png", "شعاري", "My logo")
            self.assertEqual(ctl.sticker_label("my_logo.png", "ar"), "شعاري")
            self.assertEqual(ctl.sticker_label("my_logo.png", "en"), "My logo")
            ctl.settings.data["lang"] = "ar"
            self.assertTrue(ctl.add_sticker_to_timeline(str(ctl.my_stickers_dir() / "my_logo.png"), 0.0))
            clip = [c for t in ctl.project.tracks for c in t.clips if c.clip_type == "sticker"][0]
            self.assertEqual(clip.name, "شعاري")

    def test_folder_sticker_import_is_recursive_and_validated(self):
        with tempfile.TemporaryDirectory() as data_dir, tempfile.TemporaryDirectory() as src_dir:
            ctl = vs.StudioAppController(custom_data_dir=Path(data_dir))
            nested = Path(src_dir) / "nested"
            nested.mkdir()
            valid = sticker_file("heart", nested, "#FF3B5C")
            (nested / "not_image.png").write_bytes(b"not an image")
            imported = ctl.import_stickers([src_dir])
            self.assertEqual(len(imported), 1)
            self.assertTrue(Path(imported[0]).exists())
            self.assertEqual(Path(imported[0]).name, valid.name)

    def test_detect_and_cut_silence(self):
        rate = 16000
        t = np.arange(rate) / rate
        tone = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        x = np.concatenate([tone, np.zeros(rate * 2, np.float32), tone])  # 1s sound, 2s silence, 1s sound
        spans = detect_silences(x, rate)
        self.assertEqual(len(spans), 1)
        self.assertAlmostEqual(spans[0][0], 1.06, delta=0.05)
        self.assertAlmostEqual(spans[0][1], 2.94, delta=0.05)
        ctl = vs.StudioAppController(custom_data_dir=Path(tempfile.mkdtemp()))
        proj = ctl.project
        trk = next(t for t in proj.tracks if t.track_type == "audio")
        clip = TimelineClip(name="a", clip_type="audio", source_path="x.wav", timeline_start=0.0, duration=4.0, source_in=0.0, source_out=4.0)
        proj.add_clip_to_track(trk.id, clip)
        res = SilenceRemoverPlugin(models_dir=Path(tempfile.mkdtemp())).apply(proj, clip, {"spans": spans})
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(sum(c.duration for c in trk.clips), 4.0 - (spans[0][1] - spans[0][0]), delta=0.05)


if __name__ == "__main__":
    unittest.main()
