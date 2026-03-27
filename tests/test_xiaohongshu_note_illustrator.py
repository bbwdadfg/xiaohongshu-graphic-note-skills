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


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", chunks=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self._chunks = chunks or [b"chunk"]

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def iter_content(self, chunk_size=8192):
        del chunk_size
        for chunk in self._chunks:
            yield chunk


class XiaohongshuNoteIllustratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            ROOT / "xiaohongshu-note-illustrator" / "scripts" / "generate_note_images.py",
            "test_xiaohongshu_note_illustrator_module",
        )
        cls.note = {
            "笔记标题": "OpenMAIC 很值得看",
            "图片规划": [
                {
                    "图片角色": "cover",
                    "图片用途": "封面",
                    "版式类型": "总览拆解版",
                    "卡片标题": "这工具为什么值得看",
                    "卡片副标题": "先看懂主题",
                    "卡片编号": "01/03",
                    "主视觉说明": "一个大的总览图",
                    "画面模块": [
                        {"模块类型": "主视觉", "模块标题": "总览", "要点": ["亮点一"], "强调": "居中"},
                        {"模块类型": "模块", "模块标题": "先看", "要点": ["亮点二"], "强调": "左侧"},
                    ],
                    "模块关系": ["总览 -> 先看"],
                    "记忆句": "先抓主线",
                    "配图元素": ["书本", "箭头"],
                    "画面描述": "图1",
                    "生图提示词": "prompt one",
                    "比例": "3:4",
                },
                {
                    "图片角色": "insight",
                    "图片用途": "观点",
                    "版式类型": "机制原理版",
                    "卡片标题": "核心拆解",
                    "卡片副标题": "看清关键机制",
                    "卡片编号": "02/03",
                    "主视觉说明": "一个机制主图",
                    "画面模块": [
                        {"模块类型": "主视觉", "模块标题": "机制图", "要点": ["主图"], "强调": "居中"},
                        {"模块类型": "步骤", "模块标题": "亮点", "要点": ["要点一"], "强调": "箭头"},
                    ],
                    "模块关系": ["机制图 -> 亮点"],
                    "记忆句": "抓住差异",
                    "配图元素": ["放大镜"],
                    "画面描述": "图2",
                    "生图提示词": "prompt two",
                    "比例": "4:5",
                },
                {
                    "图片角色": "scenario",
                    "图片用途": "场景",
                    "版式类型": "流程步骤版",
                    "卡片标题": "应用步骤",
                    "卡片副标题": "别只看热闹",
                    "卡片编号": "03/03",
                    "主视觉说明": "一个步骤链路",
                    "画面模块": [
                        {"模块类型": "步骤", "模块标题": "步骤一", "要点": ["先准备"], "强调": "起点"},
                        {"模块类型": "步骤", "模块标题": "步骤二", "要点": ["再执行"], "强调": "中段"},
                        {"模块类型": "误区", "模块标题": "避坑", "要点": ["别漏配置"], "强调": "红框"},
                    ],
                    "模块关系": ["步骤一 -> 步骤二", "流程 -> 避坑"],
                    "记忆句": "去落地",
                    "配图元素": ["清单"],
                    "画面描述": "图3",
                    "生图提示词": "prompt three",
                    "比例": "4:5",
                },
            ],
        }

    def test_build_generation_jobs_creates_three_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = self.module.build_generation_jobs(self.note, temp_dir)
        self.assertEqual(len(jobs), 3)
        self.assertTrue(jobs[0]["path"].endswith(".png"))
        self.assertEqual(jobs[0]["图片角色"], "cover")
        self.assertEqual(jobs[0]["plan_item"]["卡片标题"], "这工具为什么值得看")
        self.assertEqual(jobs[1]["plan_item"]["版式类型"], "机制原理版")
        self.assertEqual(jobs[0]["prompt"], "prompt one")

    def test_generate_images_skips_existing_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = self.module.build_generation_jobs(self.note, temp_dir)
            existing_path = Path(jobs[0]["path"])
            existing_path.parent.mkdir(parents=True, exist_ok=True)
            existing_path.write_bytes(b"existing")
            with patch.object(self.module, "_generate_with_replicate", return_value={"render_engine": "replicate"}) as mock_generate:
                results = self.module.generate_images(self.note, temp_dir, force=False)
        self.assertEqual(results[0]["status"], "skipped")
        self.assertEqual(results[1]["status"], "generated")
        self.assertEqual(mock_generate.call_count, 2)

    def test_generate_images_regenerates_empty_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            jobs = self.module.build_generation_jobs(self.note, temp_dir)
            existing_path = Path(jobs[0]["path"])
            existing_path.parent.mkdir(parents=True, exist_ok=True)
            existing_path.write_bytes(b"")

            def fake_generate(job, config, output_path):
                del job, config
                Path(output_path).write_bytes(b"fresh")
                return {"render_engine": "replicate", "prediction_id": "pred"}

            with patch.object(self.module, "_generate_with_replicate", side_effect=fake_generate) as mock_generate:
                results = self.module.generate_images(self.note, temp_dir, force=False)
        self.assertEqual(results[0]["status"], "generated")
        self.assertEqual(mock_generate.call_count, 3)

    def test_decorate_prompt_builds_knowledge_card_prompt(self):
        config = self.module.load_config()
        prompt = self.module.decorate_prompt(
            {
                "比例": "3:4",
                "版式类型": "机制原理版",
                "卡片标题": "圆的认识",
                "卡片副标题": "先理解定义和特征",
                "主视觉说明": "画一个圆形主图",
                "画面模块": [{"模块类型": "主视觉", "模块标题": "定义", "要点": ["到定点距离相等的点集合"], "强调": "居中"}],
                "模块关系": ["定义 -> 特征"],
                "记忆句": "先记定义，再记关系",
                "配图元素": ["圆形", "箭头"],
            },
            config,
        )
        self.assertIn("请生成 1 张 3:4 竖版学科笔记图", prompt)
        self.assertIn("圆的认识", prompt)
        self.assertIn("机制原理版", prompt)
        self.assertIn("知识图解", prompt)
        self.assertIn("所有中文文字都必须由模型直接生成", prompt)
        self.assertIn("不能后期代码叠字", prompt)

    def test_decorate_prompt_returns_base_when_present(self):
        prompt = self.module.decorate_prompt({"生图提示词": "custom prompt"}, {"prompt_suffix": ""})
        self.assertEqual(prompt, "custom prompt")

    def test_load_note_payload_supports_multiple_shapes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            payload_paths = {
                "data": temp_dir_path / "data.json",
                "note": temp_dir_path / "note.json",
                "direct": temp_dir_path / "direct.json",
            }
            payload_paths["data"].write_text(json.dumps({"data": self.note}, ensure_ascii=False), encoding="utf-8")
            payload_paths["note"].write_text(json.dumps({"note": {"data": self.note}}, ensure_ascii=False), encoding="utf-8")
            payload_paths["direct"].write_text(json.dumps(self.note, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(self.module._load_note_payload(str(payload_paths["data"]))["笔记标题"], self.note["笔记标题"])
            self.assertEqual(self.module._load_note_payload(str(payload_paths["note"]))["笔记标题"], self.note["笔记标题"])
            self.assertEqual(self.module._load_note_payload(str(payload_paths["direct"]))["笔记标题"], self.note["笔记标题"])

            bad_path = temp_dir_path / "bad.json"
            bad_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.module._load_note_payload(str(bad_path))

    def test_decorate_prompt_raises_without_any_prompt(self):
        prompt = self.module.decorate_prompt({"图片角色": "cover", "比例": "4:5", "版式类型": "总览拆解版"}, self.module.load_config())
        self.assertIn("4:5", prompt)

    def test_replicate_api_token_prefers_env_and_config(self):
        with patch.dict(self.module.os.environ, {"REPLICATE_API_TOKEN": "env-token"}, clear=True):
            token = self.module._replicate_api_token({})
        self.assertEqual(token, "env-token")
        self.assertEqual(self.module._replicate_api_token({"replicate_api_token": "cfg-token"}), "cfg-token")

    def test_generate_images_raises_without_api_key(self):
        with patch.dict(self.module.os.environ, {}, clear=True), patch.object(
            self.module,
            "load_config",
            return_value={
                "render_engine": "replicate",
                "model": "google/nano-banana-pro",
                "default_output_format": "png",
                "default_resolution": "2K",
                "prompt_suffix": "",
            },
        ):
            with self.assertRaises(ValueError):
                job = self.module.build_generation_jobs(self.note, "/tmp/nope")[0]
                self.module._generate_with_replicate(job, self.module.load_config(), Path("/tmp/nope.png"))

    def test_generate_images_rejects_non_replicate_render_engine(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(
            self.module,
            "load_config",
            return_value={
                "render_engine": "local_knowledge_card",
                "replicate_api_token": "token",
                "model": "google/nano-banana-pro",
                "default_output_format": "png",
                "default_resolution": "2K",
                "prompt_suffix": "",
            },
        ):
            with self.assertRaises(ValueError):
                self.module.generate_images(self.note, temp_dir, force=True)

    def test_replicate_create_prediction_and_wait_output(self):
        with patch.object(self.module.requests, "post", return_value=FakeResponse(status_code=201, payload={"id": "pred_1"})):
            prediction_id = self.module._replicate_create_prediction("token", "model", "prompt", "3:4", "png", "2K")
        self.assertEqual(prediction_id, "pred_1")

        with patch.object(self.module.requests, "get", return_value=FakeResponse(payload={"status": "succeeded", "output": ["https://example.com/a.png"]})), patch.object(self.module.time, "time", side_effect=[0, 0]):
            image_url = self.module._replicate_wait_output("token", "pred_1", timeout_s=10)
        self.assertEqual(image_url, "https://example.com/a.png")

        with patch.object(self.module.requests, "get", return_value=FakeResponse(payload={"status": "succeeded", "output": "https://example.com/b.png"})), patch.object(self.module.time, "time", side_effect=[0, 0]):
            image_url = self.module._replicate_wait_output("token", "pred_1", timeout_s=10)
        self.assertEqual(image_url, "https://example.com/b.png")

        with patch.object(self.module.requests, "get", return_value=FakeResponse(payload={"status": "succeeded", "output": []})), patch.object(self.module.time, "time", side_effect=[0, 0]):
            with self.assertRaises(RuntimeError):
                self.module._replicate_wait_output("token", "pred_1", timeout_s=10)

    def test_replicate_wait_output_failure_and_timeout(self):
        with patch.object(self.module.requests, "get", return_value=FakeResponse(payload={"status": "failed", "error": "boom"})), patch.object(self.module.time, "time", side_effect=[0, 0]):
            with self.assertRaises(RuntimeError):
                self.module._replicate_wait_output("token", "pred_1", timeout_s=10)

        with patch.object(self.module.time, "time", side_effect=[0, 1]):
            with self.assertRaises(TimeoutError):
                self.module._replicate_wait_output("token", "pred_1", timeout_s=0)

    def test_download_image_writes_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "image.png"
            with patch.object(self.module.requests, "get", return_value=FakeResponse(chunks=[b"a", b"b"])):
                self.module.download_image("https://example.com/a.png", str(out_path))
            self.assertEqual(out_path.read_bytes(), b"ab")

    def test_ensure_nonempty_image_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "empty.png"
            out_path.write_bytes(b"")
            with self.assertRaises(RuntimeError):
                self.module._ensure_nonempty_image(out_path)
            self.assertFalse(out_path.exists())

    def test_main_success_and_error_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "note.json"
            out_path = Path(temp_dir) / "result.json"
            input_path.write_text(json.dumps(self.note, ensure_ascii=False), encoding="utf-8")
            with patch.object(self.module, "generate_images", return_value=[{"path": "/tmp/x.png"}]), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--input", str(input_path), "--out-dir", temp_dir, "--out", str(out_path)])
            self.assertEqual(code, 0)
            self.assertTrue(out_path.exists())
            self.assertIn("/tmp/x.png", stdout.getvalue())

            with patch.object(self.module, "generate_images", side_effect=RuntimeError("boom")), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--input", str(input_path), "--out-dir", temp_dir])
            self.assertEqual(code, 1)
            self.assertIn("boom", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
