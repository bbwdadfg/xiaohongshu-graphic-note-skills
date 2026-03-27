---
name: news-source-parser
description: Parse one news/info source into normalized JSON for downstream Xiaohongshu note generation. Use when the user provides one URL, pasted text, or a local file and wants a structured source object before copywriting.
---

# News Source Parser

把单条资讯源整理成统一 JSON，供后续的小红书图文链路使用。

这个 skill 是完全自包含的解析器：
- 自带文本清洗、URL 抓取和 GitHub 仓库解析
- 在解析结果上补充资讯场景字段
- 不做批量，不做内容改写

## 适用输入

- GitHub 链接
- X 链接
- 小红书链接
- 即刻链接
- 手动粘贴的资讯文本
- 本地文本文件

## 规则

- 只处理单条内容
- 必须使用 `scripts/parse_news_source.py`
- 解析失败时直接抛错，不在这里偷偷改写内容

## 命令行

```bash
python3 news-source-parser/scripts/parse_news_source.py \
  --url "https://github.com/THU-MAIC/OpenMAIC"
```

也支持：

```bash
python3 news-source-parser/scripts/parse_news_source.py \
  --text "这里是一段资讯原文"
```

## 输出

输出 JSON 继承原解析器的字段，并补充：
- `news_angle`
- `target_readers`
- `parser_version`
