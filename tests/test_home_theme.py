# -*- coding: utf-8 -*-
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from video_studio import StudioAppController  # noqa: E402
from video_studio_core import VideoStudioProject  # noqa: E402
from video_studio_i18n import TRANSLATIONS, tr  # noqa: E402
from video_studio_theme import ACCENT_COLORS, BASE_PALETTES, build_stylesheet, get_effective_palette, mix_colors  # noqa: E402


class TestHomeKeys(unittest.TestCase):
    def test_every_key_used_by_home_module_exists_in_both_languages(self):
        src = (PROJECT_ROOT / "video_studio_home.py").read_text(encoding="utf-8")
        keys = set(re.findall(r'tr\(\s*"([a-z_0-9:]+)"', src))
        keys |= {f"home_new_{i}" for i in range(1, 7)} | {f"home_tip_{i}" for i in range(1, 5)}
        keys |= {f"home_age_{u}" for u in ("now", "min", "hour", "day", "week", "month", "year")}
        keys |= {f"home_ar_{k}" for k in ("16:9", "9:16", "1:1", "4:5")}
        for k in keys:
            self.assertIn(k, TRANSLATIONS, k)
            self.assertTrue(TRANSLATIONS[k][0] and TRANSLATIONS[k][1], k)

    def test_format_placeholders_match_between_languages(self):
        for k, (ar, en) in TRANSLATIONS.items():
            self.assertEqual(sorted(re.findall(r"\{(\w+)\}", ar)), sorted(re.findall(r"\{(\w+)\}", en)), k)


class TestThemeRefresh(unittest.TestCase):
    def test_mix_colors(self):
        self.assertEqual(mix_colors("#000000", "#FFFFFF", 0.5), "#808080")
        self.assertEqual(mix_colors("#102030", "#FFFFFF", 0.0), "#102030")

    def test_all_theme_accent_combinations_render_a_complete_stylesheet(self):
        for mode in BASE_PALETTES:
            for acc in ACCENT_COLORS:
                pal = get_effective_palette(mode, acc)
                for k in ("accent_soft", "accent_border", "hover_bg", "text_disabled"):
                    self.assertRegex(pal[k], r"^#[0-9A-F]{6}$", k)
                qss = build_stylesheet(pal)
                self.assertNotIn("${", qss)  # every token substituted
                self.assertEqual(qss.count("{"), qss.count("}"))
                for needle in ("QScrollBar", "QSlider", "QProgressBar", "QMenu", "QToolTip", "ProjectCard", "BigAccent", "QComboBox QAbstractItemView"):
                    self.assertIn(needle, qss)


class TestControllerProjects(unittest.TestCase):
    def test_open_project_file_records_recent_and_keeps_old_project_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            c = StudioAppController(tmp_path / "data")
            proj = VideoStudioProject(name="Cover Reel", aspect_ratio="9:16")
            f = tmp_path / "reel.hvsp"
            proj.save_project_file(str(f))
            self.assertTrue(c.open_cli_file(str(f)))
            self.assertEqual(c.project.name, "Cover Reel")
            self.assertEqual(c.project.aspect_ratio, "9:16")
            ents = c.recents.entries()
            self.assertEqual([e["name"] for e in ents], ["Cover Reel"])
            self.assertEqual(ents[0]["aspect"], "9:16")
            self.assertTrue(c.current_project_path.endswith("reel.hvsp"))

            keep = c.project
            bad = tmp_path / "bad.hvsp"
            bad.write_text("{broken", encoding="utf-8")
            with self.assertRaises(Exception):
                c.open_project_file(str(bad))
            self.assertIs(c.project, keep)  # a corrupt file never replaces the open project


if __name__ == "__main__":
    unittest.main()
