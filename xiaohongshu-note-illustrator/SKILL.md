---
name: xiaohongshu-note-illustrator
description: Generate three Xiaohongshu note images from a note JSON plan. This skill must call Replicate `google/nano-banana-pro` to generate the final Chinese knowledge-card images with text included in the model output.
---

# Xiaohongshu Note Illustrator

根据文案子 skill 输出的 `图片规划` 生成 3 张小红书知识图解配图。

这个 skill 只允许调用 Replicate 上的 `google/nano-banana-pro` 生成最终成图，图里的中文标题、模块标题、要点和记忆句都要求由模型一次生成，不做本地脚本生图，也不做本地代码叠字。

## 规则

- 必须使用 `scripts/generate_note_images.py`
- 默认生成 3 张图
- 如果输出文件已存在且没有 `--force`，优先跳过
- 输入必须来自 `xiaohongshu-note-writer` 或总控 skill 的 JSON
- 输出目标是知识图解，不是摄影场景图
- 不同 `版式类型` 必须走不同信息结构，不能所有图都长一个样
- 必须要求模型直接生成清晰中文，不允许预留空白文字位给后期叠字
- 不允许回退到本地 Python 脚本渲染

## 命令行

```bash
python3 xiaohongshu-note-illustrator/scripts/generate_note_images.py \
  --input "/tmp/note.json" \
  --out-dir "/tmp/xhs_images"
```
