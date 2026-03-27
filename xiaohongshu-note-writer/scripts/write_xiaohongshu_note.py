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


NOTE_FIELDS = [
    "笔记标题",
    "开场钩子",
    "笔记正文",
    "总结",
    "推荐标签",
    "封面标题",
    "图片规划",
    "生成状态",
]

LAYOUT_TYPES = [
    "总览拆解版",
    "对比评测版",
    "流程步骤版",
    "机制原理版",
    "影响因素版",
    "易错纠正版",
]

DEFAULT_IMAGE_PLAN = [
    {"图片角色": "cover", "图片用途": "封面总览知识图", "比例": "3:4"},
    {"图片角色": "insight", "图片用途": "核心拆解知识图", "比例": "4:5"},
    {"图片角色": "scenario", "图片用途": "应用步骤知识图", "比例": "4:5"},
]

ROLE_DEFAULTS = {
    "cover": {
        "版式类型": "总览拆解版",
        "卡片标题": "这条资讯到底是什么",
        "卡片副标题": "先抓概念，再看价值",
        "卡片编号": "01/03",
        "主视觉说明": "用一个大的主视觉概括主题，再用三个模块拆开说明。",
        "记忆句": "先看定义，再抓价值点。",
        "配图元素": ["主图", "箭头", "书本", "标签"],
        "画面模块": [
            {"模块类型": "主视觉", "模块标题": "主题总览", "要点": ["一句话说清主题"], "强调": "主图居中"},
            {"模块类型": "模块", "模块标题": "这是什么", "要点": ["一句话定义"], "强调": "放左侧"},
            {"模块类型": "模块", "模块标题": "为什么重要", "要点": ["一句话价值"], "强调": "放右侧"},
            {"模块类型": "结论", "模块标题": "最该记住", "要点": ["2 个关键词"], "强调": "底部总结"},
        ],
        "模块关系": ["主视觉 -> 这是什么", "主视觉 -> 为什么重要", "这是什么 + 为什么重要 -> 最该记住"],
    },
    "insight": {
        "版式类型": "机制原理版",
        "卡片标题": "核心机制怎么运作",
        "卡片副标题": "不是结论堆砌，而是讲明白",
        "卡片编号": "02/03",
        "主视觉说明": "画一个大的机制主图，再用箭头展示关键环节。",
        "记忆句": "抓住机制，才算真正看懂。",
        "配图元素": ["主图", "流程箭头", "齿轮", "放大镜"],
        "画面模块": [
            {"模块类型": "主视觉", "模块标题": "机制主图", "要点": ["中间放一个解释原理的主体图"], "强调": "最大视觉重心"},
            {"模块类型": "步骤", "模块标题": "第一环节", "要点": ["输入或触发条件"], "强调": "箭头连接"},
            {"模块类型": "步骤", "模块标题": "第二环节", "要点": ["中间处理逻辑"], "强调": "箭头连接"},
            {"模块类型": "步骤", "模块标题": "第三环节", "要点": ["输出或结果"], "强调": "箭头连接"},
            {"模块类型": "结论", "模块标题": "一句本质", "要点": ["底部结论"], "强调": "底部横条"},
        ],
        "模块关系": ["第一环节 -> 第二环节 -> 第三环节", "主视觉 -> 三个环节", "三个环节 -> 一句本质"],
    },
    "scenario": {
        "版式类型": "流程步骤版",
        "卡片标题": "怎么上手最省力",
        "卡片副标题": "步骤图 + 避坑提醒",
        "卡片编号": "03/03",
        "主视觉说明": "以步骤链路为主，中间用箭头串起来，右下补避坑提醒。",
        "记忆句": "先搭流程，再谈效率。",
        "配图元素": ["清单", "对勾", "警告牌", "箭头"],
        "画面模块": [
            {"模块类型": "步骤", "模块标题": "第一步", "要点": ["先完成准备动作"], "强调": "起点"},
            {"模块类型": "步骤", "模块标题": "第二步", "要点": ["执行关键设置"], "强调": "中间节点"},
            {"模块类型": "步骤", "模块标题": "第三步", "要点": ["开始运行或验证"], "强调": "终点"},
            {"模块类型": "误区", "模块标题": "避坑提醒", "要点": ["一个高频错误"], "强调": "红框强调"},
            {"模块类型": "结论", "模块标题": "行动建议", "要点": ["一句话总结"], "强调": "底部总结"},
        ],
        "模块关系": ["第一步 -> 第二步 -> 第三步", "流程 -> 避坑提醒", "流程 -> 行动建议"],
    },
}

REFERENCE_STYLE = (
    "请参考小红书上复杂知识笔记案例的完成度，接近“细胞呼吸：对比与考点”“金属活动性顺序”“圆的认识”这类"
    "一页多模块、高信息密度、图文一起讲知识的手绘知识卡片。"
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
    raise ValueError("missing Replicate API token")


def _default_module_item(item: dict) -> dict:
    return {
        "模块类型": item["模块类型"],
        "模块标题": item["模块标题"],
        "要点": list(item["要点"]),
        "强调": item["强调"],
    }


def _default_image_item(default: dict) -> dict:
    role = default["图片角色"]
    role_defaults = ROLE_DEFAULTS[role]
    return {
        "图片角色": role,
        "图片用途": default["图片用途"],
        "版式类型": role_defaults["版式类型"],
        "卡片标题": role_defaults["卡片标题"],
        "卡片副标题": role_defaults["卡片副标题"],
        "卡片编号": role_defaults["卡片编号"],
        "主视觉说明": role_defaults["主视觉说明"],
        "画面模块": [_default_module_item(item) for item in role_defaults["画面模块"]],
        "模块关系": list(role_defaults["模块关系"]),
        "记忆句": role_defaults["记忆句"],
        "配图元素": list(role_defaults["配图元素"]),
        "画面描述": "",
        "生图提示词": "",
        "比例": default["比例"],
    }


def _default_schema() -> dict:
    return {
        "笔记标题": "",
        "开场钩子": "",
        "笔记正文": "",
        "总结": "",
        "推荐标签": ["#AI资讯", "#效率工具", "#小红书运营"],
        "封面标题": "",
        "图片规划": [_default_image_item(item) for item in DEFAULT_IMAGE_PLAN],
        "生成状态": "已生成",
    }


def build_prompt(source: dict, config: dict) -> str:
    del config
    source_json = json.dumps(source, ensure_ascii=False, indent=2)
    schema_json = json.dumps(_default_schema(), ensure_ascii=False, indent=2)
    layout_json = json.dumps(
        {
            "总览拆解版": "适合解释一个新概念 / 工具 / 项目，结构是主视觉 + 3 个拆解模块 + 底部结论。",
            "对比评测版": "适合讲两种方案或两类对象的差异，结构是左右对比 + 差异总结 + 选择建议。",
            "流程步骤版": "适合讲怎么上手、怎么操作、怎么执行，结构是 3 到 4 步流程 + 避坑提醒。",
            "机制原理版": "适合讲底层原理、运行逻辑、因果关系，结构是主图 + 箭头环节 + 本质总结。",
            "影响因素版": "适合讲多个变量如何影响结果，结构是核心结论 + 2x2 或 1x4 因素模块。",
            "易错纠正版": "适合讲误区和纠错，结构是错误说法 vs 正确认知 + 底部口诀。",
        },
        ensure_ascii=False,
        indent=2,
    )

    return f"""
你是一名很会写中文小红书图文笔记的内容编辑，同时也是“知识图解策划师”。

你的任务：
1. 根据输入资讯生成 1 篇完整的小红书图文笔记。
2. 同时为 3 张配图生成可以直接落地的“知识图解版式方案”。
3. 严格输出 JSON，不要 Markdown，不要解释，不要代码块。

输入资讯：
{source_json}

笔记写作要求：
- 笔记标题：要有吸引力，但不能浮夸失真。
- 开场钩子：1 到 2 句，说明这条资讯为什么值得关注。
- 笔记正文：4 到 6 个短段落，既有信息提炼，也有自己的拆解视角。
- 总结：1 到 2 句收尾，强调实际价值。
- 推荐标签：输出 3 到 6 个字符串，必须以 # 开头。
- 封面标题：适合放在封面上的短句。
- 生成状态：固定写 已生成。

图片规划总原则：
- 必须刚好 3 项，角色分别是 cover、insight、scenario。
- 这 3 张图全部都必须是“知识图解”，不是场景图，不是摄影图，不是简单便签卡片。
- 图形和文字要一起讲知识，不能只是 3 个圆角框堆信息。
- cover 优先用“总览拆解版”。
- insight 必须从“机制原理版 / 对比评测版 / 影响因素版”中选一个最适合当前资讯的版式。
- scenario 必须从“流程步骤版 / 易错纠正版”中选一个最适合当前资讯的版式。

固定版式库：
{layout_json}

每张图片规划必须包含这些字段：
- 图片角色
- 图片用途
- 版式类型：必须从这 6 个固定版式中选择一个
- 卡片标题
- 卡片副标题
- 卡片编号
- 主视觉说明：说明这张图最核心的视觉主体应该是什么
- 画面模块：3 到 6 项，每项都要有 模块类型、模块标题、要点、强调
- 模块关系：1 到 4 条字符串，描述模块之间的箭头关系或认知顺序
- 记忆句
- 配图元素：3 到 6 个字符串
- 画面描述：中文，描述整张知识图怎么布局
- 生图提示词：完整中文 AI 绘图指令
- 比例

画面模块规则：
- 模块类型只能使用：主视觉、模块、对比、步骤、因素、误区、结论
- 每个模块要点 1 到 3 条，必须是简短中文
- 不同版式要体现不同模块组织方式，不能所有图都只是“模块 + 模块 + 模块”

固定风格规则：
- 可爱彩铅手绘涂鸦（Full-Color Hand-Drawn Doodle）
- 模拟彩铅 / 蜡笔 / 水彩填色，柔和黑色细线勾轮廓
- 背景浅米色淡纹理或留白
- 马卡龙色系或柔和彩虹色，颜色有自然笔触感
- 线条不完美，略带抖动的手绘感
- 中文文字要清晰可读，像彩色手写课堂笔记
- 允许箭头、流程、对比框、四宫格、横向链路、口诀横条
- 不是简陋卡片，而是“会讲知识的图解笔记”

案例感知要求：
- {REFERENCE_STYLE}
- 画面要复杂、饱满、有层次，不要只做 3 个圆角框，不要大面积空白。
- 每张图都要有明确的信息组织结构，像真正的学习笔记，而不是“插画 + 几个标签”。

生图提示词写法要求：
- 必须明确写出“请生成 1 张 {{比例}} 竖版学科笔记图”
- 必须写明具体版式类型
- 必须写明主视觉、模块标题、模块关系、记忆句都要出现在画面中
- 必须点明这是一张知识图解，不是场景摄影，不是简单卡片
- 必须把中文文字作为独立文字图层清晰呈现
- 必须把需要显示的中文标题、模块标题、要点、口诀全部直接写进提示词，不允许写“此处放标题”“预留文字区”
- 必须明确要求模型自己直接生成中文手写字，不能为后期代码叠字留空，不能输出空白标签框

严禁：
- 不要输出多余字段
- 不要编造输入里完全没有的硬事实
- 不要把 3 张图都写成同一套模板
- 不要只写“科技感插画”“信息卡片”这种空泛词
- 不要把图片写成纯底图、纯场景图、纯 icon 海报

输出 JSON 模板：
{schema_json}
""".strip()


def _combine_output(output: str | list[str]) -> str:
    if isinstance(output, list):
        return "".join(str(part) for part in output)
    return str(output)


def _extract_json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not match:
        raise ValueError("model output did not contain a JSON object")
    return json.loads(match.group(0))


def _normalize_tags(value) -> list[str]:
    raw_items = value if isinstance(value, list) else re.split(r"[\s,，]+", str(value or ""))
    tags: list[str] = []
    for item in raw_items:
        text = str(item or "").strip().replace("＃", "#")
        if not text:
            continue
        if not text.startswith("#"):
            text = f"#{text.lstrip('#')}"
        text = re.sub(r"\s+", "", text)
        if text not in tags:
            tags.append(text)
    return tags[:6] or ["#AI资讯", "#效率工具", "#小红书图文"]


def _clean_text(value, default: str = "", max_length: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    return text[:max_length] if text else default


def _normalize_string_list(items, fallback: list[str], max_items: int, max_length: int = 40) -> list[str]:
    raw_items = items if isinstance(items, list) else re.split(r"[；;\n]+", str(items or ""))
    result: list[str] = []
    for item in raw_items:
        text = _clean_text(item, max_length=max_length)
        if text and text not in result:
            result.append(text)
    return result[:max_items] or fallback[:max_items]


def _normalize_modules(items, fallback: list[dict]) -> list[dict]:
    raw_items = items if isinstance(items, list) else []
    modules: list[dict] = []
    allowed_types = {"主视觉", "模块", "对比", "步骤", "因素", "误区", "结论"}
    for item in raw_items[:6]:
        if not isinstance(item, dict):
            continue
        module_type = _clean_text(item.get("模块类型"), max_length=10)
        if module_type not in allowed_types:
            continue
        module_title = _clean_text(item.get("模块标题"), max_length=22)
        points = _normalize_string_list(item.get("要点"), [], 3, max_length=34)
        emphasis = _clean_text(item.get("强调"), max_length=40)
        if module_title and points:
            modules.append(
                {
                    "模块类型": module_type,
                    "模块标题": module_title,
                    "要点": points,
                    "强调": emphasis,
                }
            )
    if modules:
        return modules
    return [_default_module_item(item) for item in fallback]


def _normalize_image_plan(items) -> list[dict]:
    raw_items = items if isinstance(items, list) else []
    normalized: list[dict] = []
    for idx, default in enumerate(DEFAULT_IMAGE_PLAN):
        raw_item = raw_items[idx] if idx < len(raw_items) and isinstance(raw_items[idx], dict) else {}
        role_defaults = ROLE_DEFAULTS[default["图片角色"]]
        layout_type = _clean_text(raw_item.get("版式类型"), role_defaults["版式类型"], 20)
        if layout_type not in LAYOUT_TYPES:
            layout_type = role_defaults["版式类型"]
        normalized.append(
            {
                "图片角色": default["图片角色"],
                "图片用途": _clean_text(raw_item.get("图片用途"), default["图片用途"], 30),
                "版式类型": layout_type,
                "卡片标题": _clean_text(raw_item.get("卡片标题"), role_defaults["卡片标题"], 30),
                "卡片副标题": _clean_text(raw_item.get("卡片副标题"), role_defaults["卡片副标题"], 36),
                "卡片编号": _clean_text(raw_item.get("卡片编号"), role_defaults["卡片编号"], 10),
                "主视觉说明": _clean_text(raw_item.get("主视觉说明"), role_defaults["主视觉说明"], 120),
                "画面模块": _normalize_modules(raw_item.get("画面模块"), role_defaults["画面模块"]),
                "模块关系": _normalize_string_list(raw_item.get("模块关系"), role_defaults["模块关系"], 4, max_length=60),
                "记忆句": _clean_text(raw_item.get("记忆句"), role_defaults["记忆句"], 50),
                "配图元素": _normalize_string_list(raw_item.get("配图元素"), role_defaults["配图元素"], 6, max_length=18),
                "画面描述": _clean_text(raw_item.get("画面描述"), "", 320),
                "生图提示词": _clean_text(raw_item.get("生图提示词"), "", 2600),
                "比例": default["比例"],
            }
        )
    return normalized


def sanitize_note_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("note payload must be a JSON object")
    missing = [field for field in NOTE_FIELDS if field not in payload]
    if missing:
        raise ValueError(f"model output missing fields: {missing}")
    return {
        "笔记标题": _clean_text(payload.get("笔记标题"), max_length=40),
        "开场钩子": _clean_text(payload.get("开场钩子"), max_length=140),
        "笔记正文": str(payload.get("笔记正文") or "").strip(),
        "总结": _clean_text(payload.get("总结"), max_length=140),
        "推荐标签": _normalize_tags(payload.get("推荐标签")),
        "封面标题": _clean_text(payload.get("封面标题"), max_length=24),
        "图片规划": _normalize_image_plan(payload.get("图片规划")),
        "生成状态": _clean_text(payload.get("生成状态"), "已生成", 20),
    }


def _replicate_create_prediction(api_token: str, model: str, model_input: dict) -> str:
    headers = {"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"}
    resp = requests.post(
        f"https://api.replicate.com/v1/models/{model}/predictions",
        headers=headers,
        json={"input": model_input},
        timeout=30,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"Replicate create prediction failed: {resp.status_code} ({resp.text[:400]})")
    return resp.json()["id"]


def _replicate_wait_output(api_token: str, prediction_id: str, timeout_s: int = 300) -> str:
    headers = {"Authorization": f"Bearer {api_token}"}
    url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
    deadline = time.time() + timeout_s
    last_status = None
    while time.time() < deadline:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        last_status = payload.get("status")
        if last_status == "succeeded":
            return _combine_output(payload.get("output", ""))
        if last_status == "failed":
            raise RuntimeError(f"Replicate prediction failed: {payload.get('error', 'unknown error')}")
        time.sleep(2)
    raise TimeoutError(f"Replicate prediction timed out (last_status={last_status})")


def write_note(source: dict) -> tuple[dict, dict]:
    config = load_config()
    api_token = _replicate_api_token(config)
    prompt = build_prompt(source, config)
    model_input = {
        "prompt": prompt,
        "temperature": config["temperature"],
        "top_p": config["top_p"],
        "thinking_level": config["thinking_level"],
        "max_output_tokens": config["max_output_tokens"],
    }
    prediction_id = _replicate_create_prediction(api_token, config["model"], model_input)
    raw_output = _replicate_wait_output(api_token, prediction_id)
    payload = sanitize_note_payload(_extract_json_object(raw_output))
    meta = {
        "prediction_id": prediction_id,
        "model": config["model"],
        "raw_output": raw_output,
    }
    return payload, meta


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="write one Xiaohongshu graphic note from a structured source JSON")
    parser.add_argument("--input", required=True, help="source JSON path")
    parser.add_argument("--out", help="output JSON path")
    args = parser.parse_args(argv)

    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    try:
        payload, meta = write_note(source)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    result = {"data": payload, "meta": meta}
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
