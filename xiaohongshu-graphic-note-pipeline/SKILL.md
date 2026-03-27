---
name: xiaohongshu-graphic-note-pipeline
description: "Orchestrate a multi-skill Xiaohongshu graphic-note workflow for one news/info source by parsing the source, writing one high-quality note with Replicate google/gemini-3-pro, and generating three final knowledge-card images with Replicate google/nano-banana-pro. Use when the user wants one complete Xiaohongshu image-and-text post from one source."
---

# Xiaohongshu Graphic Note Pipeline

这是总控入口 skill，负责串联 4 个子 skill：

1. `news-source-parser`
2. `xiaohongshu-note-writer`
3. `xiaohongshu-note-illustrator`
4. `xiaohongshu-bitable-publisher`

## 标准流程

1. 解析单条资讯源
2. 生成 1 篇高质量小红书图文笔记
3. 为 3 张图选择知识图版式并生成最终知识卡片配图
4. 可选写入飞书多维表格

## 规则

- 只处理单条内容
- 必须优先调用 `scripts/run_graphic_note_pipeline.py`
- 如果只是想跑整条链路，不要手动拆步骤

## 命令行

```bash
python3 xiaohongshu-graphic-note-pipeline/scripts/run_graphic_note_pipeline.py \
  --url "https://github.com/THU-MAIC/OpenMAIC" \
  --out-dir "/tmp/xhs_graphic_note"
```

也支持：

```bash
python3 xiaohongshu-graphic-note-pipeline/scripts/run_graphic_note_pipeline.py \
  --text "这里是一段资讯原文" \
  --out-dir "/tmp/xhs_graphic_note"
```

## 输出

输出 JSON 包含：
- `source`
- `note`
- `images`
- `feishu`
- `output_dir`
