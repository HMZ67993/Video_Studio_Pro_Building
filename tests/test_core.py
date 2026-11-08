# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from video_studio_core import (  # noqa: E402
    Keyframe,
    TimelineClip,
    VideoStudioProject,
    build_ffmpeg_clip_filters,
    evaluate_speed_curve,
    export_clips_to_srt,
    interpolate_keyframes,
    parse_cube_lut,
    parse_srt_content,
    process_frame_effects,
)
from video_studio_plugins import AIPluginRegistry  # noqa: E402


class TestVideoStudioCore(unittest.TestCase):
    def test_timeline_split_freeze_detach_and_undo_redo(self) -> None:
        proj = VideoStudioProject(name="TestProj", aspect_ratio="16:9", fps=30)
        v_track = proj.tracks[0]
        clip = TimelineClip(name="Scene1", clip_type="video", timeline_start=0.0, duration=6.0)
        self.assertTrue(proj.add_clip_to_track(v_track.id, clip))
        self.assertEqual(len(v_track.clips), 1)

        split_res = proj.split_clip_at(clip.id, split_time=2.5)
        self.assertIsNotNone(split_res)
        self.assertEqual(len(v_track.clips), 2)
        self.assertAlmostEqual(v_track.clips[0].duration, 2.5)
        self.assertAlmostEqual(v_track.clips[1].timeline_start, 2.5)
        self.assertAlmostEqual(v_track.clips[1].duration, 3.5)

        self.assertTrue(proj.undo())
        self.assertEqual(len(proj.tracks[0].clips), 1)
        self.assertTrue(proj.redo())
        self.assertEqual(len(proj.tracks[0].clips), 2)

        c0_id = proj.tracks[0].clips[0].id
        frozen = proj.freeze_frame_at(c0_id, freeze_time=1.0, freeze_duration=2.0)
        self.assertIsNotNone(frozen)
        self.assertTrue(frozen.is_freeze_frame)

        detached = proj.detach_audio_from_clip(c0_id)
        self.assertIsNotNone(detached)
        self.assertEqual(detached.clip_type, "audio")

    def test_magnetic_snapping(self) -> None:
        proj = VideoStudioProject()
        proj.playhead_sec = 4.0
        self.assertAlmostEqual(proj.compute_snap_time(4.12), 4.0)
        self.assertAlmostEqual(proj.compute_snap_time(5.5), 5.5)

    def test_keyframes_and_speed_curves(self) -> None:
        kfs = [
            Keyframe(time_offset=0.0, value=0.0, easing="linear"),
            Keyframe(time_offset=2.0, value=100.0, easing="ease_in_out"),
        ]
        self.assertAlmostEqual(interpolate_keyframes(kfs, 0.0, 10.0), 0.0)
        self.assertAlmostEqual(interpolate_keyframes(kfs, 1.0, 10.0), 50.0)
        self.assertAlmostEqual(interpolate_keyframes(kfs, 2.0, 10.0), 100.0)
        self.assertGreater(evaluate_speed_curve("montage", 0.5, base_speed=1.0), 1.5)

    def test_color_grading_chroma_masks_and_cube_lut(self) -> None:
        frame = np.full((120, 160, 3), (0, 255, 0), dtype=np.uint8)
        clip = TimelineClip(name="GreenScreen")
        clip.chroma.enabled = True
        clip.chroma.key_color_hex = "#00FF00"
        clip.color.brightness = 15.0
        clip.color.contrast = 10.0
        clip.color.saturation = 20.0
        clip.mask.shape = "circle"
        clip.visual_effect = "warm_film"

        with tempfile.TemporaryDirectory() as tmp:
            lut_file = Path(tmp) / "test.cube"
            lut_content = "\n".join(
                [
                    'TITLE "TestLUT"',
                    "LUT_3D_SIZE 2",
                    "0.0 0.0 0.0",
                    "1.0 0.0 0.0",
                    "0.0 1.0 0.0",
                    "1.0 1.0 0.0",
                    "0.0 0.0 1.0",
                    "1.0 0.0 1.0",
                    "0.0 1.0 1.0",
                    "1.0 1.0 1.0",
                ]
            )
            lut_file.write_text(lut_content, encoding="utf-8")
            parsed = parse_cube_lut(str(lut_file))
            self.assertIsNotNone(parsed)
            clip.color.lut_path = str(lut_file)

            out_bgr, alpha = process_frame_effects(frame, clip, local_time=0.5)
            self.assertEqual(out_bgr.shape, (120, 160, 3))
            self.assertEqual(alpha.shape, (120, 160))
            self.assertLess(float(np.mean(alpha)), 0.1)

    def test_srt_subtitles_and_ffmpeg_filters(self) -> None:
        srt_sample = (
            "1\n00:00:01,000 --> 00:00:03,500\nمرحباً بكم في HMZ\n\n"
            "2\n00:00:04,000 --> 00:00:06,000\nWelcome to HMZ Studio\n"
        )
        clips = parse_srt_content(srt_sample)
        self.assertEqual(len(clips), 2)
        self.assertAlmostEqual(clips[0].timeline_start, 1.0)
        self.assertAlmostEqual(clips[0].duration, 2.5)
        exported_srt = export_clips_to_srt(clips)
        self.assertIn("00:00:01,000 --> 00:00:03,500", exported_srt)

        v_clip = TimelineClip(flip_h=True, reverse=True, speed=1.5, volume_db=3.0, fade_in=0.5, pitch_semitones=2.0, eq_preset="voice")
        vf, af = build_ffmpeg_clip_filters(v_clip)
        self.assertIn("hflip", vf)
        self.assertIn("reverse", vf)
        self.assertTrue(any("volume=" in f for f in af))
        self.assertTrue(any("equalizer=" in f for f in af))

    def test_project_serialization_and_video_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            proj = VideoStudioProject(name="ExportTest", aspect_ratio="16:9", fps=10)
            c = TimelineClip(name="ClipA", clip_type="video", timeline_start=0.0, duration=0.5)
            proj.add_clip_to_track(proj.tracks[0].id, c)

            hvsp_file = tmp_path / "test_proj.hvsp"
            proj.save_project_file(str(hvsp_file))
            self.assertTrue(hvsp_file.exists())

            proj2 = VideoStudioProject()
            proj2.load_project_file(str(hvsp_file))
            self.assertEqual(proj2.name, "ExportTest")

            mp4_out = tmp_path / "out.mp4"
            ok = proj2.export_project(str(mp4_out), resolution_label="540p (Proxy)", fps=10)
            self.assertTrue(ok)
            self.assertTrue(mp4_out.exists())
            self.assertGreater(mp4_out.stat().st_size, 0)

    def test_extensible_local_ai_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg = AIPluginRegistry(models_dir=Path(tmp))
            ids = {p.descriptor.plugin_id for p in reg.list_plugins()}
            self.assertEqual(ids, {"ai_beat_detection", "ai_scene_split", "ai_noise_reduction", "ai_silence_remover", "ai_whisper_captions", "ai_auto_cutout", "ai_auto_reframe", "ai_motion_tracking"})
            # tools that need a model are NOT reported as installed until the model really exists
            self.assertFalse(reg.get_plugin("ai_whisper_captions").is_installed())
            self.assertFalse(reg.get_plugin("ai_auto_cutout").is_installed())
            # without a clip, tools refuse honestly instead of pretending
            proj = VideoStudioProject()
            res = reg.get_plugin("ai_beat_detection").execute(proj, None, {})
            self.assertFalse(res.get("ok"))
            self.assertEqual(res.get("reason"), "no_clip")


if __name__ == "__main__":
    unittest.main()
