# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(ROOT))

from video_studio import StudioAppController  # noqa: E402
from video_studio_audio import _try_unlink, audio_signature, render_preview_wav  # noqa: E402
from unittest.mock import patch  # noqa: E402
from video_studio_core import TimelineClip, VideoStudioProject, generate_thumbnail  # noqa: E402

FF = shutil.which("ffmpeg")


class TestAutosave(unittest.TestCase):
    def test_dirty_autosave_recover_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            c = StudioAppController(custom_data_dir=Path(d))
            self.assertFalse(c.is_dirty())
            self.assertFalse(c.autosave_if_dirty())          # nothing to save yet
            c.project.playhead_sec = 3.0
            self.assertFalse(c.is_dirty())                    # playhead moves are not edits
            c.project.add_track("text")
            self.assertTrue(c.is_dirty())
            self.assertTrue(c.autosave_if_dirty())
            self.assertTrue(c.has_recovery())
            n_tracks = len(c.project.tracks)
            c2 = StudioAppController(custom_data_dir=Path(d))  # "new session after a crash"
            self.assertTrue(c2.has_recovery())
            self.assertTrue(c2.recover_project())
            self.assertEqual(len(c2.project.tracks), n_tracks)
            self.assertTrue(c2.is_dirty())                    # recovered work still counts as unsaved
            c2.mark_saved()
            self.assertFalse(c2.has_recovery())

    def test_corrupt_autosave_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            c = StudioAppController(custom_data_dir=Path(d))
            c.autosave_path().write_text("{broken", encoding="utf-8")
            self.assertFalse(c.has_recovery())
            self.assertFalse(c.autosave_path().exists())


class TestAudioPreview(unittest.TestCase):
    def test_temp_wav_cleanup_tolerates_windows_file_lock(self):
        # Regression for WinError 32: a media backend can keep a rendered WAV open.
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "mix_locked.wav"
            target.write_bytes(b"wav")
            with patch.object(Path, "unlink", side_effect=PermissionError("file is in use")):
                self.assertFalse(_try_unlink(target))
            self.assertTrue(target.exists())
            self.assertTrue(_try_unlink(target))
            self.assertFalse(target.exists())

    def test_signature_changes_only_with_audio(self):
        p = VideoStudioProject(name="t")
        for t in p.tracks:
            t.clips.clear()
        vt = next(t for t in p.tracks if t.track_type == "video")
        c = TimelineClip(name="v", clip_type="video", source_path=__file__, duration=2)
        vt.clips.append(c)
        s1 = audio_signature(p)
        c.pos_x = 50                      # a visual edit does not invalidate the audio
        self.assertEqual(s1, audio_signature(p))
        c.volume_db = -6                  # an audible edit does
        self.assertNotEqual(s1, audio_signature(p))

    @unittest.skipUnless(FF, "ffmpeg missing")
    def test_render_preview_wav_and_thumbnail(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([FF, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=160x90:d=2:r=30", "-f", "lavfi", "-i", "sine=d=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", f"{d}/v.mp4"], check=True)
            p = VideoStudioProject(name="t")
            for t in p.tracks:
                t.clips.clear()
            next(t for t in p.tracks if t.track_type == "video").clips.append(TimelineClip(name="v", clip_type="video", source_path=f"{d}/v.mp4", duration=2, source_out=2))
            out = Path(d) / "pv.wav"
            self.assertTrue(render_preview_wav(p, FF, out))
            self.assertGreater(out.stat().st_size, 100000)
            th = generate_thumbnail(f"{d}/v.mp4", 1.0, 40)
            self.assertEqual(th.shape[0], 40)
            self.assertIsNone(generate_thumbnail(f"{d}/missing.mp4", 0, 40))
            # cancel kills ffmpeg and reports False
            self.assertFalse(render_preview_wav(p, FF, Path(d) / "x.wav", cancel=lambda: True))


if __name__ == "__main__":
    unittest.main()
