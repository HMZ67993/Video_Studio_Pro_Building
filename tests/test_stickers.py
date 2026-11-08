# -*- coding: utf-8 -*-
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
from video_studio_core import TimelineClip, VideoStudioProject, probe_media_duration  # noqa: E402
from video_studio_stickers import COLORS, STICKERS, render_frame, sticker_file  # noqa: E402


class TestStickers(unittest.TestCase):
    def test_library_complete_and_original(self):
        self.assertEqual(len(STICKERS), 38)
        self.assertEqual(sum(1 for v in STICKERS.values() if v[2]), 13)
        for sid in STICKERS:
            im = render_frame(sid, 0.4, "#FF3B30")
            self.assertEqual(im.mode, "RGBA")
            self.assertGreater(np.asarray(im)[..., 3].max(), 0, sid)

    def test_animated_frames_differ(self):
        for sid, v in STICKERS.items():
            frames = [np.asarray(render_frame(sid, p / 10.0, "#FFD60A")) for p in range(10)]
            moving = any(not np.array_equal(frames[0], f) for f in frames[1:])
            self.assertEqual(moving, bool(v[2]), sid)  # animated <=> frames really change

    def test_file_render_and_timeline(self):
        with tempfile.TemporaryDirectory() as d:
            static = sticker_file("star", Path(d), "#FFD60A")
            anim = sticker_file("spinner", Path(d), "#00D2E6")
            self.assertTrue(static.exists() and anim.exists())
            self.assertGreater(probe_media_duration(str(anim)), 0.2)
            ctl = vs.StudioAppController(custom_data_dir=Path(d))
            self.assertTrue(ctl.add_sticker_to_timeline(str(anim), 1.0))
            clips = [c for t in ctl.project.tracks for c in t.clips if c.clip_type == "sticker"]
            self.assertEqual(len(clips), 1)
            self.assertAlmostEqual(clips[0].timeline_start, 1.0, delta=0.01)
            f0 = ctl.project.render_composite_frame(0.5, 0.25)
            f1 = ctl.project.render_composite_frame(1.5, 0.25)
            self.assertFalse(np.array_equal(f0, f1))  # sticker visible in the composite

    def test_crop_changes_render(self):
        import cv2
        from video_studio_core import process_frame_effects

        frame = np.zeros((90, 160, 3), np.uint8)
        frame[:, :40] = 255
        clip = TimelineClip(name="c", clip_type="video")
        base, _ = process_frame_effects(frame, clip, 0.0)
        clip.crop_left = 0.25
        cropped, _ = process_frame_effects(frame, clip, 0.0)
        self.assertGreater(base[:, :40].mean(), 200)
        self.assertLess(cropped[:, :40].mean(), 40)  # white strip cropped away

    def test_colors_valid(self):
        for hex_ in COLORS:
            self.assertRegex(hex_, r"^#[0-9A-Fa-f]{6}$")


if __name__ == "__main__":
    unittest.main()
