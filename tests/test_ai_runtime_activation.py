"""Tests for activation/validation of the optional per-user AI runtime."""
from pathlib import Path
from unittest.mock import patch

import video_studio_ai_runtime as runtime


def test_runtime_marker_without_required_packages_is_not_accepted(tmp_path):
    root = tmp_path / "ai_runtime"
    root.mkdir()
    (root / ".hmz_ai_runtime_ready").write_text("ai-runtime", encoding="utf-8")
    with patch.object(runtime, "runtime_dir", return_value=root):
        assert runtime.activate_runtime() is False


def test_runtime_activation_adds_root_to_path_and_is_idempotent(tmp_path):
    root = tmp_path / "ai_runtime"
    (root / "faster_whisper").mkdir(parents=True)
    (root / "ctranslate2").mkdir()
    (root / "faster_whisper" / "__init__.py").write_text("", encoding="utf-8")
    (root / "ctranslate2" / "__init__.py").write_text("", encoding="utf-8")
    (root / ".hmz_ai_runtime_ready").write_text("ai-runtime", encoding="utf-8")
    root_s = str(root)
    with patch.object(runtime, "runtime_dir", return_value=root):
        original = list(runtime.sys.path)
        try:
            assert runtime.activate_runtime() is True
            assert runtime.activate_runtime() is True
            assert runtime.sys.path.count(root_s) == 1
        finally:
            runtime.sys.path[:] = original



def test_windows_build_explicitly_bundles_asyncio_for_lazy_ai_imports():
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    source = (root / "video_studio.py").read_text(encoding="utf-8")
    requirements = (root / "requirements-ai.txt").read_text(encoding="utf-8")
    assert "--include-package=asyncio" in workflow
    assert "import asyncio" in source
    assert "huggingface-hub>=0.13,<1.0" in requirements


def test_ai_runtime_workflow_smoke_tests_optional_runtime_imports():
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")
    assert "import asyncio, faster_whisper, ctranslate2, onnxruntime" in workflow
