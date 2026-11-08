import sys
from pathlib import Path
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from video_studio_core import (  # noqa: E402
    Keyframe, TimelineClip, VideoStudioProject, export_clips_to_vtt,
    evaluate_clip_property, process_frame_effects,
)
from video_studio_ffmpeg import build_audio_mix, clip_audio_chain  # noqa: E402
from video_studio_plugins import smooth_tracking_path, detect_gradual_transition_times, _source_offset_to_timeline  # noqa: E402


class Phase23FeatureTests(unittest.TestCase):
    def test_nested_color_keyframes_evaluate_and_render(self):
        clip = TimelineClip()
        clip.color.brightness = 0
        clip.keyframes['color.brightness'] = [Keyframe(0, 0), Keyframe(2, 50)]
        self.assertAlmostEqual(evaluate_clip_property(clip, 'color.brightness', 1, 0), 25)
        frame = np.full((48, 64, 3), 80, np.uint8)
        out, _ = process_frame_effects(frame, clip, local_time=2)
        self.assertGreater(float(out.mean()), float(frame.mean()))

    def test_effect_intensity_and_new_effects(self):
        frame = np.full((64, 64, 3), (40, 100, 180), np.uint8)
        clip = TimelineClip(visual_effect='invert', effect_intensity=0)
        out0, _ = process_frame_effects(frame, clip)
        self.assertTrue(np.array_equal(out0, frame))
        clip.effect_intensity = 100
        out1, _ = process_frame_effects(frame, clip)
        self.assertFalse(np.array_equal(out1, frame))
        clip.visual_effect = 'gaussian_blur'
        self.assertEqual(process_frame_effects(frame, clip)[0].shape, frame.shape)

    def test_vtt_export(self):
        clip = TimelineClip(clip_type='text', timeline_start=1.25, duration=2.0)
        clip.text_style.text = 'Hello world'
        vtt = export_clips_to_vtt([clip])
        self.assertTrue(vtt.startswith('WEBVTT'))
        self.assertIn('00:00:01.250 --> 00:00:03.250', vtt)
        self.assertIn('Hello world', vtt)

    def test_auto_ducking_graph_is_opt_in_and_sidechains_dialogue(self):
        with tempfile.TemporaryDirectory() as tmp:
            voice = Path(tmp) / 'voice.wav'
            music = Path(tmp) / 'music.wav'
            voice.write_bytes(b'x')
            music.write_bytes(b'x')
            class Track:
                def __init__(self, name, kind, clips): self.name, self.track_type, self.muted, self.clips = name, kind, False, clips
            v = TimelineClip(clip_type='video', source_path=str(voice), duration=3, source_out=3)
            m = TimelineClip(clip_type='audio', source_path=str(music), duration=3, source_out=3)
            proj = VideoStudioProject()
            proj.tracks = [Track('Video 1', 'video', [v]), Track('Music', 'audio', [m])]
            # Avoid ffprobe dependency in graph construction.
            import video_studio_ffmpeg as vf
            old = vf.has_audio_stream
            vf.has_audio_stream = lambda _ff, _path: True
            try:
                proj.auto_ducking = True
                graph = build_audio_mix(proj, 'ffmpeg', 3, 0)
                self.assertIn('sidechaincompress', graph['filter'])
                self.assertIn('hmzvoice', graph['filter'])
                proj.auto_ducking = False
                graph_off = build_audio_mix(proj, 'ffmpeg', 3, 0)
                self.assertNotIn('sidechaincompress', graph_off['filter'])
            finally:
                vf.has_audio_stream = old

    def test_gradual_scene_transition_detection(self):
        diffs = [(i * 0.2, value) for i, value in enumerate([0.01, 0.08, 0.14, 0.19, 0.17, 0.12, 0.02, 0.01])]
        times = detect_gradual_transition_times(diffs, start=0, duration=3, min_scene=0.3)
        self.assertEqual(len(times), 1)
        self.assertGreater(times[0], 0.2)
        self.assertLess(times[0], 1.2)

    def test_ab_transition_creates_real_overlap_and_preserves_end(self):
        project = VideoStudioProject()
        track = project.tracks[0]
        outgoing = TimelineClip(clip_type='video', timeline_start=0, duration=4, source_in=0, source_out=4)
        incoming = TimelineClip(clip_type='video', timeline_start=4, duration=4, source_in=1, source_out=5)
        track.clips = [outgoing, incoming]
        original_end = incoming.timeline_end
        self.assertTrue(project.create_ab_transition(outgoing.id, incoming.id, 0.5, 'crossfade'))
        self.assertAlmostEqual(incoming.timeline_start, 3.5)
        self.assertAlmostEqual(incoming.source_in, 0.5)
        self.assertAlmostEqual(incoming.timeline_end, original_end)
        self.assertEqual(incoming.transition_in, 'crossfade')
        self.assertAlmostEqual(incoming.transition_duration, 0.5)

    def test_transcript_timing_maps_source_time_through_speed_curve(self):
        clip = TimelineClip(duration=4.0, speed=2.0, speed_curve="constant")
        self.assertAlmostEqual(_source_offset_to_timeline(clip, 3.0), 1.5, places=3)
        clip.speed_curve = "ease_in"
        mapped = _source_offset_to_timeline(clip, 1.0)
        self.assertGreater(mapped, 0.0)
        self.assertLess(mapped, 4.0)

    def test_ab_transition_blends_both_clips_during_overlap(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            a_path, b_path = Path(tmp) / 'a.png', Path(tmp) / 'b.png'
            Image.fromarray(np.full((32, 48, 3), (20, 20, 20), dtype=np.uint8)).save(a_path)
            Image.fromarray(np.full((32, 48, 3), (220, 220, 220), dtype=np.uint8)).save(b_path)
            project = VideoStudioProject()
            track = project.tracks[0]
            outgoing = TimelineClip(clip_type='image', source_path=str(a_path), timeline_start=0, duration=4, source_in=0, source_out=4)
            incoming = TimelineClip(clip_type='image', source_path=str(b_path), timeline_start=4, duration=4, source_in=1, source_out=5)
            track.clips = [outgoing, incoming]
            self.assertTrue(project.create_ab_transition(outgoing.id, incoming.id, 0.5, 'crossfade'))
            frame = project.render_composite_frame(3.75, preview_scale=0.05)
            self.assertGreater(float(frame.mean()), 70.0)
            self.assertLess(float(frame.mean()), 180.0)

    def test_tracking_path_smoothing(self):
        samples = [(0, .1, .5), (1, .9, .5), (2, .1, .5)]
        smoothed = smooth_tracking_path(samples, radius=1)
        self.assertEqual(len(smoothed), 3)
        self.assertLess(smoothed[1][1], .9)

    def test_volume_keyframes_create_ffmpeg_automation(self):
        clip = TimelineClip(volume_db=0)
        clip.keyframes["volume_db"] = [Keyframe(0, 0), Keyframe(1, -12), Keyframe(2, 0)]
        chain = clip_audio_chain(clip)
        self.assertIn("volume='pow(10,", chain)
        self.assertIn("eval=frame", chain)
        self.assertIn("-12.0000", chain)

    def test_powerpoint_style_transitions_render_without_shape_errors(self):
        from PIL import Image
        transitions = ["wipe_right", "wipe_up", "wipe_down", "circle_reveal", "diamond", "blinds",
                       "checkerboard", "push_left", "push_right", "push_up", "push_down", "rotate_in", "blur_in", "flash"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "solid.png"
            Image.fromarray(np.full((48, 64, 3), (60, 140, 220), dtype=np.uint8)).save(path)
            project = VideoStudioProject()
            for transition in transitions:
                clip = TimelineClip(clip_type="image", source_path=str(path), duration=2,
                                    transition_in=transition, transition_duration=1)
                project.tracks[0].clips = [clip]
                frame = project.render_composite_frame(0.4, preview_scale=0.05)
                self.assertEqual(frame.shape, (64, 96, 3), transition)

    def test_transcript_range_removal_ripples_all_tracks_in_sync(self):
        project = VideoStudioProject()
        video_track = project.tracks[0]
        audio_track = project.tracks[2]
        video = TimelineClip(clip_type="video", source_path="video.mp4", timeline_start=0, duration=10, source_in=0, source_out=10)
        audio = TimelineClip(clip_type="audio", source_path="audio.wav", timeline_start=0, duration=10, source_in=0, source_out=10)
        caption = TimelineClip(clip_type="text", timeline_start=2, duration=2)
        caption.ai_metadata = {"transcript_source_clip_id": video.id, "transcript_timeline_start": 2, "transcript_timeline_end": 4}
        later = TimelineClip(clip_type="text", timeline_start=6, duration=1)
        video_track.clips = [video]
        audio_track.clips = [audio]
        project.tracks[1].clips = [caption, later]
        self.assertTrue(project.remove_transcript_segment(caption.id))
        self.assertEqual(len(video_track.clips), 2)
        self.assertAlmostEqual(video_track.clips[0].duration, 2)
        self.assertAlmostEqual(video_track.clips[1].timeline_start, 2)
        self.assertAlmostEqual(video_track.clips[1].duration, 6)
        self.assertEqual(len(audio_track.clips), 2)
        self.assertAlmostEqual(audio_track.clips[1].timeline_start, 2)
        self.assertAlmostEqual(project.tracks[1].clips[0].timeline_start, 4)

    def test_project_ducking_round_trip(self):
        p = VideoStudioProject()
        p.auto_ducking = True
        p.ducking_amount_db = 15
        q = VideoStudioProject()
        q.load_from_json_string(p.to_json_string())
        self.assertTrue(q.auto_ducking)
        self.assertEqual(q.ducking_amount_db, 15)


if __name__ == '__main__':
    unittest.main()
