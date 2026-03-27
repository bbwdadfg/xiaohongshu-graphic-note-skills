from __future__ import annotations

import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class XiaohongshuPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            ROOT / "xiaohongshu-graphic-note-pipeline" / "scripts" / "run_graphic_note_pipeline.py",
            "test_xiaohongshu_pipeline_module",
        )

    def test_run_pipeline_composes_child_skills(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(self.module.PARSER, "parse_source", return_value={"source_title": "A"}), patch.object(self.module.WRITER, "write_note", return_value=({"笔记标题": "标题", "图片规划": []}, {"prediction_id": "pred"})), patch.object(self.module.ILLUSTRATOR, "generate_images", return_value=[{"path": "/tmp/a.png"}]):
                payload = self.module.run_pipeline("https://example.com", None, None, temp_dir, skip_images=False)
        self.assertEqual(payload["source"]["source_title"], "A")
        self.assertEqual(payload["note"]["meta"]["prediction_id"], "pred")
        self.assertEqual(payload["images"][0]["path"], "/tmp/a.png")
        self.assertIsNone(payload["feishu"])

    def test_run_pipeline_can_skip_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(self.module.PARSER, "parse_source", return_value={"source_title": "A"}), patch.object(self.module.WRITER, "write_note", return_value=({"笔记标题": "标题", "图片规划": []}, {"prediction_id": "pred"})), patch.object(self.module.ILLUSTRATOR, "generate_images") as mock_images:
                payload = self.module.run_pipeline(None, "text", None, temp_dir, skip_images=True)
        self.assertEqual(payload["images"], [])
        mock_images.assert_not_called()

    def test_run_pipeline_can_publish_feishu(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(self.module.PARSER, "parse_source", return_value={"source_title": "A"}), patch.object(self.module.WRITER, "write_note", return_value=({"笔记标题": "标题", "图片规划": []}, {"prediction_id": "pred"})), patch.object(self.module.ILLUSTRATOR, "generate_images", return_value=[]), patch.object(self.module.PUBLISHER, "load_config", return_value={"table_id": "tbl"}), patch.object(self.module.PUBLISHER, "create_record", return_value={"record_id": "rec1"}):
                payload = self.module.run_pipeline("https://example.com", None, None, temp_dir, skip_images=False, publish_feishu=True)
        self.assertEqual(payload["feishu"]["record_id"], "rec1")

    def test_load_module_raises_on_missing_path(self):
        with self.assertRaises(FileNotFoundError):
            self.module._load_module("missing_mod", Path("/tmp/does-not-exist.py"))

    def test_main_success_and_error_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "payload.json"
            with patch.object(self.module, "run_pipeline", return_value={"ok": True}), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--text", "hello", "--out-dir", temp_dir, "--out", str(out_path)])
            self.assertEqual(code, 0)
            self.assertTrue(out_path.exists())
            self.assertEqual(json.loads(out_path.read_text(encoding="utf-8"))["ok"], True)
            self.assertIn('"ok": true', stdout.getvalue())

            with patch.object(self.module, "run_pipeline", side_effect=RuntimeError("boom")), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--text", "hello"])
            self.assertEqual(code, 1)
            self.assertIn("boom", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
