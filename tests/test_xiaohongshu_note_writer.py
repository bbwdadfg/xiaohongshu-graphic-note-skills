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
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class XiaohongshuNoteWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            ROOT / "xiaohongshu-note-writer" / "scripts" / "write_xiaohongshu_note.py",
            "test_xiaohongshu_note_writer_module",
        )
        cls.source = {
            "source_title": "OpenMAIC",
            "source_summary": "A new open-source AI benchmark.",
            "core_points": ["Point A", "Point B"],
            "news_angle": "为什么这个项目值得关注",
        }

    def test_build_prompt_mentions_three_image_roles(self):
        prompt = self.module.build_prompt(self.source, self.module.load_config())
        self.assertIn("cover、insight、scenario", prompt)
        self.assertIn("知识图解", prompt)
        self.assertIn("OpenMAIC", prompt)
        self.assertIn("版式类型", prompt)
        self.assertIn("机制原理版", prompt)
        self.assertIn("细胞呼吸：对比与考点", prompt)
        self.assertIn("不能为后期代码叠字留空", prompt)

    def test_extract_json_object_accepts_code_fence(self):
        raw = """```json
        {"笔记标题":"A","开场钩子":"B","笔记正文":"C","总结":"D","推荐标签":["AI资讯"],"封面标题":"E","图片规划":[],"生成状态":"已生成"}
        ```"""
        payload = self.module._extract_json_object(raw)
        self.assertEqual(payload["笔记标题"], "A")

    def test_extract_json_object_raises_when_missing(self):
        with self.assertRaises(ValueError):
            self.module._extract_json_object("no json here")

    def test_combine_output_handles_list(self):
        self.assertEqual(self.module._combine_output(["A", "B"]), "AB")
        self.assertEqual(self.module._combine_output("AB"), "AB")

    def test_sanitize_note_payload_normalizes_tags_and_image_plan(self):
        payload = {
            "笔记标题": "标题",
            "开场钩子": "钩子",
            "笔记正文": "正文",
            "总结": "总结",
            "推荐标签": "AI资讯 效率工具",
            "封面标题": "封面",
            "图片规划": [
                {
                    "图片用途": "封面",
                    "版式类型": "总览拆解版",
                    "卡片标题": "先看这个",
                    "卡片副标题": "副标题",
                    "卡片编号": "01/03",
                    "主视觉说明": "一个大的主题主图",
                    "画面模块": [
                        {"模块类型": "主视觉", "模块标题": "总览", "要点": ["主题1"], "强调": "居中"},
                        {"模块类型": "模块", "模块标题": "重点", "要点": ["要点1", "要点2"], "强调": "左侧"},
                    ],
                    "模块关系": ["总览 -> 重点"],
                    "记忆句": "记住它",
                    "配图元素": ["书本", "箭头"],
                    "画面描述": "卡片1",
                    "生图提示词": "prompt1",
                },
                {
                    "图片用途": "观点",
                    "版式类型": "机制原理版",
                    "卡片标题": "核心拆解",
                    "主视觉说明": "一个机制图",
                    "画面模块": [{"模块类型": "步骤", "模块标题": "亮点", "要点": ["要点A"], "强调": "箭头"}],
                    "配图元素": ["放大镜"],
                    "画面描述": "卡片2",
                    "生图提示词": "prompt2",
                },
                {
                    "图片用途": "场景",
                    "版式类型": "流程步骤版",
                    "卡片标题": "应用步骤",
                    "主视觉说明": "步骤链路",
                    "画面模块": [{"模块类型": "步骤", "模块标题": "步骤", "要点": ["步骤1"], "强调": "第一步"}],
                    "画面描述": "卡片3",
                    "生图提示词": "prompt3",
                    "比例": "1:1",
                },
            ],
            "生成状态": "已生成",
        }
        note = self.module.sanitize_note_payload(payload)
        self.assertEqual(note["推荐标签"], ["#AI资讯", "#效率工具"])
        self.assertEqual([item["图片角色"] for item in note["图片规划"]], ["cover", "insight", "scenario"])
        self.assertEqual([item["比例"] for item in note["图片规划"]], ["3:4", "4:5", "4:5"])
        self.assertEqual(note["图片规划"][0]["版式类型"], "总览拆解版")
        self.assertEqual(note["图片规划"][0]["画面模块"][1]["模块标题"], "重点")
        self.assertEqual(note["图片规划"][1]["配图元素"], ["放大镜"])
        self.assertEqual(note["图片规划"][2]["版式类型"], "流程步骤版")
        self.assertEqual(note["图片规划"][0]["生图提示词"], "prompt1")

    def test_write_note_uses_replicate_helpers(self):
        raw_output = json.dumps(
            {
                "笔记标题": "标题",
                "开场钩子": "钩子",
                "笔记正文": "正文",
                "总结": "总结",
                "推荐标签": ["#AI资讯", "#效率工具"],
                "封面标题": "封面",
                "图片规划": [
                    {
                        "图片角色": "cover",
                        "图片用途": "封面",
                        "版式类型": "总览拆解版",
                        "卡片标题": "标题卡",
                        "卡片副标题": "副标题",
                        "卡片编号": "01/03",
                        "主视觉说明": "主图",
                        "画面模块": [{"模块类型": "主视觉", "模块标题": "重点", "要点": ["要点1"], "强调": "居中"}],
                        "模块关系": ["主图 -> 重点"],
                        "记忆句": "记住它",
                        "配图元素": ["书本"],
                        "画面描述": "卡片1",
                        "生图提示词": "prompt1",
                        "比例": "3:4",
                    },
                    {
                        "图片角色": "insight",
                        "图片用途": "观点",
                        "版式类型": "机制原理版",
                        "卡片标题": "拆解卡",
                        "卡片副标题": "副标题2",
                        "卡片编号": "02/03",
                        "主视觉说明": "机制图",
                        "画面模块": [{"模块类型": "步骤", "模块标题": "亮点", "要点": ["要点2"], "强调": "箭头"}],
                        "模块关系": ["亮点 -> 结果"],
                        "记忆句": "抓重点",
                        "配图元素": ["灯泡"],
                        "画面描述": "卡片2",
                        "生图提示词": "prompt2",
                        "比例": "4:5",
                    },
                    {
                        "图片角色": "scenario",
                        "图片用途": "场景",
                        "版式类型": "流程步骤版",
                        "卡片标题": "应用卡",
                        "卡片副标题": "副标题3",
                        "卡片编号": "03/03",
                        "主视觉说明": "流程图",
                        "画面模块": [{"模块类型": "步骤", "模块标题": "步骤", "要点": ["要点3"], "强调": "第一步"}],
                        "模块关系": ["步骤1 -> 步骤2"],
                        "记忆句": "去落地",
                        "配图元素": ["清单"],
                        "画面描述": "卡片3",
                        "生图提示词": "prompt3",
                        "比例": "4:5",
                    },
                ],
                "生成状态": "已生成",
            },
            ensure_ascii=False,
        )
        with patch.object(self.module, "_replicate_api_token", return_value="token"), patch.object(self.module, "_replicate_create_prediction", return_value="pred_1"), patch.object(self.module, "_replicate_wait_output", return_value=raw_output):
            note, meta = self.module.write_note(self.source)
        self.assertEqual(note["笔记标题"], "标题")
        self.assertEqual(meta["prediction_id"], "pred_1")
        self.assertEqual(note["图片规划"][1]["版式类型"], "机制原理版")

    def test_replicate_api_token_prefers_env(self):
        with patch.dict(self.module.os.environ, {"REPLICATE_API_TOKEN": "env-token"}, clear=True):
            token = self.module._replicate_api_token({})
        self.assertEqual(token, "env-token")

    def test_replicate_api_token_uses_config(self):
        self.assertEqual(self.module._replicate_api_token({"replicate_api_token": "cfg-token"}), "cfg-token")

    def test_replicate_api_token_raises_without_any_source(self):
        with patch.dict(self.module.os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                self.module._replicate_api_token({})

    def test_sanitize_note_payload_rejects_bad_shapes(self):
        with self.assertRaises(ValueError):
            self.module.sanitize_note_payload("bad")
        with self.assertRaises(ValueError):
            self.module.sanitize_note_payload({"笔记标题": "only one field"})

    def test_replicate_create_prediction_raises_on_http_error(self):
        with patch.object(self.module.requests, "post", return_value=FakeResponse(status_code=500, text="bad request")):
            with self.assertRaises(RuntimeError):
                self.module._replicate_create_prediction("token", "model", {"prompt": "x"})

    def test_replicate_create_prediction_success(self):
        with patch.object(self.module.requests, "post", return_value=FakeResponse(status_code=201, payload={"id": "pred_1"})):
            prediction_id = self.module._replicate_create_prediction("token", "model", {"prompt": "x"})
        self.assertEqual(prediction_id, "pred_1")

    def test_replicate_wait_output_success_failed_and_timeout(self):
        with patch.object(self.module.requests, "get", return_value=FakeResponse(payload={"status": "succeeded", "output": ["A", "B"]})), patch.object(self.module.time, "time", side_effect=[0, 0]):
            output = self.module._replicate_wait_output("token", "pred", timeout_s=10)
        self.assertEqual(output, "AB")

        with patch.object(self.module.requests, "get", return_value=FakeResponse(payload={"status": "failed", "error": "boom"})), patch.object(self.module.time, "time", side_effect=[0, 0]):
            with self.assertRaises(RuntimeError):
                self.module._replicate_wait_output("token", "pred", timeout_s=10)

        with patch.object(self.module.time, "time", side_effect=[0, 1]):
            with self.assertRaises(TimeoutError):
                self.module._replicate_wait_output("token", "pred", timeout_s=0)

    def test_normalize_tags_default_when_empty(self):
        self.assertEqual(self.module._normalize_tags(""), ["#AI资讯", "#效率工具", "#小红书图文"])

    def test_main_success_and_error_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "source.json"
            output_path = Path(temp_dir) / "note.json"
            input_path.write_text(json.dumps(self.source, ensure_ascii=False), encoding="utf-8")
            with patch.object(self.module, "write_note", return_value=({"笔记标题": "标题", "开场钩子": "钩子", "笔记正文": "正文", "总结": "总结", "推荐标签": ["#AI资讯"], "封面标题": "封面", "图片规划": [], "生成状态": "已生成"}, {"prediction_id": "pred"})), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--input", str(input_path), "--out", str(output_path)])
            self.assertEqual(code, 0)
            self.assertTrue(output_path.exists())
            self.assertIn('"prediction_id": "pred"', stdout.getvalue())

            with patch.object(self.module, "write_note", side_effect=RuntimeError("boom")), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--input", str(input_path)])
            self.assertEqual(code, 1)
            self.assertIn("boom", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
