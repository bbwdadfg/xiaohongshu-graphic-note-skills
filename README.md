# 小红书图文生成 Skills

一套固定流程的内容生产链路，用来把一条资讯源转成：

1. 结构化来源 JSON
2. 一篇小红书图文笔记
3. 3 张知识图解配图
4. 可选的飞书多维表格入库结果

这不是通用内容平台，而是一套故意收窄范围的 Skills 原型。

## 包含哪些模块

- `news-source-parser`: 解析单条资讯源
- `xiaohongshu-note-writer`: 生成笔记文案和 3 张图的规划
- `xiaohongshu-note-illustrator`: 按规划生成 3 张最终图片
- `xiaohongshu-bitable-publisher`: 可选，把结果写入飞书多维表格
- `xiaohongshu-graphic-note-pipeline`: 总控编排入口

## 输入与输出

支持输入：

- GitHub 链接
- X 链接
- 小红书链接
- 即刻链接
- 手动粘贴文本
- 本地文本文件

标准输出：

- `source.json`
- `note.json`
- `images/`
- `result.json`

固定图片角色：

- `cover`: 封面总览知识图
- `insight`: 核心拆解知识图
- `scenario`: 应用步骤知识图

## 真实案例

下面这组图文是这条链路的一个真实输出案例，输入来源是 `gstack` 这个 GitHub 项目，目标是把一个技术项目整理成适合小红书分发的图文笔记。

案例标题：

`一个人怎么做出 20 人工程团队的效率？我刚挖到这个 GitHub 项目`

正文节选：

> 今天刷 GitHub 时，我认真看了 Garry Tan 开源的 gstack，第一感觉不是“又一个 AI 编程工具”，而是“终于有人把 AI 协作开发的流程做成产品了”。
>
> 它最强的点，不是帮你多写几行代码，而是把一个真实团队里的关键角色拆出来：CEO 负责重新想产品，工程经理负责锁架构，设计师负责看视觉和交互，review 负责查生产风险，QA 负责走真实页面，发布工具负责把最后一公里跑完。
>
> gstack 的价值不在单点提速，而是把 Think、Plan、Build、Review、Test、Ship、Reflect 串成一条连续流程，让 AI 真正进入软件开发主流程。

适合展示这条链路能处理什么内容：

- 可以把技术项目转成平台化表达，而不是只做资讯摘要
- 可以同时产出笔记文案和 3 张结构不同的知识图解
- 输出更像“可直接发布的成品”，不是一堆半成品中间稿

案例话题词：

`#GitHub发现 #AI编程 #ClaudeCode #独立开发 #程序员工具 #开发效率`

案例配图：

![gstack cover](examples/gstack/cover.png)

![gstack insight](examples/gstack/insight.png)

![gstack scenario](examples/gstack/scenario.png)

## 快速开始

安装依赖：

```bash
python3 -m pip install requests
```

配置外部服务。公开仓库内的 `config.json` 都是脱敏占位值，优先使用环境变量：

```bash
export REPLICATE_API_TOKEN="your_replicate_api_token"

# 只有要写飞书时才需要
export FEISHU_APP_ID="your_feishu_app_id"
export FEISHU_APP_SECRET="your_feishu_app_secret"
export FEISHU_BITABLE_APP_TOKEN="your_feishu_bitable_app_token"
export FEISHU_BITABLE_TABLE_ID="your_feishu_bitable_table_id"
```

直接跑整条链路：

```bash
python3 xiaohongshu-graphic-note-pipeline/scripts/run_graphic_note_pipeline.py \
  --url "https://github.com/THU-MAIC/OpenMAIC" \
  --out-dir "./output/demo"
```

处理原始文本：

```bash
python3 xiaohongshu-graphic-note-pipeline/scripts/run_graphic_note_pipeline.py \
  --text "这里是一段资讯原文" \
  --out-dir "./output/demo"
```

跳过生图，只产出文案：

```bash
python3 xiaohongshu-graphic-note-pipeline/scripts/run_graphic_note_pipeline.py \
  --url "https://github.com/THU-MAIC/OpenMAIC" \
  --out-dir "./output/demo" \
  --skip-images
```

生成后直接写入飞书：

```bash
python3 xiaohongshu-graphic-note-pipeline/scripts/run_graphic_note_pipeline.py \
  --url "https://github.com/THU-MAIC/OpenMAIC" \
  --out-dir "./output/demo" \
  --publish-feishu
```

## 分步执行

先解析来源：

```bash
python3 news-source-parser/scripts/parse_news_source.py \
  --url "https://github.com/THU-MAIC/OpenMAIC" \
  --out "./tmp/source.json"
```

再生成笔记：

```bash
python3 xiaohongshu-note-writer/scripts/write_xiaohongshu_note.py \
  --input "./tmp/source.json" \
  --out "./tmp/note.json"
```

再生成图片：

```bash
python3 xiaohongshu-note-illustrator/scripts/generate_note_images.py \
  --input "./tmp/note.json" \
  --out-dir "./output/demo/images" \
  --out "./tmp/images.json"
```

最后可选入飞书：

```bash
python3 xiaohongshu-bitable-publisher/scripts/publish_to_bitable.py \
  --input "./output/demo/result.json"
```

## 约束

- 只处理单条内容
- 图片固定 3 张
- 图片只允许走 `Replicate -> google/nano-banana-pro`
- 不允许回退到本地 Python 脚本生图
- 非 `replicate` 渲染配置会直接报错

这是设计选择，不是遗漏。

## 调试建议

排查顺序保持固定：

1. 先跑 parser，确认 `source.json` 正常
2. 再跑 writer，确认 `note.json` 和 `图片规划` 正常
3. 再单独跑 illustrator
4. 最后再决定是否写飞书

图片阶段不稳定时，优先怀疑第三方服务波动，不要先改 writer 或 prompt。

## 测试

```bash
python3 -m unittest discover -s tests
```

## 仓库清理策略

这个公开版本默认不提交以下内容：

- 本地缓存和 `__pycache__`
- 中间产物 `tmp/`
- 输出目录 `output/`
- 本机无关的系统文件
- 任何真实 token、密钥、私有 Base/Table 标识

## 当前链路定位

这是一个高约束、强流程的 Skill 原型，不是通用平台。

它解决的问题不是“任意生成内容”，而是：

给一条资讯源，稳定地产出一篇适合小红书的图文笔记和 3 张知识图解，并把结果组织成可复用的结构化产物。
