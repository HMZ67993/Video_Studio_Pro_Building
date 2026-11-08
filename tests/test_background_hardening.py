import ast
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from video_studio_core import TimelineClip, VideoStudioProject
from video_studio_store import FALLBACK_PRODUCTS, load_cached_products_catalog

ROOT = Path(__file__).resolve().parents[1]


class TestBackgroundHardening(unittest.TestCase):
    def test_preview_uses_proxy_but_final_frame_read_uses_original(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = root / "original.avi"
            proxy = root / "proxy.avi"
            for filename, color in ((original, (0, 0, 220)), (proxy, (220, 0, 0))):
                writer = cv2.VideoWriter(str(filename), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (80, 60))
                if not writer.isOpened():
                    self.skipTest("OpenCV MJPG VideoWriter is unavailable")
                writer.write(np.full((60, 80, 3), color, np.uint8))
                writer.release()

            project = VideoStudioProject()
            clip = TimelineClip(
                name="video", clip_type="video", source_path=str(original), proxy_path=str(proxy),
                duration=0.1, source_out=0.1,
            )
            project.tracks[0].clips.append(clip)

            full_quality = project._read_clip_source_frame(clip, 0.0, 80, 60, use_proxy=False)
            preview = project._read_clip_source_frame(clip, 0.0, 80, 60, use_proxy=True)
            self.assertGreater(float(full_quality[:, :, 2].mean()), float(full_quality[:, :, 0].mean()))
            self.assertGreater(float(preview[:, :, 0].mean()), float(preview[:, :, 2].mean()))

    def test_proxy_generation_is_cached_and_background_callable(self):
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("FFmpeg is unavailable")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.avi"
            writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"MJPG"), 15.0, (160, 120))
            if not writer.isOpened():
                self.skipTest("OpenCV MJPG VideoWriter is unavailable")
            for i in range(8):
                frame = np.full((120, 160, 3), i * 20, np.uint8)
                writer.write(frame)
            writer.release()

            project = VideoStudioProject()
            clip = TimelineClip(name="proxy", clip_type="video", source_path=str(source), duration=8 / 15, source_out=8 / 15)
            project.tracks[0].clips.append(clip)
            out = project.generate_proxy_for_clip(clip.id, root / "proxies", ffmpeg_path=ffmpeg)
            self.assertIsNotNone(out)
            self.assertTrue(out.is_file())
            self.assertEqual(clip.proxy_path, str(out))

            before = out.stat().st_mtime_ns
            out_again = project.generate_proxy_for_clip(clip.id, root / "proxies", ffmpeg_path=ffmpeg)
            self.assertEqual(out_again, out)
            self.assertEqual(out.stat().st_mtime_ns, before)

            # A different source path with identical bytes/mtime must not reuse a
            # proxy generated for the previous file after relinking a clip.
            second_source = root / "second_source.avi"
            import shutil as _shutil
            _shutil.copy2(source, second_source)
            clip.source_path = str(second_source)
            second_proxy = project.generate_proxy_for_clip(clip.id, root / "proxies", ffmpeg_path=ffmpeg)
            self.assertIsNotNone(second_proxy)
            self.assertNotEqual(second_proxy, out)
            self.assertTrue(second_proxy.is_file())

    def test_cache_only_store_load_does_not_make_network_request(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("video_studio_store.urllib.request.urlopen", side_effect=AssertionError("network call")):
                products, is_live = load_cached_products_catalog(Path(td))
            self.assertFalse(is_live)
            self.assertEqual(products, FALLBACK_PRODUCTS)

    def test_editor_panels_and_timeline_are_imported_only_by_lazy_builder(self):
        tree = ast.parse((ROOT / "video_studio.py").read_text(encoding="utf-8"))
        main_window = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "VideoStudioMainWindow"
        )
        methods = {node.name: node for node in main_window.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        lazy_builder = ast.unparse(methods["_build_editor_ui_body"])
        home_builder = ast.unparse(methods["_build_ui"])
        self.assertIn("video_studio_panels", lazy_builder)
        self.assertIn("video_studio_timeline", lazy_builder)
        self.assertNotIn("video_studio_panels", home_builder)
        self.assertNotIn("video_studio_timeline", home_builder)


    def test_preview_paint_event_never_decodes_synchronously(self):
        timeline = ast.parse((ROOT / "video_studio_timeline.py").read_text(encoding="utf-8"))
        canvas = next(node for node in ast.walk(timeline) if isinstance(node, ast.ClassDef) and node.name == "PreviewCanvasWidget")
        methods = {node.name: node for node in canvas.body if isinstance(node, ast.FunctionDef)}
        paint = ast.unparse(methods["paintEvent"])
        self.assertNotIn("sync=True", paint)
        self.assertIn("self.refresh_frame()", paint)

    def test_preview_worker_deserializes_project_snapshot_once(self):
        timeline = ast.parse((ROOT / "video_studio_timeline.py").read_text(encoding="utf-8"))
        worker = next(node for node in ast.walk(timeline) if isinstance(node, ast.ClassDef) and node.name == "_FrameWorker")
        run_method = next(node for node in worker.body if isinstance(node, ast.FunctionDef) and node.name == "_run")
        self.assertEqual(ast.unparse(run_method).count("load_from_json_string"), 1)

    def test_ai_worker_is_registered_with_application_shutdown(self):
        panels = ast.parse((ROOT / "video_studio_panels.py").read_text(encoding="utf-8"))
        main = ast.parse((ROOT / "video_studio.py").read_text(encoding="utf-8"))
        ai_class = next(node for node in ast.walk(panels) if isinstance(node, ast.ClassDef) and node.name == "AIJobThread")
        ai_methods = {node.name: node for node in ai_class.body if isinstance(node, ast.FunctionDef)}
        self.assertIn("cancel", ai_methods)
        browser = next(node for node in ast.walk(panels) if isinstance(node, ast.ClassDef) and node.name == "BrowserPanel")
        start_method = next(node for node in browser.body if isinstance(node, ast.FunctionDef) and node.name == "_ai_start")
        self.assertIn("register_background_worker", ast.unparse(start_method))
        window = next(node for node in ast.walk(main) if isinstance(node, ast.ClassDef) and node.name == "VideoStudioMainWindow")
        methods = {node.name: node for node in window.body if isinstance(node, ast.FunctionDef)}
        self.assertIn("_track_qt_worker", ast.unparse(methods["register_background_worker"]))
        self.assertIn("_LIVE_QT_WORKERS", ast.unparse(methods["closeEvent"]))

    def test_runtime_stabilization_cache_path_survives_export_clone(self):
        project = VideoStudioProject()
        project.stabilization_cache_dir = Path("custom") / "stabilization"
        clone = project.clone_for_export()
        self.assertEqual(clone.stabilization_cache_dir, project.stabilization_cache_dir)


if __name__ == "__main__":
    unittest.main()
