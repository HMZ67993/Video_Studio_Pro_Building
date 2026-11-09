"""Regression tests for AI model directory layout and Whisper error reporting."""
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from video_studio_plugins import (
    AIError,
    AIPluginRegistry,
    WhisperAutoCaptionsPlugin,
    get_ai_models_dir,
)


def test_models_dir_is_idempotent_for_app_and_models_roots():
    with tempfile.TemporaryDirectory() as tmp:
        app_root = Path(tmp) / "HMZVideoStudioPro"
        expected = app_root / "ai_models"
        assert get_ai_models_dir(app_root) == expected
        assert get_ai_models_dir(expected) == expected


def test_registry_and_plugins_share_one_models_directory():
    with tempfile.TemporaryDirectory() as tmp:
        app_root = Path(tmp) / "HMZVideoStudioPro"
        registry = AIPluginRegistry(models_dir=app_root)
        assert registry.models_dir == app_root / "ai_models"
        for plugin in registry.list_plugins():
            assert plugin.models_dir == registry.models_dir
        whisper = registry.get_plugin("ai_whisper_captions")
        assert whisper.model_dir == app_root / "ai_models" / "whisper_base"


def test_legacy_nested_models_are_migrated_without_overwrite():
    with tempfile.TemporaryDirectory() as tmp:
        app_root = Path(tmp) / "HMZVideoStudioPro"
        models = app_root / "ai_models"
        legacy = models / "ai_models"
        legacy.mkdir(parents=True)
        (legacy / "u2net_human_seg.onnx").write_bytes(b"legacy-model")
        (models / "keep.bin").write_bytes(b"current")
        assert get_ai_models_dir(app_root) == models
        assert (models / "u2net_human_seg.onnx").read_bytes() == b"legacy-model"
        assert (models / "keep.bin").read_bytes() == b"current"
        assert not legacy.exists()


def test_whisper_dependency_error_is_preserved_in_ai_error():
    with tempfile.TemporaryDirectory() as tmp:
        plugin = WhisperAutoCaptionsPlugin(models_dir=Path(tmp))
        detail = "faster-whisper / ctranslate2 (ImportError: DLL load failed: missing dependency)"
        with patch.object(plugin, "dependency_error", return_value="missing_dependency:" + detail):
            with pytest.raises(AIError) as caught:
                plugin._load()
        assert caught.value.reason == "missing_dependency"
        assert detail in caught.value.detail


def test_whisper_model_loader_failure_includes_exception_type_and_message():
    with tempfile.TemporaryDirectory() as tmp:
        plugin = WhisperAutoCaptionsPlugin(models_dir=Path(tmp))
        fake_module = types.ModuleType("faster_whisper")

        def fail_model(*_args, **_kwargs):
            raise OSError("model cache is not writable")

        fake_module.WhisperModel = fail_model
        with patch.object(plugin, "dependency_error", return_value=""):
            with patch.dict(sys.modules, {"faster_whisper": fake_module}):
                with pytest.raises(AIError) as caught:
                    plugin._load()
        assert caught.value.reason == "model_failed"
        assert "OSError" in caught.value.detail
        assert "model cache is not writable" in caught.value.detail


def test_whisper_model_dir_uses_selected_size_under_canonical_root():
    with tempfile.TemporaryDirectory() as tmp:
        plugin = WhisperAutoCaptionsPlugin(models_dir=Path(tmp))
        plugin.model_size = "tiny"
        assert plugin.model_dir == Path(tmp) / "ai_models" / "whisper_tiny"
