#!/usr/bin/env python3
"""Print APP_VERSION for build.bat. `--four` prints a 4-part version (1.2.3 -> 1.2.3.0) for Windows file info."""
import re
import sys
from pathlib import Path

text = (Path(__file__).resolve().parent.parent / "video_studio_i18n.py").read_text(encoding="utf-8")
m = re.search(r'^APP_VERSION\s*=\s*"(\d+(?:\.\d+){0,3})"', text, re.MULTILINE)
if not m:
    sys.exit("APP_VERSION not found")
parts = m.group(1).split(".")
if "--four" in sys.argv:
    parts = (parts + ["0"] * 4)[:4]
print(".".join(parts))
