# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(os.path.abspath(__file__)).parent.parent))

import numpy as np  # noqa: E402

import video_studio as vs  # noqa: E402
from video_studio_core import TimelineClip, VideoStudioProject, blend_layers, clip_animation_state, track_accepts  # noqa: E402
from video_studio_i18n import track_display_name  # noqa: E402
from video_studio_stickers import STICKERS, clip_display_name, sticker_file  # noqa: E402


class TestStickerTracks(unittest.TestCase):
    def test_sticker_track_is_created_on_demand(self):
        p = VideoStudioProject()
        self.assertEqual([t.track_type for t in p.tracks], ["video", "text", "audio"])
        stk = p.add_track("sticker")
        self.assertEqual([t.track_type for t in p.tracks], ["video", "sticker", "text", "audio"])

    def test_sticker_goes_to_sticker_track_and_name_follows_language(self):
        with tempfile.TemporaryDirectory() as d:
            ctl = vs.StudioAppController(custom_data_dir=Path(d))
            f = sticker_file("star", Path(d), "#FFD60A")
            self.assertTrue(ctl.add_sticker_to_timeline(str(f), 1.0, meta={"sticker_id": "star", "sticker_color": "#FFD60A"}))
            trk, clip = next((t, c) for t in ctl.project.tracks for c in t.clips if c.clip_type == "sticker")
            self.assertEqual(trk.track_type, "sticker")
            self.assertEqual(clip_display_name(clip, "ar"), STICKERS["star"][0])
            self.assertEqual(clip_display_name(clip, "en"), STICKERS["star"][1])
            # overlapping sticker -> a second sticker track, one undo step
            n = len(ctl.project.tracks)
            self.assertTrue(ctl.add_sticker_to_timeline(str(f), 1.5))
            self.assertEqual(len(ctl.project.tracks), n + 1)
            ctl.project.undo()
            self.assertEqual(len(ctl.project.tracks), n)

    def test_accepts_paste_and_track_names(self):
        self.assertTrue(track_accepts("sticker", "sticker"))
        self.assertFalse(track_accepts("sticker", "video"))
        self.assertTrue(track_accepts("video", "sticker"))  # old projects
        p = VideoStudioProject()
        stk = p.add_track("sticker")
        c = TimelineClip(clip_type="sticker", duration=1)
        p.add_clip_to_track(stk.id, c)
        self.assertIsNotNone(p.paste_clip(c, None, 4.0))
        self.assertEqual(track_display_name(stk, "ar"), "مسار ملصقات 1")
        self.assertEqual(track_display_name(stk, "en"), "Sticker Track 1")

    def test_close_gaps_and_roundtrip(self):
        p = VideoStudioProject()
        v = p.tracks[0]
        for s in (0.0, 3.0, 9.0):
            p.add_clip_to_track(v.id, TimelineClip(clip_type="image", timeline_start=s, duration=2, anim_in="pop", anim_loop="pulse"))
        self.assertTrue(p.close_gaps(v.id))
        self.assertEqual([c.timeline_start for c in v.clips], [0.0, 2.0, 4.0])
        q = VideoStudioProject()
        q.load_from_json_string(p.to_json_string())
        self.assertEqual(q.tracks[0].clips[0].anim_in, "pop")


class TestAnimBlend(unittest.TestCase):
    def test_animation_state(self):
        c = TimelineClip(duration=3, anim_in="fade", anim_out="fade")
        self.assertLess(clip_animation_state(c, 0.05, 960, 540)[4], 0.5)
        self.assertAlmostEqual(clip_animation_state(c, 1.5, 960, 540)[4], 1.0)
        self.assertLess(clip_animation_state(c, 2.95, 960, 540)[4], 0.5)

    def test_animated_sticker_changes_render(self):
        with tempfile.TemporaryDirectory() as d:
            ctl = vs.StudioAppController(custom_data_dir=Path(d))
            f = sticker_file("star", Path(d), "#FFD60A")
            ctl.add_sticker_to_timeline(str(f), 0.0, duration=3.0)
            clip = ctl.get_selected_clip()
            a = ctl.project.render_composite_frame(0.0, 0.25)
            clip.anim_in = "fade"
            b = ctl.project.render_composite_frame(0.0, 0.25)
            self.assertFalse(np.array_equal(a, b))

    def test_blend_roi_matches_reference(self):
        rng = np.random.default_rng(1)
        base = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
        top = rng.integers(0, 255, (60, 80, 3), dtype=np.uint8)
        al = np.zeros((60, 80), np.float32)
        al[10:30, 20:50] = rng.random((20, 30))
        for mode in ("normal", "multiply", "screen"):
            out = blend_layers(base, top, al, mode)
            self.assertTrue(np.array_equal(out[:10], base[:10]))
            self.assertEqual(out.dtype, np.uint8)
        full = blend_layers(base, top, np.ones((60, 80), np.float32))
        self.assertTrue(np.array_equal(full, top))


if __name__ == "__main__":
    unittest.main()
