#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def _bundle_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_module(module_name: str, path: Path):
    if not path.exists():
        raise FileNotFoundError(f"missing skill script: {path}")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


PARSER = _load_module(
    "bundle_news_source_parser",
    _bundle_root() / "news-source-parser" / "scripts" / "parse_news_source.py",
)
WRITER = _load_module(
    "bundle_xiaohongshu_note_writer",
    _bundle_root() / "xiaohongshu-note-writer" / "scripts" / "write_xiaohongshu_note.py",
)
ILLUSTRATOR = _load_module(
    "bundle_xiaohongshu_note_illustrator",
    _bundle_root() / "xiaohongshu-note-illustrator" / "scripts" / "generate_note_images.py",
)
PUBLISHER = _load_module(
    "bundle_xiaohongshu_bitable_publisher",
    _bundle_root() / "xiaohongshu-bitable-publisher" / "scripts" / "publish_to_bitable.py",
)


def run_pipeline(
    url: str | None,
    text: str | None,
    file_path: str | None,
    out_dir: str | None,
    skip_images: bool = False,
    publish_feishu: bool = False,
) -> dict:
    output_dir = Path(out_dir or "/tmp/xhs_graphic_note").expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    source = PARSER.parse_source(url, text, file_path)
    note_data, note_meta = WRITER.write_note(source)

    note_result = {"data": note_data, "meta": note_meta}
    note_json_path = output_dir / "note.json"
    note_json_path.write_text(json.dumps(note_result, ensure_ascii=False, indent=2), encoding="utf-8")

    images = []
    if not skip_images:
        images = ILLUSTRATOR.generate_images(note_data, output_dir / "images")

    payload = {
        "source": source,
        "note": note_result,
        "images": images,
        "feishu": None,
        "output_dir": str(output_dir),
    }
    result_json_path = output_dir / "result.json"
    result_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if publish_feishu:
        payload["feishu"] = PUBLISHER.create_record(PUBLISHER.load_config(), payload)
        result_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="run the bundled Xiaohongshu graphic note pipeline")
    parser.add_argument("--url", help="one URL to process")
    parser.add_argument("--text", help="raw text to process")
    parser.add_argument("--file", help="local text file path")
    parser.add_argument("--out-dir", help="output directory")
    parser.add_argument("--out", help="final JSON output path")
    parser.add_argument("--skip-images", action="store_true", help="only generate the note JSON")
    parser.add_argument("--publish-feishu", action="store_true", help="append the generated note to Feishu Bitable")
    args = parser.parse_args(argv)

    try:
        payload = run_pipeline(
            args.url,
            args.text,
            args.file,
            args.out_dir,
            skip_images=args.skip_images,
            publish_feishu=args.publish_feishu,
        )
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
