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


class XiaohongshuBitablePublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            ROOT / "xiaohongshu-bitable-publisher" / "scripts" / "publish_to_bitable.py",
            "test_xiaohongshu_bitable_publisher_module",
        )
        cls.payload = {
            "source": {
                "source_platform": "github",
                "source_url": "https://github.com/example/repo",
                "source_summary": "summary",
            },
            "note": {
                "data": {
                    "笔记标题": "标题",
                    "开场钩子": "钩子",
                    "笔记正文": "正文",
                    "总结": "总结",
                    "推荐标签": ["#AI工具", "#程序员"],
                    "封面标题": "封面",
                    "生成状态": "已生成",
                }
            },
            "images": [
                {"图片角色": "cover", "path": "/tmp/cover.png"},
                {"图片角色": "insight", "path": "/tmp/insight.png"},
                {"图片角色": "scenario", "path": "/tmp/scenario.png"},
            ],
        }

    def test_load_input_accepts_pipeline_payload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "result.json"
            input_path.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            payload = self.module._load_input(str(input_path))
        self.assertEqual(payload["source"]["source_platform"], "github")

    def test_load_input_rejects_invalid_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "bad.json"
            input_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.module._load_input(str(input_path))

    def test_image_path_map(self):
        mapped = self.module._image_path_map(self.payload)
        self.assertEqual(mapped["封面图"], "/tmp/cover.png")
        self.assertEqual(mapped["观点图"], "/tmp/insight.png")
        self.assertEqual(mapped["场景图"], "/tmp/scenario.png")

    def test_raise_feishu_error_includes_details(self):
        response = FakeResponse(status_code=403, payload={"code": 91403, "msg": "forbidden", "error": {"permission_violations": [{"subject": "bitable:record:write"}]}})
        with self.assertRaises(RuntimeError) as ctx:
            self.module._raise_feishu_error("失败", response)
        self.assertIn("bitable:record:write", str(ctx.exception))
        self.assertIn("hint", str(ctx.exception))

    def test_get_tenant_access_token_success_and_error(self):
        with patch.object(self.module.requests, "post", return_value=FakeResponse(payload={"code": 0, "tenant_access_token": "token"})):
            token = self.module.get_tenant_access_token(self.module.load_config())
        self.assertEqual(token, "token")

        with patch.object(self.module.requests, "post", return_value=FakeResponse(status_code=500, text="oops")):
            with self.assertRaises(RuntimeError):
                self.module.get_tenant_access_token(self.module.load_config())

        with patch.object(self.module.requests, "post", return_value=FakeResponse(payload={"code": 999, "msg": "bad"})):
            with self.assertRaises(RuntimeError):
                self.module.get_tenant_access_token(self.module.load_config())

    def test_config_value_prefers_env(self):
        with patch.dict(
            "os.environ",
            {
                "FEISHU_APP_ID": "env-app-id",
                "FEISHU_APP_SECRET": "env-app-secret",
                "FEISHU_BITABLE_APP_TOKEN": "env-app-token",
                "FEISHU_BITABLE_TABLE_ID": "env-table-id",
            },
            clear=True,
        ):
            config = self.module.load_config()
            self.assertEqual(self.module._required_config_value(config, "FEISHU_APP_ID", "app_id"), "env-app-id")
            self.assertEqual(self.module._required_config_value(config, "FEISHU_APP_SECRET", "app_secret"), "env-app-secret")
            self.assertEqual(self.module._required_config_value(config, "FEISHU_BITABLE_APP_TOKEN", "app_token"), "env-app-token")
            self.assertEqual(self.module._required_config_value(config, "FEISHU_BITABLE_TABLE_ID", "table_id"), "env-table-id")

    def test_list_field_items_and_field_mutations(self):
        with patch.object(self.module.requests, "get", return_value=FakeResponse(payload={"code": 0, "data": {"items": [{"field_name": "标题"}]}})):
            items = self.module.list_field_items(self.module.load_config(), "token")
        self.assertEqual(items[0]["field_name"], "标题")

        with patch.object(self.module.requests, "post", return_value=FakeResponse(payload={"code": 0})):
            self.module.create_field(self.module.load_config(), "token", "字段", 1)
        with patch.object(self.module.requests, "delete", return_value=FakeResponse(payload={"code": 0})):
            self.module.delete_field(self.module.load_config(), "token", "fld1", "字段")
        with patch.object(self.module.requests, "put", return_value=FakeResponse(payload={"code": 0})):
            self.module.update_field(self.module.load_config(), "token", "fld1", "字段", 1)

    def test_ensure_fields_updates_primary_and_creates_missing(self):
        field_snapshots = [
            [
                {"field_id": "fld_primary", "field_name": "文本", "is_primary": True},
                {"field_id": "fld_attach", "field_name": "附件", "is_primary": False},
            ],
            [
                {"field_id": "fld_primary", "field_name": "标题", "is_primary": True},
            ],
            [
                {"field_id": "fld_primary", "field_name": "标题", "is_primary": True},
                *[
                    {"field_id": f"fld_{idx}", "field_name": name, "is_primary": False}
                    for idx, name in enumerate(self.module.load_config()["field_order"][1:], start=1)
                ],
            ],
        ]

        def fake_list_field_items(config, access_token):
            del config, access_token
            return field_snapshots.pop(0)

        with patch.object(self.module, "list_field_items", side_effect=fake_list_field_items), patch.object(self.module, "delete_field") as mock_delete, patch.object(self.module, "update_field") as mock_update, patch.object(self.module, "create_field") as mock_create:
            fields = self.module.ensure_fields(self.module.load_config(), "token")
        self.assertIn("标题", fields)
        mock_update.assert_called()
        mock_delete.assert_called()
        mock_create.assert_called()

    def test_upload_attachment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "cover.png"
            file_path.write_bytes(b"pngdata")
            with patch.object(self.module.requests, "post", return_value=FakeResponse(payload={"code": 0, "data": {"file_token": "file_tok"}})):
                token = self.module.upload_attachment(self.module.load_config(), "access", str(file_path))
        self.assertEqual(token, "file_tok")

        with self.assertRaises(FileNotFoundError):
            self.module.upload_attachment(self.module.load_config(), "access", "/tmp/does-not-exist.png")

    def test_upload_attachment_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "cover.png"
            file_path.write_bytes(b"")
            with self.assertRaises(RuntimeError):
                self.module.upload_attachment(self.module.load_config(), "access", str(file_path))

    def test_build_record_fields(self):
        remote_fields = set(self.module.load_config()["field_order"])
        with patch.object(self.module, "upload_attachment", side_effect=["tok1", "tok2", "tok3"]), patch.object(self.module.time, "time", return_value=1000):
            fields = self.module.build_record_fields(self.module.load_config(), remote_fields, self.payload, "access")
        self.assertEqual(fields["标题"], "标题")
        self.assertEqual(fields["推荐标签"], "#AI工具 #程序员")
        self.assertEqual(fields["封面图"], [{"file_token": "tok1"}])
        self.assertEqual(fields["日期"], 1000000)

    def test_create_record_uses_helpers(self):
        with patch.object(self.module, "get_tenant_access_token", return_value="access"), patch.object(self.module, "ensure_fields", return_value=self.module.load_config()["field_order"]), patch.object(self.module, "build_record_fields", return_value={"标题": "标题"}), patch.object(self.module.requests, "post", return_value=FakeResponse(payload={"code": 0, "data": {"record_id": "rec1"}})):
            result = self.module.create_record(self.module.load_config(), self.payload)
        self.assertEqual(result["record_id"], "rec1")

    def test_create_record_raises_when_api_fails(self):
        with patch.object(self.module, "get_tenant_access_token", return_value="access"), patch.object(self.module, "ensure_fields", return_value=self.module.load_config()["field_order"]), patch.object(self.module, "build_record_fields", return_value={"标题": "标题"}), patch.object(self.module.requests, "post", return_value=FakeResponse(payload={"code": 999, "msg": "bad"})):
            with self.assertRaises(RuntimeError):
                self.module.create_record(self.module.load_config(), self.payload)

    def test_main_success_and_error_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "result.json"
            input_path.write_text(json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
            with patch.object(self.module, "create_record", return_value={"record_id": "rec1"}), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--input", str(input_path)])
            self.assertEqual(code, 0)
            self.assertIn("rec1", stdout.getvalue())

            with patch.object(self.module, "create_record", side_effect=RuntimeError("boom")), patch("sys.stdout", new=io.StringIO()) as stdout:
                code = self.module.main(["--input", str(input_path)])
            self.assertEqual(code, 1)
            self.assertIn("boom", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
