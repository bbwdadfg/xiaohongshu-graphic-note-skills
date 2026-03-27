---
name: xiaohongshu-note-writer
description: Turn one structured source JSON into one high-quality Xiaohongshu graphic note using Replicate google/gemini-3-pro. Use when the user wants a complete note draft plus three knowledge-infographic plans with fixed layout types, modules, and exact Chinese card copy.
---

# Xiaohongshu Note Writer

把单条结构化资讯源改写成一篇高质量的小红书图文笔记，并为每张配图生成可直接落地的知识图解版式结构。

这个 skill 只负责文案和知识图解规划，不负责真正生图。文案模型固定走 Replicate 上的 `google/gemini-3-pro`。

## 输出内容

- `笔记标题`
- `开场钩子`
- `笔记正文`
- `总结`
- `推荐标签`
- `封面标题`
- `图片规划`
- `生成状态`

其中 `图片规划` 固定为 3 张图：
1. `cover`
2. `insight`
3. `scenario`

每张图都会补齐这些知识图字段：
- `版式类型`
- `卡片标题`
- `卡片副标题`
- `卡片编号`
- `主视觉说明`
- `画面模块`
- `模块关系`
- `记忆句`
- `配图元素`
- `画面描述`
- `生图提示词`

## 规则

- 必须使用 `scripts/write_xiaohongshu_note.py`
- 只处理单条内容
- 输出必须是 JSON
- `生图提示词` 必须是完整中文知识图解 prompt
- 三张图都必须是知识图解，不是简单卡片，更不是纯场景图
- 必须从 6 种固定版式里为每张图选择最合适的一种
- `生图提示词` 必须把画面里要显示的中文文字直接写全，明确要求模型直接生成文字，不给后期叠字留空位
- 不要在这里直接调用图片生成

## 命令行

```bash
python3 xiaohongshu-note-writer/scripts/write_xiaohongshu_note.py \
  --input "/tmp/source.json"
```
