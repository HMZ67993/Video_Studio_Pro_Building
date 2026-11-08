# -*- coding: utf-8 -*-
import json
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

import video_studio as vs  # noqa: E402
from video_studio_core import TextStyleSettings  # noqa: E402
from video_studio_guide import get_guide_sections  # noqa: E402
from video_studio_i18n import TRANSLATIONS, tr  # noqa: E402
from video_studio_text import render_text_layer  # noqa: E402


class TestCrashLog(unittest.TestCase):
    def test_redaction(self):
        raw = "license_key=abcdef123 VSP1-eyJh.sig_AAA token: XYZ 1a2b3c4d-1a2b3c4d-1a2b3c4d-1a2b3c4d " + "A" * 60
        out = vs.redact_sensitive(raw)
        for bad in ("abcdef123", "VSP1-eyJh", "XYZ", "1a2b3c4d-", "A" * 40):
            self.assertNotIn(bad, out)

    def test_log_written_with_ref_and_trim(self):
        with tempfile.TemporaryDirectory() as d:
            try:
                raise ValueError("license_key=SECRETVALUE boom")
            except ValueError:
                p = vs.write_crash_log(*sys.exc_info(), custom_dir=Path(d))
            text = p.read_text(encoding="utf-8")
            self.assertIn("ref ", text)
            self.assertIn("Python:", text)
            self.assertNotIn("SECRETVALUE", text)
            for _ in range(400):
                try:
                    raise RuntimeError("x" * 1000)
                except RuntimeError:
                    vs.write_crash_log(*sys.exc_info(), custom_dir=Path(d))
            self.assertLessEqual(p.stat().st_size, vs.MAX_CRASH_LOG_BYTES)


class TestSettings(unittest.TestCase):
    def test_corrupt_recovery_and_atomic_save(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "settings.json").write_text("{not json", encoding="utf-8")
            s = vs.SettingsManager(Path(d))
            self.assertEqual(s.data["lang"], "ar")
            self.assertTrue(list(Path(d).glob("settings.corrupt-*.json")))
            s.data["lang"] = "en"
            s.save()
            self.assertEqual(json.loads((Path(d) / "settings.json").read_text(encoding="utf-8"))["lang"], "en")
            self.assertFalse(list(Path(d).glob("*.tmp")))

    def test_non_object_root(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "settings.json").write_text("[1,2]", encoding="utf-8")
            self.assertEqual(vs.SettingsManager(Path(d)).data["theme"], "dark")


class TestLicenseMessages(unittest.TestCase):
    def test_all_statuses_have_text(self):
        for st in ("ok", "invalid", "product", "device", "expired", "disabled", "network_error", "not_yet_valid", "not_configured", "integrity", "weird"):
            key = vs.license_message_key(st)
            self.assertIn(key, TRANSLATIONS)
            self.assertTrue(tr(key, "ar") and tr(key, "en"))


class TestTextEngine(unittest.TestCase):
    def test_features_change_output(self):
        base = TextStyleSettings(text="Hello مرحبا")
        _, a0 = render_text_layer(base, 400, 200)
        self.assertGreater(a0.max(), 0)
        variants = [
            dict(shadow_enabled=True), dict(glow_enabled=True), dict(stroke_width=12), dict(bg_enabled=True),
            dict(reflection_enabled=True), dict(font_size=base.font_size + 30), dict(underline=True),
        ]
        for v in variants:
            ts = TextStyleSettings(text="Hello مرحبا", **v)
            _, a = render_text_layer(ts, 400, 200)
            self.assertFalse((a.shape == a0.shape) and (a == a0).all(), f"{v} had no visible effect")

    def test_letter_spacing_latin_only(self):
        _, a0 = render_text_layer(TextStyleSettings(text="Hello"), 400, 200)
        _, a1 = render_text_layer(TextStyleSettings(text="Hello", letter_spacing=8), 400, 200)
        self.assertFalse(a0.shape == a1.shape and (a0 == a1).all())
        _, b0 = render_text_layer(TextStyleSettings(text="مرحبا"), 400, 200)
        _, b1 = render_text_layer(TextStyleSettings(text="مرحبا", letter_spacing=8), 400, 200)
        self.assertTrue((b0 == b1).all())  # Arabic joining must not be broken by spacing

    def test_empty_and_multiline(self):
        render_text_layer(TextStyleSettings(text=""), 200, 100)
        _, a = render_text_layer(TextStyleSettings(text="a\nb\nc", align="center"), 300, 200)
        self.assertGreater(a.max(), 0)

    def test_animations(self):
        for anim in ("fade", "slide_up", "slide_down", "zoom", "typewriter"):
            ts = TextStyleSettings(text="Anim", animation_in=anim, animation_out="fade", animation_duration=0.5)
            for t in (0.0, 0.25, 1.0, 2.0):
                render_text_layer(ts, 300, 150, local_t=t, duration=2.0)


class TestGuide(unittest.TestCase):
    def test_guide_is_detailed(self):
        secs = get_guide_sections()
        self.assertGreaterEqual(len(secs), 25)
        total = sum(len(s["html_ar"]) + len(s["html_en"]) for s in secs)
        self.assertGreater(total, 20000)
        for s in secs:
            self.assertTrue(s["title_ar"] and s["title_en"] and s["html_ar"] and s["html_en"])


class TestDeveloperTools(unittest.TestCase):
    """Run keygen/issue/revoke/release/manifest on a copy so real sources stay untouched."""

    def run_tool(self, work, *args):
        r = subprocess.run([sys.executable, "-I", str(work / "tools" / "issue_serial.py"), *args], capture_output=True, text=True, cwd=work)
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return r.stdout.strip()

    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "app"
            shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("__pycache__", "keys", "state.json", "output", ".pytest_cache"))
            self.run_tool(work, "keygen")
            serial = self.run_tool(work, "issue", "--machine", "*", "--customer", "Test User", "--days", "30").splitlines()[-1]
            code = (
                "import sys,json;sys.path.insert(0,'.');import video_studio_license as L;"
                f"print(L.verify_manual_serial({serial!r})[0])"
            )
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=work).stdout.strip()
            self.assertEqual(out, "ok")
            # revoke -> signed list verifies and contains the jti
            self.run_tool(work, "revoke", "--serial", serial)
            doc = json.loads((work / "tools" / "output" / "update.json").read_text(encoding="utf-8"))
            code = (
                "import sys,json;sys.path.insert(0,'.');import video_studio_license as L;"
                "d=json.load(open('tools/output/update.json',encoding='utf-8'));print(len(L.verify_signed_revoked_list_or_none(d)))"
            )
            self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=work).stdout.strip(), "1")
            self.run_tool(work, "release", "--version", "2.0.0", "--url", "https://example.com/a.exe", "--sha256", "a" * 64, "--notes", "x")
            code = (
                "import sys,json;sys.path.insert(0,'.');import video_studio_license as L;"
                "d=json.load(open('tools/output/update.json',encoding='utf-8'));print(L.verify_signed_release(d)['version'])"
            )
            self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=work).stdout.strip(), "2.0.0")
            # manifest + integrity
            build = Path(d) / "dist"
            build.mkdir()
            (build / "App.exe").write_bytes(b"123")
            self.run_tool(work, "manifest", "--dir", str(build))
            code = (
                "import sys;sys.path.insert(0,'.');import video_studio_integrity as I;from pathlib import Path;"
                f"print(I.check_integrity(Path({str(build)!r}))[0])"
            )
            self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=work).stdout.strip(), "ok")
            (build / "App.exe").write_bytes(b"124")
            self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=work).stdout.strip(), "mismatch")

    def test_keygen_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "app"
            shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("__pycache__", "keys", "state.json", "output", ".pytest_cache"))
            self.run_tool(work, "keygen")
            r = subprocess.run([sys.executable, "-I", str(work / "tools" / "issue_serial.py"), "keygen"], capture_output=True, text=True, cwd=work)
            self.assertNotEqual(r.returncode, 0)

    def test_source_keys_untouched(self):
        self.assertFalse((ROOT / "tools" / "keys").exists(), "private keys must never be inside the deliverable")


if __name__ == "__main__":
    unittest.main()
