# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from video_studio import (  # noqa: E402
    HAS_PYQT6,
    MAX_CRASH_LOG_BYTES,
    StudioAppController,
    format_timecode_ltr,
    handle_remove_integrations,
    write_crash_log,
)
from video_studio_guide import get_guide_sections  # noqa: E402
from video_studio_i18n import TRANSLATIONS, tr  # noqa: E402
from video_studio_store import load_products_catalog  # noqa: E402
from video_studio_theme import ACCENT_COLORS, build_stylesheet, get_effective_palette  # noqa: E402


class TestUISmoke(unittest.TestCase):
    def test_bilingual_i18n_and_themes(self) -> None:
        for key, pair in TRANSLATIONS.items():
            self.assertEqual(len(pair), 2, f"Missing translation pair for {key}")
            self.assertTrue(len(pair[0]) > 0 and len(pair[1]) > 0)
        self.assertIn("تصدير", tr("btn_export", "ar"))
        self.assertIn("Export", tr("btn_export", "en"))

        for mode in ("dark", "light", "system"):
            for acc in ACCENT_COLORS:
                pal = get_effective_palette(mode, acc)
                qss = build_stylesheet(pal)
                self.assertIn("QComboBox QAbstractItemView", qss)
                self.assertIn("QCheckBox::indicator", qss)

    def test_guide_and_store_catalog_offline_fallback(self) -> None:
        sections = get_guide_sections()
        self.assertGreaterEqual(len(sections), 6)
        ids = [s["id"] for s in sections]
        self.assertIn("license", ids)
        self.assertIn("security", ids)

        with tempfile.TemporaryDirectory() as tmp:
            items, is_live = load_products_catalog(
                products_url="http://127.0.0.1:9/offline.json",
                gumroad_url="http://127.0.0.1:9/offline",
                custom_cache_dir=Path(tmp),
                timeout=0.2,
            )
            self.assertFalse(is_live)
            self.assertGreaterEqual(len(items), 3)

    def test_controller_and_crash_log_trimming(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            ctrl = StudioAppController(custom_data_dir=tmp_dir)
            self.assertEqual(ctrl.lang, "ar")
            self.assertEqual(ctrl.toggle_language(), "en")
            self.assertEqual(ctrl.toggle_language(), "ar")
            self.assertEqual(format_timecode_ltr(65.5, 30), "00:01:05:15")

            log_file = tmp_dir / "crash.log"
            log_file.write_bytes(b"X" * (MAX_CRASH_LOG_BYTES + 50000))
            try:
                raise RuntimeError("Simulated error for crash log test")
            except RuntimeError:
                write_crash_log(*sys.exc_info(), custom_dir=tmp_dir)
            self.assertLessEqual(log_file.stat().st_size, MAX_CRASH_LOG_BYTES)
            self.assertEqual(handle_remove_integrations(custom_dir=tmp_dir), 0)

    def test_timeline_has_working_horizontal_scrollbar(self) -> None:
        if not HAS_PYQT6:
            self.skipTest("PyQt6 is not installed")
        from PyQt6.QtWidgets import QApplication
        from video_studio_timeline import MultiTrackTimelineWidget

        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            controller = StudioAppController(custom_data_dir=Path(tmp))
            widget = MultiTrackTimelineWidget(controller, host=object())
            widget.resize(640, 210)
            widget.show()
            app.processEvents()

            self.assertGreater(widget.h_scrollbar.maximum(), 0)
            widget.h_scrollbar.setValue(widget.h_scrollbar.maximum())
            app.processEvents()
            self.assertGreater(widget.scroll_x, 0.0)
            self.assertAlmostEqual(widget.h_scrollbar.value() / 1000.0, widget.scroll_x, places=2)
            widget.close()


if __name__ == "__main__":
    unittest.main()
