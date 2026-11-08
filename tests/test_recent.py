# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(os.path.abspath(__file__)).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from video_studio_recent import MAX_RECENT_ITEMS, RecentProjects, age_parts, format_duration, summarize_project  # noqa: E402


def _proj(name="P", aspect="9:16", clips=((0, 5), (3, 4))):
    cl = [SimpleNamespace(timeline_start=s, duration=d) for s, d in clips]
    return SimpleNamespace(name=name, aspect_ratio=aspect, fps=30, tracks=[SimpleNamespace(clips=cl), SimpleNamespace(clips=[])])


class TestRecent(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _file(self, name):
        p = self.dir / name
        p.write_text("{}", encoding="utf-8")
        return str(p)

    def test_summary_and_formats(self):
        s = summarize_project(_proj())
        self.assertEqual((s["aspect"], s["clips"], s["tracks"], s["duration"]), ("9:16", 2, 2, 7.0))
        self.assertEqual(format_duration(7), "0:07")
        self.assertEqual(format_duration(3725), "1:02:05")
        self.assertEqual(age_parts(10), ("now", 0))
        self.assertEqual(age_parts(3 * 3600 + 5), ("hour", 3))
        self.assertEqual(age_parts(86400 * 40), ("month", 1))

    def test_record_order_pin_persist(self):
        rp = RecentProjects(self.dir)
        a, b = self._file("a.hvsp"), self._file("b.hvsp")
        rp.record(a, _proj("A"), now=100)
        rp.record(b, _proj("B"), now=200)
        self.assertEqual([e["name"] for e in rp.entries()], ["B", "A"])
        rp.record(a, _proj("A2"), now=300)  # re-open moves to top, no duplicate
        self.assertEqual([e["name"] for e in rp.entries()], ["A2", "B"])
        self.assertTrue(rp.toggle_pin(b))
        self.assertEqual([e["name"] for e in rp.entries()], ["B", "A2"])
        again = RecentProjects(self.dir)  # persisted
        self.assertEqual([e["name"] for e in again.entries()], ["B", "A2"])
        self.assertTrue(again.entries()[0]["pinned"])

    def test_missing_files_hidden_and_remove(self):
        rp = RecentProjects(self.dir)
        a = self._file("a.hvsp")
        rp.record(a, _proj("A"))
        rp.record(str(self.dir / "gone.hvsp"), _proj("G"))
        self.assertEqual([e["name"] for e in rp.entries()], ["A"])
        self.assertTrue(rp.remove(a))
        self.assertFalse(rp.remove(a))
        self.assertEqual(rp.entries(), [])

    def test_trim_keeps_pinned(self):
        rp = RecentProjects(self.dir)
        first = self._file("p0.hvsp")
        rp.record(first, _proj("P0"), now=1)
        rp.toggle_pin(first)
        for i in range(1, MAX_RECENT_ITEMS + 5):
            rp.record(self._file(f"p{i}.hvsp"), _proj(f"P{i}"), now=1 + i)
        self.assertEqual(len(rp.items), MAX_RECENT_ITEMS)
        self.assertIn("P0", [e["name"] for e in rp.items])

    def test_corrupt_file_is_survivable(self):
        (self.dir / "recent_projects.json").write_text("{not json", encoding="utf-8")
        rp = RecentProjects(self.dir)
        self.assertEqual(rp.entries(), [])
        rp.record(self._file("a.hvsp"), _proj("A"))
        self.assertEqual(len(RecentProjects(self.dir).entries()), 1)


if __name__ == "__main__":
    unittest.main()
