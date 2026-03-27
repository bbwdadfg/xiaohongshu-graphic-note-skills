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


class NewsSourceParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            ROOT / "news-source-parser" / "scripts" / "parse_news_source.py",
            "test_news_source_parser_module",
        )

    def test_normalize_source_adds_bundle_fields(self):
        payload = {
            "source_title": "Test Source",
            "suggested_angle": "old way vs new way",
            "audience": "builders",
        }
        normalized = self.module.normalize_source(payload)
        self.assertEqual(normalized["news_angle"], "old way vs new way")
        self.assertEqual(normalized["target_readers"], "builders")
        self.assertEqual(normalized["parser_version"], "news-source-parser/v2")

    def test_detect_platform(self):
        self.assertEqual(self.module.detect_platform("https://github.com/openai/openai-python"), "github")
        self.assertEqual(self.module.detect_platform("https://x.com/foo/status/1"), "x")
        self.assertEqual(self.module.detect_platform("https://www.xiaohongshu.com/explore/123"), "xiaohongshu")
        self.assertEqual(self.module.detect_platform("https://okjike.com/originalPosts/1"), "jike")
        self.assertEqual(self.module.detect_platform(None), "raw_text")

    def test_helper_text_and_angle_functions(self):
        self.assertEqual(self.module._clean_text("A\r\n\r\n\r\nB&nbsp;"), "A\n\nB")
        self.assertEqual(self.module._first_sentences("", 10), "")
        self.assertEqual(self.module._first_sentences("第一段\n第二段\n第三段", 100), "第一段 第二段")
        self.assertTrue(self.module._first_sentences("abcdef", 4).endswith("…"))
        self.assertIn("自动搞定", self.module._default_angle("url", "", "auto workflow"))
        self.assertIn("一个入口", self.module._default_angle("url", "", "research notes"))
        self.assertIn("实际机会", self.module._default_angle("url", "", "产品发布了"))
        self.assertIn("GitHub", self.module._default_angle("github", "", ""))
        self.assertIn("小红书拆解", self.module._default_angle("url", "", "ordinary news"))
        self.assertIn("程序员", self.module._default_audience("github api"))
        self.assertIn("产品经理", self.module._default_audience("增长变现"))
        self.assertIn("AI 资讯关注者", self.module._default_audience("普通文本"))

    def test_bullet_and_core_point_helpers(self):
        self.assertEqual(self.module._normalize_bullet("- **Hello** `world`"), "Hello world")
        self.assertEqual(self.module._normalize_bullet("2. item"), "item")
        self.assertEqual(self.module._normalize_bullet("plain"), "plain")
        self.assertTrue(self.module._looks_like_bullet("- item"))
        self.assertFalse(self.module._looks_like_bullet("plain"))
        self.assertTrue(self.module._should_skip_core_point(""))
        self.assertTrue(self.module._should_skip_core_point("x" * 161))
        self.assertTrue(self.module._should_skip_core_point("![img]"))
        self.assertFalse(self.module._should_skip_core_point("正常卖点"))
        points = self.module._collect_points_from_lines(["- A", "* B", "3. C", "plain"])
        self.assertEqual(points, ["A", "B", "C"])
        fallback = self.module._extract_core_points("plain text", "fallback")
        self.assertEqual(fallback, ["fallback"])

    def test_github_owner_repo_and_html_helpers(self):
        self.assertEqual(self.module._extract_github_owner_repo("https://github.com/openai/openai-python"), ("openai", "openai-python"))
        self.assertIsNone(self.module._extract_github_owner_repo("https://github.com/openai"))
        self.assertEqual(self.module._html_title('<meta property="og:title" content="OG 标题">', "https://example.com"), "OG 标题")
        self.assertEqual(self.module._html_title('<meta name="twitter:title" content="Twitter 标题">', "https://example.com"), "Twitter 标题")
        self.assertEqual(self.module._html_title("<title> 页面 标题 </title>", "https://example.com"), "页面 标题")
        self.assertEqual(self.module._html_title("<html></html>", "https://example.com"), "https://example.com")
        html_text = self.module._html_text("<style>x</style><script>y</script><p>第一段</p><br><div>第二段</div>")
        self.assertIn("第一段", html_text)
        self.assertIn("第二段", html_text)

    def test_parse_source_from_text(self):
        payload = self.module.parse_source(None, "这是一个新的 AI 发布。\n- 功能一\n- 功能二", None)
        self.assertEqual(payload["source_platform"], "raw_text")
        self.assertEqual(payload["parse_status"], "ok")
        self.assertIn("news_angle", payload)

    def test_parse_source_from_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "source.txt"
            file_path.write_text("本地资讯内容\n1. 亮点A\n2. 亮点B", encoding="utf-8")
            payload = self.module.parse_source(None, None, str(file_path))
        self.assertEqual(payload["source_platform"], "raw_text")
        self.assertGreaterEqual(len(payload["core_points"]), 1)

    def test_parse_source_uses_github_metadata(self):
        with patch.object(self.module, "_fetch_github_metadata", return_value=("owner/repo", "README text", {"name": "repo", "description": "desc"})):
            payload = self.module.parse_source("https://github.com/owner/repo", None, None)
        self.assertEqual(payload["source_platform"], "github")
        self.assertEqual(payload["project_name"], "repo")

    def test_parse_source_falls_back_to_generic_url_fetch(self):
        with patch.object(self.module, "_fetch_github_metadata", side_effect=RuntimeError("boom")), patch.object(self.module, "_fetch_url_content", return_value=("网页标题", "网页正文")):
            payload = self.module.parse_source("https://github.com/owner/repo", None, None)
        self.assertEqual(payload["source_title"], "网页标题")
        self.assertEqual(payload["parse_status"], "ok")

    def test_fetch_url_content_extracts_title_and_text(self):
        html_doc = """
        <html><head><title>测试标题</title></head>
        <body><article><p>第一段内容</p><p>第二段内容</p></article></body></html>
        """

        class FakeResponse:
            def __init__(self, text: str):
                self.text = text

            def raise_for_status(self):
                return None

        with patch.object(self.module.requests, "get", return_value=FakeResponse(html_doc)):
            title, text = self.module._fetch_url_content("https://example.com")
        self.assertEqual(title, "测试标题")
        self.assertIn("第一段内容", text)

    def test_fetch_url_content_uses_meta_description_when_text_empty(self):
        html_doc = '<html><head><meta name="description" content="描述内容"></head><body></body></html>'

        class FakeResponse:
            def __init__(self, text: str):
                self.text = text

            def raise_for_status(self):
                return None

        with patch.object(self.module.requests, "get", return_value=FakeResponse(html_doc)), patch.object(self.module, "_html_text", return_value=""):
            title, text = self.module._fetch_url_content("https://example.com")
        self.assertEqual(title, "https://example.com")
        self.assertEqual(text, "描述内容")

    def test_fetch_github_metadata_reads_main_or_master(self):
        class FakeResponse:
            def __init__(self, status_code=200, payload=None, text=""):
                self.status_code = status_code
                self._payload = payload or {}
                self.text = text

            def json(self):
                return self._payload

            def raise_for_status(self):
                return None

        responses = [
            FakeResponse(payload={"full_name": "owner/repo", "description": "desc", "name": "repo"}),
            FakeResponse(status_code=404, text=""),
            FakeResponse(status_code=200, text="README body"),
        ]
        with patch.object(self.module.requests, "get", side_effect=responses):
            title, combined, meta = self.module._fetch_github_metadata("https://github.com/owner/repo")
        self.assertEqual(title, "owner/repo")
        self.assertIn("README body", combined)
        self.assertEqual(meta["name"], "repo")

    def test_parse_source_raises_without_input(self):
        with self.assertRaises(ValueError):
            self.module.parse_source(None, None, None)

    def test_main_writes_output_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            out_path = Path(temp_dir) / "source.json"
            with patch.object(self.module, "parse_source", return_value={"source_title": "A"}), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--text", "hello", "--out", str(out_path)])
            self.assertEqual(code, 0)
            self.assertTrue(out_path.exists())
            self.assertEqual(json.loads(out_path.read_text(encoding="utf-8"))["source_title"], "A")
            self.assertIn('"source_title": "A"', stdout.getvalue())

    def test_main_returns_error_on_exception(self):
        with patch.object(self.module, "parse_source", side_effect=RuntimeError("boom")), patch("sys.stdout", new=io.StringIO()) as stdout:
            code = self.module.main(["--text", "hello"])
        self.assertEqual(code, 1)
        self.assertIn("boom", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
