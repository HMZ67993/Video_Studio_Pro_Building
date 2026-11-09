"""Regression tests for optional AI panel dialog dependencies."""
import ast
from pathlib import Path


def test_ai_panel_imports_qinputdialog_used_by_whisper_and_tracking():
    source = Path(__file__).parents[1].joinpath("video_studio_panels.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_widgets = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "PyQt6.QtWidgets"
        for alias in node.names
    }
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "QInputDialog" in imported_widgets
    assert "QInputDialog" in used_names
