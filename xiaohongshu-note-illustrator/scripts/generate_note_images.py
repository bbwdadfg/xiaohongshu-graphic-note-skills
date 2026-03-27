#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

REFERENCE_STYLE = "参考小红书里“细胞呼吸：对比与考点”“金属活动性顺序”“圆的认识”这类复杂饱满的知识笔记案例。"
FIXED_STYLE_RULES = (
    "风格固定为可爱彩铅手绘涂鸦（Full-Color Hand-Drawn Doodle），模拟彩铅、蜡笔、水彩填色，"
    "柔和黑色细线勾轮廓，浅米色淡纹理纸张背景，马卡龙或柔和彩虹配色，线条略抖动，柔软亲切。"
    "所有中文都必须是彩色手写体效果，标题是粗体手写艺术字，正文是自然笔记手写体，绝对不要电脑字体。"
)


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_config() -> dict:
    return json.loads((_skill_root() / "config.json").read_text(encoding="utf-8"))


def _replicate_api_token(config: dict) -> str:
    env_value = os.environ.get("REPLICATE_API_TOKEN")
    if env_value and env_value.strip():
        return env_value.strip()
    cfg_value = config.get("replicate_api_token")
    if isinstance(cfg_value, str) and cfg_value.strip():
        return cfg_value.strip()
    raise ValueError("missing image API key from config.json or REPLICATE_API_TOKEN")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", str(text or "").strip()).strip("-")
    return slug[:50] or "xiaohongshu-note"


def _load_note_payload(path: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "data" in payload and isinstance(payload["data"], dict):
        return payload["data"]
    note = payload.get("note")
    if isinstance(note, dict) and isinstance(note.get("data"), dict):
        return note["data"]
    if "笔记标题" in payload:
        return payload
    raise ValueError("input JSON does not look like a note payload")


def _clean_text(value, max_length: int = 240) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())[:max_length]


def _modules(plan_item: dict) -> list[dict]:
    raw_items = plan_item.get("画面模块")
    modules: list[dict] = []
    if isinstance(raw_items, list):
        for item in raw_items[:6]:
            if not isinstance(item, dict):
                continue
            title = _clean_text(item.get("模块标题"), 24)
            kind = _clean_text(item.get("模块类型"), 10)
            emphasis = _clean_text(item.get("强调"), 40)
            raw_points = item.get("要点")
            points = raw_points if isinstance(raw_points, list) else [raw_points]
            normalized_points = [_clean_text(point, 36) for point in points if _clean_text(point, 36)]
            if title and normalized_points:
                modules.append(
                    {
                        "模块类型": kind or "模块",
                        "模块标题": title,
                        "要点": normalized_points[:3],
                        "强调": emphasis,
                    }
                )
    if modules:
        return modules
    return [{"模块类型": "模块", "模块标题": "重点", "要点": ["提炼输入资讯的核心信息"], "强调": ""}]


def _layout_type(plan_item: dict) -> str:
    return _clean_text(plan_item.get("版式类型"), 20) or "总览拆解版"


def _doodle_elements(plan_item: dict) -> list[str]:
    raw_items = plan_item.get("配图元素")
    items = raw_items if isinstance(raw_items, list) else []
    normalized = [_clean_text(item, 18) for item in items if _clean_text(item, 18)]
    return normalized[:6] or ["箭头", "标签", "便签"]


def _module_layout_guidance(layout_type: str) -> str:
    mapping = {
        "总览拆解版": "采用 1 个大主视觉 + 3 到 4 个拆解模块的总览结构，上中下层次清楚。",
        "对比评测版": "采用左右或上下对比结构，中间有 VS 或差异箭头，下方有选择建议和总结。",
        "流程步骤版": "采用 3 到 4 个步骤串联的流程结构，节点之间有明显箭头，并补一个避坑或行动建议区域。",
        "机制原理版": "采用中心主图 + 多环节箭头解释机制的结构，把因果链和本质总结讲清楚。",
        "影响因素版": "采用核心结论 + 2x2 或 1x4 因素模块的结构，强调变量如何影响结果。",
        "易错纠正版": "采用错误认知 vs 正确认知的纠错结构，用红绿对照和口诀收束重点。",
    }
    return mapping.get(layout_type, mapping["总览拆解版"])


def _text_requirements(plan_item: dict) -> str:
    lines = []
    title = _clean_text(plan_item.get("卡片标题"), 32)
    subtitle = _clean_text(plan_item.get("卡片副标题"), 40)
    card_number = _clean_text(plan_item.get("卡片编号"), 12)
    if title:
        lines.append(f"标题：{title}")
    if subtitle:
        lines.append(f"副标题：{subtitle}")
    if card_number:
        lines.append(f"编号：{card_number}")
    for idx, module in enumerate(_modules(plan_item), start=1):
        points = "；".join(module["要点"])
        lines.append(f"模块{idx} {module['模块标题']}：{points}")
    relations = plan_item.get("模块关系") or []
    if relations:
        lines.append(f"关系箭头：{'；'.join(_clean_text(item, 60) for item in relations[:4])}")
    memory = _clean_text(plan_item.get("记忆句"), 60)
    if memory:
        lines.append(f"记忆句：{memory}")
    return "；".join(lines)


def decorate_prompt(plan_item: dict, config: dict) -> str:
    base = _clean_text(plan_item.get("生图提示词"), 6000)
    if base:
        return base

    modules = _modules(plan_item)
    module_text = "；".join(f"{item['模块标题']}：{'，'.join(item['要点'])}" for item in modules)
    relations = "；".join(plan_item.get("模块关系") or [])
    layout_type = _layout_type(plan_item)
    prompt = (
        f"请生成 1 张 {_clean_text(plan_item.get('比例'), 10) or '4:5'} 竖版学科笔记图。"
        f"版式类型是{layout_type}，这是知识图解，不是场景摄影，也不是简单卡片。"
        f"{REFERENCE_STYLE}"
        f"{_module_layout_guidance(layout_type)}"
        f"大标题“{_clean_text(plan_item.get('卡片标题'), 28)}”，副标题“{_clean_text(plan_item.get('卡片副标题'), 36)}”。"
        f"主视觉说明：{_clean_text(plan_item.get('主视觉说明'), 100)}。"
        f"画面模块包括：{module_text}。"
    )
    if relations:
        prompt += f" 模块关系用箭头表示：{relations}。"
    prompt += (
        f" 底部记忆句是“{_clean_text(plan_item.get('记忆句'), 50)}”。"
        f" 图中加入这些手绘元素：{'、'.join(_doodle_elements(plan_item))}。"
        f" {FIXED_STYLE_RULES}"
        " 必须生成高信息密度的一页式学习笔记，图画讲知识，文字只做极简标签，但所有关键信息都要真实写在图里。"
        " 所有中文文字都必须由模型直接生成，清晰可读，不能留空白标题栏、空白标签框、空白箭头框，也不能后期代码叠字。"
        f" 图中文字必须完整覆盖这些内容：{_text_requirements(plan_item)}。"
        " 加入手绘箭头、框线、项目符号、对比区、流程链路、口诀横条，让画面复杂、饱满、有层次。"
        " 不要摄影感，不要海报感，不要只画场景，不要英文电脑字体，不要乱码，不要错别字，不要水印。"
    )
    suffix = _clean_text(config.get("prompt_suffix"), 300)
    if suffix:
        prompt += f" {suffix}"
    return prompt


def build_generation_jobs(note: dict, out_dir: str | Path) -> list[dict]:
    config = load_config()
    output_dir = Path(out_dir).expanduser().resolve()
    slug = _slugify(note.get("笔记标题"))
    plan_items = note.get("图片规划") or []
    jobs: list[dict] = []
    for idx, item in enumerate(plan_items, start=1):
        role = str(item.get("图片角色") or f"image_{idx}")
        extension = config.get("default_output_format", "png")
        output_path = output_dir / f"{idx:02d}_{role}_{slug}.{extension}"
        jobs.append(
            {
                "图片角色": role,
                "图片用途": _clean_text(item.get("图片用途"), 40),
                "比例": _clean_text(item.get("比例"), 10) or "4:5",
                "prompt": decorate_prompt(item, config),
                "path": str(output_path),
                "model": config.get("model", ""),
                "plan_item": item,
                "index": idx,
                "total": len(plan_items),
            }
        )
    return jobs


def _replicate_create_prediction(api_key: str, model: str, prompt: str, aspect_ratio: str, output_format: str, resolution: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "version": model,
        "input": {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "output_format": output_format,
            "resolution": resolution,
            "image_input": [],
            "safety_filter_level": "block_only_high",
        },
    }
    resp = requests.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload, timeout=30)
    if resp.status_code != 201:
        raise RuntimeError(f"Replicate create prediction failed: {resp.status_code} ({resp.text[:400]})")
    return resp.json()["id"]


def _replicate_wait_output(api_key: str, prediction_id: str, timeout_s: int = 300) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        last_status = payload.get("status")
        if last_status == "succeeded":
            output = payload.get("output")
            if isinstance(output, list) and output:
                return str(output[0])
            if isinstance(output, str) and output:
                return output
            raise RuntimeError("Replicate succeeded but output is empty")
        if last_status == "failed":
            raise RuntimeError(f"Replicate prediction failed: {payload.get('error', 'unknown error')}")
        time.sleep(2)
    raise TimeoutError(f"Replicate prediction timed out (last_status={last_status})")


def download_image(url: str, output_path: str) -> None:
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    with open(output_path, "wb") as fh:
        for chunk in response.iter_content(chunk_size=8192):
            fh.write(chunk)


def _ensure_nonempty_image(path: Path) -> None:
    if not path.exists():
        raise RuntimeError(f"generated image missing: {path}")
    if path.stat().st_size <= 0:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"generated image is empty: {path}")


def _prompt_candidates(job: dict, config: dict) -> list[str]:
    plan_item = job["plan_item"]
    modules = "；".join(f"{item['模块标题']}：{'，'.join(item['要点'])}" for item in _modules(plan_item))
    candidates = [
        job["prompt"],
        (
            f"请生成 1 张 {job['比例']} 竖版知识图解，版式类型为{_layout_type(plan_item)}。"
            f"标题“{_clean_text(plan_item.get('卡片标题'), 28)}”，模块包括：{modules}。"
            f"记忆句“{_clean_text(plan_item.get('记忆句'), 50)}”。"
            f"{REFERENCE_STYLE}"
            "可爱彩铅手绘涂鸦，知识讲解型编排，画面复杂饱满。"
            "所有中文标题、模块标题、要点和记忆句都由模型直接生成，不要留空位，不要后期叠字。"
        ),
        (
            f"请严格生成中文手写知识卡片：{_text_requirements(plan_item)}。"
            f"版式类型是{_layout_type(plan_item)}，{_module_layout_guidance(_layout_type(plan_item))}"
            "画面必须像复杂好看的课堂知识图，不是底图，不是场景插画，不是便签拼贴。"
        ),
    ]
    unique: list[str] = []
    for item in candidates:
        text = _clean_text(item, 6000)
        if text and text not in unique:
            unique.append(text)
    return unique


def _generate_with_replicate(job: dict, config: dict, output_path: Path) -> dict:
    api_key = _replicate_api_token(config)
    errors: list[str] = []
    for attempt, prompt in enumerate(_prompt_candidates(job, config), start=1):
        try:
            prediction_id = _replicate_create_prediction(api_key, job["model"], prompt, job["比例"], config["default_output_format"], config["default_resolution"])
            image_url = _replicate_wait_output(api_key, prediction_id)
            download_image(image_url, str(output_path))
            _ensure_nonempty_image(output_path)
            return {
                "prediction_id": prediction_id,
                "image_url": image_url,
                "prompt": prompt,
                "attempt": attempt,
                "render_engine": "replicate",
            }
        except Exception as exc:
            errors.append(str(exc))
    raise RuntimeError(" ; ".join(errors))


def generate_images(note: dict, out_dir: str | Path, force: bool = False) -> list[dict]:
    config = load_config()
    render_engine = config.get("render_engine", "replicate")
    if render_engine != "replicate":
        raise ValueError(f"unsupported render_engine: {render_engine}; only replicate is supported")
    results: list[dict] = []
    for job in build_generation_jobs(note, out_dir):
        output_path = Path(job["path"])
        if output_path.exists() and not force:
            try:
                _ensure_nonempty_image(output_path)
            except RuntimeError:
                pass
            else:
                results.append(
                    {
                        "图片角色": job["图片角色"],
                        "图片用途": job["图片用途"],
                        "比例": job["比例"],
                        "prompt": job["prompt"],
                        "path": str(output_path),
                        "model": job["model"],
                        "status": "skipped",
                        "render_engine": render_engine,
                    }
                )
                continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = _generate_with_replicate(job, config, output_path)
        results.append(
            {
                "图片角色": job["图片角色"],
                "图片用途": job["图片用途"],
                "比例": job["比例"],
                "prompt": job["prompt"],
                "path": str(output_path),
                "model": job["model"],
                "status": "generated",
                **metadata,
            }
        )
    return results


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="generate Xiaohongshu note images from note JSON")
    parser.add_argument("--input", required=True, help="note JSON path")
    parser.add_argument("--out-dir", required=True, help="output directory for images")
    parser.add_argument("--out", help="output JSON path")
    parser.add_argument("--force", action="store_true", help="overwrite existing images")
    args = parser.parse_args(argv)
    try:
        note = _load_note_payload(args.input)
        payload = generate_images(note, args.out_dir, force=args.force)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
