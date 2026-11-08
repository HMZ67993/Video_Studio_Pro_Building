# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(ROOT))

import video_studio_ffmpeg as F  # noqa: E402
from video_studio_core import TimelineClip, VideoStudioProject  # noqa: E402

FF = shutil.which("ffmpeg")
needs_ffmpeg = unittest.skipUnless(FF, "ffmpeg not installed on this machine")


def fake_ffmpeg(dir_: Path) -> Path:
    p = dir_ / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
    p.write_text("#!/bin/sh\necho 'ffmpeg version 7.0.1 Copyright'\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return p


class TestLocate(unittest.TestCase):
    def test_find_order_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "ffmpeg").mkdir()
            exe = fake_ffmpeg(d / "ffmpeg")
            self.assertEqual(F.find_ffmpeg(d, ""), str(exe))
            self.assertEqual(F.find_ffmpeg(d, str(exe)), str(exe))
            # Version parsing is platform-independent; don't execute a POSIX
            # shebang fixture as a Windows PE executable on GitHub's Windows runner.
            with mock.patch.object(F, "_run", return_value=(0, "ffmpeg version 7.0.1 Copyright")):
                self.assertEqual(F.ffmpeg_version(str(exe)), (7, 0, 1))
            with mock.patch.object(F, "_run", return_value=(-1, "not found")):
                self.assertIsNone(F.ffmpeg_version(str(d / "nope")))
            bad = d / "bad.exe"
            bad.write_text("not a binary")
            self.assertFalse(F.validate_ffmpeg(str(bad)))

    def test_extract_from_zip(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = fake_ffmpeg(d)
            z = d / "x.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.write(src, "ffmpeg-7.0-essentials_build/bin/" + src.name)
                zf.writestr("ffmpeg-7.0-essentials_build/readme.txt", "x")
            # Extraction is what this test covers; execution is tested separately
            # with a mocked subprocess result because this fixture is not a real binary.
            with mock.patch.object(F, "validate_ffmpeg", return_value=True):
                ok, path = F.extract_ffmpeg_from_zip(z, d / "out")
            self.assertTrue(ok, path)
            self.assertTrue(Path(path).exists())

    def test_zip_without_ffmpeg(self):
        with tempfile.TemporaryDirectory() as d:
            z = Path(d) / "x.zip"
            with zipfile.ZipFile(z, "w") as zf:
                zf.writestr("readme.txt", "x")
            ok, msg = F.extract_ffmpeg_from_zip(z, Path(d) / "o")
            self.assertFalse(ok)

    def test_download_rejects_http_and_bad_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(F.download_ffmpeg(Path(d), zip_url="http://x/y.zip", sha_url="https://x/y.sha")[0])

            class Resp:
                def __init__(self, data):
                    self.data, self.headers, self.pos = data, {"Content-Length": str(len(data))}, 0
                def read(self, n=-1):
                    chunk = self.data[self.pos:self.pos + (n if n > 0 else len(self.data))]
                    self.pos += len(chunk)
                    return chunk
                def __enter__(self): return self
                def __exit__(self, *a): return False

            def fake_urlopen(req, timeout=0):
                url = req.full_url if hasattr(req, "full_url") else req
                return Resp((("0" * 64) + "  f.zip").encode() if url.endswith(".sha256") else b"zipdata")

            with mock.patch.object(F.urllib.request, "urlopen", fake_urlopen):
                ok, msg = F.download_ffmpeg(Path(d))
            self.assertFalse(ok)
            self.assertEqual(msg, "checksum mismatch")


class TestAudioGraph(unittest.TestCase):
    def clip(self, **kw):
        base = dict(name="a", clip_type="audio", source_path="/x.wav", timeline_start=1.5, duration=2.0, source_in=0.0, source_out=2.0)
        base.update(kw)
        return TimelineClip(**base)

    def test_chain_contents(self):
        c = F.clip_audio_chain(self.clip(volume_db=-6, fade_in=0.5, fade_out=0.5, speed=4.0, reverse=True, eq_preset="voice", pitch_semitones=3))
        for token in ("atrim=start=0.0000:end=2.0000", "areverse", "atempo=2.0,atempo=2.00000", "volume=-6.00dB", "afade=t=in", "afade=t=out", "equalizer", "asetrate", "adelay=1500|1500"):
            self.assertIn(token, c)

    def test_atempo_chain_ranges(self):
        for sp in (0.1, 0.25, 0.5, 1.7, 2.0, 3.0, 10.0, 100.0):
            for part in F._atempo_chain(sp):
                v = float(part.split("=")[1])
                self.assertTrue(0.5 <= v <= 2.0, (sp, part))

    def test_audible_rules(self):
        p = VideoStudioProject(name="t")
        for t in p.tracks:
            t.clips.clear()
        vt = next(t for t in p.tracks if t.track_type == "video")
        at = next((t for t in p.tracks if t.track_type == "audio"), None) or p.add_track("audio", "A")
        vt.clips.append(TimelineClip(name="v", clip_type="video", source_path="/v.mp4"))
        vt.clips.append(TimelineClip(name="m", clip_type="video", source_path="/v.mp4", muted=True))
        vt.clips.append(TimelineClip(name="i", clip_type="image", source_path="/i.png"))
        at.clips.append(TimelineClip(name="a", clip_type="audio", source_path="/a.wav"))
        self.assertEqual({c.name for c in F.audible_clips(p)}, {"v", "a"})
        at.muted = True
        self.assertEqual({c.name for c in F.audible_clips(p)}, {"v"})


@needs_ffmpeg
class TestRealMix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.tmp.name
        run = lambda *a: subprocess.run([FF, "-y", "-v", "error", *a], check=True)  # noqa: E731
        run("-f", "lavfi", "-i", "testsrc=s=160x90:d=2:r=30", "-f", "lavfi", "-i", "sine=f=440:d=2", "-c:v", "libx264", "-c:a", "aac", "-shortest", f"{d}/v.mp4")
        run("-f", "lavfi", "-i", "sine=f=880:d=1", f"{d}/m.wav")
        run("-f", "lavfi", "-i", "testsrc=s=160x90:d=1:r=30", "-c:v", "libx264", f"{d}/s.mp4")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def project(self, with_music=True):
        d = self.tmp.name
        p = VideoStudioProject(name="t")
        for t in p.tracks:
            t.clips.clear()
        vt = next(t for t in p.tracks if t.track_type == "video")
        at = next((t for t in p.tracks if t.track_type == "audio"), None) or p.add_track("audio", "A")
        vt.clips.append(TimelineClip(name="v", clip_type="video", source_path=f"{d}/v.mp4", timeline_start=0, duration=2, source_out=2))
        vt.clips.append(TimelineClip(name="s", clip_type="video", source_path=f"{d}/s.mp4", timeline_start=2, duration=1, source_out=1))
        if with_music:
            at.clips.append(TimelineClip(name="m", clip_type="audio", source_path=f"{d}/m.wav", timeline_start=0.5, duration=1, source_out=1))
        return p

    def probe(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name", "-of", "json", path], capture_output=True, text=True).stdout
        return {s["codec_type"]: s["codec_name"] for s in json.loads(out)["streams"]}

    def mean_db(self, path, a, b):
        r = subprocess.run([FF, "-v", "info", "-ss", str(a), "-to", str(b), "-i", path, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
        return float(re.findall(r"mean_volume: (\S+)", r)[0])

    def test_video_has_mixed_audio(self):
        out = f"{self.tmp.name}/out.mp4"
        p = self.project()
        self.assertTrue(p.export_project(out, "540p (Proxy)", 30, ffmpeg_path=FF))
        self.assertEqual(p.last_export_info["audio"], "mixed")
        streams = self.probe(out)
        self.assertEqual(streams, {"video": "h264", "audio": "aac"})
        self.assertGreater(self.mean_db(out, 0.1, 1.5), -40)   # sound present
        self.assertLess(self.mean_db(out, 2.2, 2.9), -60)      # the silent clip stays silent

    def test_no_ffmpeg_gives_silent_with_flag(self):
        out = f"{self.tmp.name}/silent.mp4"
        p = self.project()
        self.assertTrue(p.export_project(out, "540p (Proxy)", 30, ffmpeg_path=None))
        self.assertEqual(p.last_export_info["audio"], "skipped_no_ffmpeg")
        self.assertEqual(list(self.probe(out)), ["video"])

    def test_wav_export_and_errors(self):
        p = self.project()
        out = f"{self.tmp.name}/o.wav"
        self.assertTrue(p.export_project(out, ffmpeg_path=FF))
        self.assertFalse(p.export_project(f"{self.tmp.name}/o2.wav", ffmpeg_path=None))
        self.assertEqual(p.last_export_info["error"], "ffmpeg_required")

    def test_cancel_removes_partial_file(self):
        out = f"{self.tmp.name}/c.mp4"
        n = [0]
        def cancel():
            n[0] += 1
            return n[0] > 3
        self.assertFalse(self.project().export_project(out, "540p (Proxy)", 30, cancel_check=cancel, ffmpeg_path=FF))
        self.assertFalse(os.path.exists(out))

    def test_clone_is_independent(self):
        p = self.project()
        c = p.clone_for_export()
        c.tracks[0].clips.clear()
        self.assertTrue(p.tracks[0].clips)


if __name__ == "__main__":
    unittest.main()
