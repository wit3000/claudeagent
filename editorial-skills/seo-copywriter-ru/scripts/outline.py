#!/usr/bin/env python3
"""Skeleton of a Russian Markdown article for a reverse outline.

Usage:
    python3 scripts/outline.py article.md
    python3 scripts/outline.py article.md --json
    cat article.md | python3 scripts/outline.py -

Prints the heading tree, the first sentence and size of every paragraph, list
and table, and the share of the text each section takes. The writer or editor
then writes the thought of every paragraph next to it in one phrase and checks
the meaning on this skeleton: answer to the heading, order, gaps, doubles,
proportions. Sections shorter than 300 characters without spaces are marked.
The "## Заметки к сдаче" block is skipped.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lint_text import parse_blocks, plain, short_quote  # noqa: E402
from text_stats import split_sentences  # noqa: E402

SHORT_SECTION = 300


def chars(text: str) -> int:
    return sum(1 for ch in plain(text) if not ch.isspace())


def outline(text: str) -> dict:
    sections: list[dict] = [{"level": 0, "title": "", "line": 0, "chars": 0, "blocks": []}]
    for block in parse_blocks(text):
        if block.kind == "heading":
            sections.append({"level": block.level, "title": plain(block.text), "line": block.line,
                             "chars": 0, "blocks": []})
            continue
        section = sections[-1]
        size = chars(block.text)
        section["chars"] += size
        blocks = section["blocks"]
        if block.kind == "paragraph":
            first = split_sentences(plain(block.text))
            blocks.append({"kind": "paragraph", "line": block.line, "chars": size,
                           "first": short_quote(first[0] if first else plain(block.text), 140)})
        elif blocks and blocks[-1]["kind"] == block.kind:
            blocks[-1]["count"] += 1
            blocks[-1]["chars"] += size
        else:
            blocks.append({"kind": block.kind, "line": block.line, "chars": size, "count": 1})
    if not sections[0]["blocks"]:
        sections.pop(0)
    total = sum(s["chars"] for s in sections) or 1
    for i, section in enumerate(sections):
        section["share"] = round(100 * section["chars"] / total)
        # A heading with subsections is a group: its own lead-in may be short.
        has_children = i + 1 < len(sections) and sections[i + 1]["level"] > section["level"] > 0
        section["short"] = (bool(section["blocks"]) and not has_children
                            and section["chars"] < SHORT_SECTION)
    return {"chars_no_spaces": sum(s["chars"] for s in sections), "sections": sections}


def format_outline(data: dict) -> str:
    out = [f"Всего знаков без пробелов: {data['chars_no_spaces']}, "
           f"разделов: {len(data['sections'])}", ""]
    for section in data["sections"]:
        level = section["level"]
        pad = "  " * max(level - 1, 0)
        title = f"{'#' * level} {section['title']}" if level else "(до заголовков)"
        mark = f"  ⚠ короче {SHORT_SECTION} знаков" if section["short"] else ""
        out.append(f"{pad}{title} — {section['chars']} зн., {section['share']}%{mark}")
        for i, block in enumerate(section["blocks"], start=1):
            where = f"{pad}  {i}. строка {block['line']}"
            if block["kind"] == "paragraph":
                out.append(f"{where}, абзац, {block['chars']} зн.: {block['first']}")
                out.append(f"{pad}     мысль: …")
            elif block["kind"] == "item":
                out.append(f"{where}, список: пунктов {block['count']}")
            else:
                out.append(f"{where}, таблица: строк {block['count']}")
    out.append("")
    out.append("Рядом с каждым «мысль: …» запиши одной фразой утверждение абзаца, над разделом — "
               "вопрос читателя и ответ. Проверки — references/meaning.md, раздел 2.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", help="Markdown file, or - for stdin")
    parser.add_argument("--json", action="store_true", help="print the outline as JSON")
    args = parser.parse_args(argv)
    try:
        if args.path == "-":
            text = sys.stdin.buffer.read().decode("utf-8")
        else:
            text = Path(args.path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"cannot read {args.path}: {exc}", file=sys.stderr)
        return 2
    data = outline(text)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_outline(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
