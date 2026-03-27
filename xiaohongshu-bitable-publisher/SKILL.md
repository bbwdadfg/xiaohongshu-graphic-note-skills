---
name: xiaohongshu-bitable-publisher
description: Publish one generated Xiaohongshu graphic-note result into the dedicated Feishu Bitable table. Use when the user wants one note stored as one row with text fields and uploaded images.
---

# Xiaohongshu Bitable Publisher

把一条已经生成完成的小红书图文笔记写入飞书多维表格。

这个 skill 服务于“小红书图文笔记”这条链路，目标 Base 和 Table 通过配置文件或环境变量提供。

## 配置来源

- `FEISHU_APP_ID` / `config.json.app_id`
- `FEISHU_APP_SECRET` / `config.json.app_secret`
- `FEISHU_BITABLE_APP_TOKEN` / `config.json.app_token`
- `FEISHU_BITABLE_TABLE_ID` / `config.json.table_id`

## 固定字段

- 标题
- 日期
- 开场钩子
- 正文
- 总结
- 推荐标签
- 封面标题
- 封面图
- 观点图
- 场景图
- 来源平台
- 来源链接
- 原始摘要
- 生成状态

## 规则

- 一条笔记写一行
- 附件字段允许为空，但不要写入空附件
- 必须使用 `scripts/publish_to_bitable.py`
- 输入优先使用总控链路输出的 JSON

## 命令行

```bash
python3 xiaohongshu-bitable-publisher/scripts/publish_to_bitable.py \
  --input "/tmp/xhs_graphic_note/result.json"
```
