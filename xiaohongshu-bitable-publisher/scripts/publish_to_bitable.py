#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import requests


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config() -> dict:
    return json.loads((_skill_root() / "config.json").read_text(encoding="utf-8"))


def _config_value(config: dict, env_name: str, key: str) -> str:
    env_value = os.environ.get(env_name)
    if env_value and env_value.strip():
        return env_value.strip()
    cfg_value = config.get(key)
    if isinstance(cfg_value, str):
        return cfg_value.strip()
    return ""


def _required_config_value(config: dict, env_name: str, key: str) -> str:
    value = _config_value(config, env_name, key)
    if value:
        return value
    raise ValueError(f"missing required setting: {key} (or environment variable {env_name})")


def _raise_feishu_error(action: str, resp: requests.Response) -> None:
    try:
        payload = resp.json()
    except ValueError:
        payload = {"status_code": resp.status_code, "body": resp.text[:500]}

    violations = payload.get("error", {}).get("permission_violations", [])
    scopes = [item.get("subject") for item in violations if item.get("subject")]
    details = {
        "status_code": resp.status_code,
        "code": payload.get("code"),
        "msg": payload.get("msg"),
    }
    if scopes:
        details["missing_scopes"] = scopes
    if payload.get("code") == 91403:
        details["hint"] = "当前应用已能调用接口，但还没有这张云文档/多维表格的资源权限。请在目标 Base 中给这个应用可编辑权限。"
    raise RuntimeError(f"{action}: {json.dumps(details, ensure_ascii=False)}")


def get_tenant_access_token(config: dict) -> str:
    app_id = _required_config_value(config, "FEISHU_APP_ID", "app_id")
    app_secret = _required_config_value(config, "FEISHU_APP_SECRET", "app_secret")
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30,
    )
    if resp.status_code >= 400:
        _raise_feishu_error("飞书鉴权失败", resp)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"飞书鉴权失败: {payload}")
    return payload["tenant_access_token"]


def list_field_items(config: dict, access_token: str) -> list[dict]:
    app_token = _required_config_value(config, "FEISHU_BITABLE_APP_TOKEN", "app_token")
    table_id = _required_config_value(config, "FEISHU_BITABLE_TABLE_ID", "table_id")
    resp = requests.get(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code >= 400:
        _raise_feishu_error("获取飞书字段失败", resp)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"获取飞书字段失败: {payload}")
    return payload.get("data", {}).get("items", [])


def create_field(config: dict, access_token: str, field_name: str, field_type: int = 1) -> None:
    app_token = _required_config_value(config, "FEISHU_BITABLE_APP_TOKEN", "app_token")
    table_id = _required_config_value(config, "FEISHU_BITABLE_TABLE_ID", "table_id")
    resp = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"field_name": field_name, "type": field_type},
        timeout=30,
    )
    if resp.status_code >= 400:
        _raise_feishu_error(f"创建字段失败({field_name})", resp)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"创建字段失败({field_name}): {payload}")


def delete_field(config: dict, access_token: str, field_id: str, field_name: str) -> None:
    app_token = _required_config_value(config, "FEISHU_BITABLE_APP_TOKEN", "app_token")
    table_id = _required_config_value(config, "FEISHU_BITABLE_TABLE_ID", "table_id")
    resp = requests.delete(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code >= 400:
        _raise_feishu_error(f"删除字段失败({field_name})", resp)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"删除字段失败({field_name}): {payload}")


def update_field(config: dict, access_token: str, field_id: str, field_name: str, field_type: int) -> None:
    app_token = _required_config_value(config, "FEISHU_BITABLE_APP_TOKEN", "app_token")
    table_id = _required_config_value(config, "FEISHU_BITABLE_TABLE_ID", "table_id")
    resp = requests.put(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields/{field_id}",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"field_name": field_name, "type": field_type},
        timeout=30,
    )
    if resp.status_code >= 400:
        _raise_feishu_error(f"更新字段失败({field_name})", resp)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"更新字段失败({field_name}): {payload}")


def ensure_fields(config: dict, access_token: str) -> list[str]:
    field_items = list_field_items(config, access_token)
    field_types = config.get("field_types", {})
    cleanup_fields = set(config.get("cleanup_fields", []))
    primary_candidates = [item for item in field_items if item.get("is_primary") and item.get("field_name") in {"文本", "多行文本"}]

    for primary in primary_candidates:
        for item in field_items:
            if item.get("field_name") == "标题" and item.get("field_id") != primary.get("field_id"):
                delete_field(config, access_token, item["field_id"], item["field_name"])

    for item in field_items:
        if item.get("is_primary") and item.get("field_name") in {"文本", "多行文本"}:
            update_field(config, access_token, item["field_id"], "标题", 1)
            continue
        if item.get("field_name") in cleanup_fields:
            delete_field(config, access_token, item["field_id"], item["field_name"])

    remote_fields = {item["field_name"] for item in list_field_items(config, access_token)}
    for field_name in config["field_order"]:
        if field_name not in remote_fields:
            create_field(config, access_token, field_name, int(field_types.get(field_name, 1)))
    return [item["field_name"] for item in list_field_items(config, access_token)]


def upload_attachment(config: dict, access_token: str, file_path: str) -> str:
    path = Path(file_path).expanduser().resolve()
    app_token = _required_config_value(config, "FEISHU_BITABLE_APP_TOKEN", "app_token")
    if not path.exists():
        raise FileNotFoundError(f"图片文件不存在: {path}")
    if path.stat().st_size <= 0:
        raise RuntimeError(f"图片文件为空，无法上传: {path}")

    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:
        resp = requests.post(
            "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all",
            headers={"Authorization": f"Bearer {access_token}"},
            data={
                "file_name": path.name,
                "parent_type": "bitable_image",
                "parent_node": app_token,
                "size": str(path.stat().st_size),
            },
            files={"file": (path.name, fh, mime_type)},
            timeout=60,
        )
    if resp.status_code >= 400:
        _raise_feishu_error("上传飞书附件失败", resp)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"上传飞书附件失败: {payload}")
    return payload["data"]["file_token"]


def _load_input(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "note" in payload and "source" in payload:
        return payload
    raise ValueError("input JSON must be a pipeline result with source and note")


def _image_path_map(payload: dict) -> dict[str, str]:
    images = payload.get("images") or []
    role_to_field = {
        "cover": "封面图",
        "insight": "观点图",
        "scenario": "场景图",
    }
    result: dict[str, str] = {}
    for item in images:
        field_name = role_to_field.get(item.get("图片角色"))
        if field_name and item.get("path"):
            result[field_name] = str(item["path"])
    return result


def build_record_fields(config: dict, remote_fields: set[str], payload: dict, access_token: str) -> dict:
    note = payload["note"]["data"]
    source = payload["source"]
    image_paths = _image_path_map(payload)
    fields: dict = {}
    attachment_fields = {"封面图", "观点图", "场景图"}

    for key in config["field_order"]:
        if key not in remote_fields:
            continue
        if key in attachment_fields:
            file_path = image_paths.get(key)
            if file_path:
                token = upload_attachment(config, access_token, file_path)
                fields[key] = [{"file_token": token}]
            continue
        if key == "标题":
            fields[key] = str(note.get("笔记标题") or "")
            continue
        if key == "日期":
            fields[key] = int(time.time() * 1000)
            continue
        if key == "开场钩子":
            fields[key] = str(note.get("开场钩子") or "")
            continue
        if key == "正文":
            fields[key] = str(note.get("笔记正文") or "")
            continue
        if key == "总结":
            fields[key] = str(note.get("总结") or "")
            continue
        if key == "推荐标签":
            fields[key] = " ".join(str(tag) for tag in note.get("推荐标签") or [])
            continue
        if key == "封面标题":
            fields[key] = str(note.get("封面标题") or "")
            continue
        if key == "来源平台":
            fields[key] = str(source.get("source_platform") or "")
            continue
        if key == "来源链接":
            fields[key] = str(source.get("source_url") or "")
            continue
        if key == "原始摘要":
            fields[key] = str(source.get("source_summary") or "")
            continue
        if key == "生成状态":
            fields[key] = str(note.get("生成状态") or "")
            continue
        fields[key] = ""
    return fields


def create_record(config: dict, payload: dict) -> dict:
    app_token = _required_config_value(config, "FEISHU_BITABLE_APP_TOKEN", "app_token")
    table_id = _required_config_value(config, "FEISHU_BITABLE_TABLE_ID", "table_id")
    access_token = get_tenant_access_token(config)
    remote_fields = set(ensure_fields(config, access_token))
    fields = build_record_fields(config, remote_fields, payload, access_token)
    resp = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"fields": fields},
        timeout=30,
    )
    if resp.status_code >= 400:
        _raise_feishu_error("创建飞书记录失败", resp)
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"创建飞书记录失败: {payload}")
    return payload.get("data", {})


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="publish one Xiaohongshu note pipeline result to Feishu Bitable")
    parser.add_argument("--input", required=True, help="pipeline result JSON path")
    args = parser.parse_args(argv)

    config = load_config()
    payload = _load_input(args.input)
    try:
        result = create_record(config, payload)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
