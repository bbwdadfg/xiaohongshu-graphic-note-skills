#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests


def _clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_platform(value: str | None) -> str:
    if not value:
        return "raw_text"
    host = urlparse(value).netloc.lower()
    if "github.com" in host:
        return "github"
    if "x.com" in host or "twitter.com" in host:
        return "x"
    if "xiaohongshu.com" in host or "xhslink.com" in host:
        return "xiaohongshu"
    if "okjike.com" in host or "jike.city" in host or "jikipedia.com" in host:
        return "jike"
    return "url"


def _first_sentences(text: str, limit: int = 220) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    paragraphs = [chunk.strip() for chunk in cleaned.split("\n") if chunk.strip()]
    joined = " ".join(paragraphs[:2])
    if len(joined) <= limit:
        return joined
    return joined[: limit - 1].rstrip() + "…"


def _default_angle(platform: str, title: str, summary: str) -> str:
    haystack = f"{title}\n{summary}".lower()
    if any(token in haystack for token in ("自动", "auto", "agent", "workflow", "自动化")):
        return "以前很麻烦，现在一个工具自动搞定"
    if any(token in haystack for token in ("搜索", "查找", "资料", "research")):
        return "以前得切很多平台找资料，现在一个入口就能讲清楚"
    if any(token in haystack for token in ("发布", "上线", "发布会", "发布了")):
        return "这条新资讯背后，最值得普通人关注的不是热闹，而是实际机会"
    if platform == "github":
        return "GitHub 上又出现了一个值得立刻关注的新项目"
    return "这条资讯里有一个很适合做小红书拆解的切入点"


def _default_audience(text: str) -> str:
    haystack = text.lower()
    if any(token in haystack for token in ("github", "repo", "代码", "开发", "程序员", "api")):
        return "程序员、AI 工具玩家、内容创作者"
    if any(token in haystack for token in ("产品", "增长", "运营", "流量", "变现")):
        return "产品经理、运营、内容创作者、AI 从业者"
    return "AI 资讯关注者、效率党、内容创作者"


def _normalize_bullet(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith(("-", "*", "•")):
        item = re.sub(r"^[-*•]\s*", "", stripped).strip()
    elif re.match(r"^\d+[.)、]\s*", stripped):
        item = re.sub(r"^\d+[.)、]\s*", "", stripped).strip()
    else:
        item = stripped

    item = re.sub(r"\*\*(.*?)\*\*", r"\1", item)
    item = re.sub(r"__(.*?)__", r"\1", item)
    item = re.sub(r"`([^`]*)`", r"\1", item)
    item = re.sub(r"\s{2,}", " ", item)
    return item.strip()


def _looks_like_bullet(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(("-", "*", "•")) or bool(re.match(r"^\d+[.)、]\s*", stripped))


def _should_skip_core_point(item: str) -> bool:
    if not item or len(item) > 160:
        return True
    if item.startswith("![") or item.startswith("|") or item.startswith("##"):
        return True
    return False


def _collect_points_from_lines(lines: list[str]) -> list[str]:
    points: list[str] = []
    for line in lines:
        if not _looks_like_bullet(line):
            continue
        item = _normalize_bullet(line)
        if _should_skip_core_point(item):
            continue
        points.append(item)
        if len(points) >= 5:
            break
    return points[:5]


def _extract_core_points(text: str, fallback: str = "") -> list[str]:
    lines = _clean_text(text).splitlines()
    points = _collect_points_from_lines(lines)
    if not points and fallback:
        points = [fallback]
    return points[:5]


def _extract_github_owner_repo(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]


def _fetch_github_metadata(url: str) -> tuple[str, str, dict]:
    owner_repo = _extract_github_owner_repo(url)
    if not owner_repo:
        raise ValueError(f"无法解析 GitHub 仓库链接: {url}")
    owner, repo = owner_repo

    repo_api = f"https://api.github.com/repos/{owner}/{repo}"
    repo_resp = requests.get(repo_api, timeout=30, headers={"Accept": "application/vnd.github+json"})
    repo_resp.raise_for_status()
    meta = repo_resp.json()

    readme_text = ""
    for branch in ("main", "master"):
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/README.md"
        readme_resp = requests.get(raw_url, timeout=30)
        if readme_resp.status_code == 200 and readme_resp.text.strip():
            readme_text = readme_resp.text
            break

    title = meta.get("full_name") or f"{owner}/{repo}"
    description = meta.get("description") or ""
    combined = _clean_text("\n\n".join(part for part in [description, readme_text] if part))
    return title, combined, meta


def _html_title(page: str, url: str) -> str:
    meta_patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pattern in meta_patterns:
        match = re.search(pattern, page, flags=re.I)
        if match:
            return html.unescape(match.group(1)).strip()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page, flags=re.I | re.S)
    if title_match:
        return html.unescape(re.sub(r"\s+", " ", title_match.group(1))).strip()
    return url


def _html_text(page: str) -> str:
    content = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", " ", page, flags=re.I | re.S)
    content = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<noscript\b[^<]*(?:(?!</noscript>)<[^<]*)*</noscript>", " ", content, flags=re.I | re.S)
    content = re.sub(r"<br\s*/?>", "\n", content, flags=re.I)
    content = re.sub(r"</(p|div|section|article|li|h\d)>", "\n", content, flags=re.I)
    content = re.sub(r"<[^>]+>", " ", content)
    content = re.sub(r"[ \t]+", " ", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return _clean_text(content)


def _fetch_url_content(url: str) -> tuple[str, str]:
    resp = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )
    resp.raise_for_status()
    page = resp.text
    title = _html_title(page, url)
    text = _html_text(page)
    if not text:
        meta_desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', page, flags=re.I)
        text = html.unescape(meta_desc.group(1)).strip() if meta_desc else ""
    return title, text


def normalize_source(payload: dict) -> dict:
    normalized = dict(payload)
    normalized["news_angle"] = payload.get("suggested_angle") or ""
    normalized["target_readers"] = payload.get("audience") or ""
    normalized["parser_version"] = "news-source-parser/v2"
    return normalized


def parse_source(url: str | None, text: str | None, file_path: str | None) -> dict:
    if file_path:
        text = Path(file_path).read_text(encoding="utf-8")

    if text and text.strip():
        cleaned = _clean_text(text)
        payload = {
            "source_platform": "raw_text",
            "source_url": "",
            "source_title": _first_sentences(cleaned, 40) or "手动输入内容",
            "source_text": cleaned,
            "source_summary": _first_sentences(cleaned),
            "project_name": "",
            "core_points": _extract_core_points(cleaned, _first_sentences(cleaned)),
            "audience": _default_audience(cleaned),
            "suggested_angle": _default_angle("raw_text", "", cleaned),
            "parse_status": "ok",
        }
        return normalize_source(payload)

    if not url:
        raise ValueError("必须提供 --url、--text 或 --file 之一")

    platform = detect_platform(url)
    if platform == "github":
        try:
            title, combined, meta = _fetch_github_metadata(url)
            summary = _first_sentences(combined or meta.get("description", ""))
            payload = {
                "source_platform": "github",
                "source_url": url,
                "source_title": title,
                "source_text": combined,
                "source_summary": summary,
                "project_name": meta.get("name") or title,
                "core_points": _extract_core_points(combined, meta.get("description", "")),
                "audience": _default_audience(combined),
                "suggested_angle": _default_angle("github", title, summary),
                "parse_status": "ok",
            }
            return normalize_source(payload)
        except Exception:
            pass

    title, content = _fetch_url_content(url)
    summary = _first_sentences(content)
    payload = {
        "source_platform": platform,
        "source_url": url,
        "source_title": title,
        "source_text": content,
        "source_summary": summary,
        "project_name": title if platform == "github" else "",
        "core_points": _extract_core_points(content, summary),
        "audience": _default_audience(content),
        "suggested_angle": _default_angle(platform, title, summary),
        "parse_status": "ok" if content else "fallback",
    }
    return normalize_source(payload)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="parse one news source for downstream Xiaohongshu generation")
    parser.add_argument("--url", help="one URL to parse")
    parser.add_argument("--text", help="raw text to parse")
    parser.add_argument("--file", help="local text file path")
    parser.add_argument("--out", help="output JSON path")
    args = parser.parse_args(argv)

    try:
        payload = parse_source(args.url, args.text, args.file)
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
