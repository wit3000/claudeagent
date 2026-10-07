#!/usr/bin/env python3
"""Count words, characters and structure of a Markdown article.

Usage:
    python3 scripts/text_stats.py article.md
    cat article.md | python3 scripts/text_stats.py -

Prints JSON to stdout. The "## Заметки к сдаче" block after a "---" line is
not counted. Sentence length is measured on paragraphs; list items are checked
only for long sentences, since short items would hide long paragraph sentences.
Exit code: 0 on success, 2 if the file is not found or cannot be read.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

NOTES_HEADING = "## Заметки к сдаче"
LONG_SENTENCE_WORDS = 25

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
# One or two digits: a line like "2024. Год…" is a paragraph, not a list.
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d{1,2}[.)])\s+(.*)$")
HR_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
EMPHASIS_RE = re.compile(r"\*+|`+|~~|(?<!\w)_+|_+(?!\w)")
WORD_CHAR_RE = re.compile(r"[^\W_]")
SENTENCE_END_RE = re.compile(r"[.!?…]+[»\"')\]]*\s+(?=[«\"(\[]?[A-ZА-ЯЁ0-9])")
# Abbreviations followed by a period that do not end a sentence.
ABBREVIATIONS = {
    "г", "гг", "д", "др", "им", "млн", "млрд", "пр", "руб", "см", "ст", "стр", "т", "тыс", "ул",
}

STAT_KEYS = (
    "words", "chars_no_spaces", "h1", "h2", "h3", "lists", "tables",
    "avg_sentence_words", "long_sentences",
)


def strip_notes(lines: list[str]) -> list[str]:
    """Drop the notes block: a "---" line followed by the notes heading."""
    for i, line in enumerate(lines):
        if line.strip() != "---":
            continue
        rest = [later.strip() for later in lines[i + 1:] if later.strip()]
        if rest and rest[0] == NOTES_HEADING:
            return lines[:i]
    return lines


def clean_inline(text: str) -> str:
    text = IMAGE_RE.sub(r"\1", text)
    text = LINK_RE.sub(r"\1", text)
    return EMPHASIS_RE.sub("", text)


def count_words(text: str) -> int:
    return sum(1 for token in text.split() if WORD_CHAR_RE.search(token))


def is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def is_table_separator(line: str) -> bool:
    body = line.strip()
    return "-" in body and not body.strip("|:- \t")


def split_sentences(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    for match in SENTENCE_END_RE.finditer(text):
        before = text[start:match.start()].split()
        last = before[-1].lower().lstrip("(«\"") if before else ""
        # Initials ("А. С.") and abbreviations ("т. е.", "стр. 8") do not end a sentence.
        if len(last.rstrip(".")) == 1 or last in ABBREVIATIONS:
            continue
        parts.append(text[start:match.end()])
        start = match.end()
    parts.append(text[start:])
    return [part for part in parts if count_words(part)]


def compute_stats(text: str) -> dict:
    lines = strip_notes(text.lstrip("﻿").splitlines())

    stats = dict.fromkeys(STAT_KEYS, 0)
    clean_lines: list[str] = []
    paragraphs: list[str] = []
    list_items: list[str] = []
    paragraph: list[str] = []

    fence = ""
    in_list = False
    prev_blank = True
    table_rows: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            paragraphs.append(" ".join(paragraph))
            paragraph.clear()

    def flush_table() -> None:
        if table_rows and any(is_table_separator(row) for row in table_rows):
            stats["tables"] += 1
        table_rows.clear()

    for raw in lines:
        fence_match = FENCE_RE.match(raw)
        if fence_match and (not fence or fence_match.group(1) == fence):
            fence = "" if fence else fence_match.group(1)
            flush_paragraph()
            flush_table()
            in_list = False
            continue
        if fence:
            clean_lines.append(raw)
            continue

        if not is_table_row(raw):
            flush_table()

        blank = not raw.strip()
        after_blank, prev_blank = prev_blank, blank
        if blank:
            flush_paragraph()
            continue

        if is_table_row(raw):
            flush_paragraph()
            in_list = False
            table_rows.append(raw)
            if not is_table_separator(raw):
                cells = raw.strip().strip("|").split("|")
                clean_lines.append(clean_inline(" ".join(cells)))
            continue

        if HR_RE.match(raw):
            flush_paragraph()
            in_list = False
            continue

        heading = HEADING_RE.match(raw)
        if heading:
            flush_paragraph()
            in_list = False
            level = len(heading.group(1))
            if level <= 3:
                stats[f"h{level}"] += 1
            clean_lines.append(clean_inline(heading.group(2)))
            continue

        item = LIST_ITEM_RE.match(raw)
        if item:
            flush_paragraph()
            if not in_list:
                stats["lists"] += 1
                in_list = True
            content = clean_inline(item.group(1))
            clean_lines.append(content)
            list_items.append(content)
            continue

        if in_list and (raw[:1].isspace() or not after_blank):
            # An indented line, or any line right after an item, continues the item.
            content = clean_inline(raw.strip())
            clean_lines.append(content)
            list_items[-1] += " " + content
            continue

        in_list = False
        content = clean_inline(raw.strip().lstrip(">").strip())
        clean_lines.append(content)
        paragraph.append(content)

    flush_paragraph()
    flush_table()

    stats["words"] = sum(count_words(line) for line in clean_lines)
    stats["chars_no_spaces"] = sum(len(re.sub(r"\s", "", line)) for line in clean_lines)

    def sentence_lengths(units: list[str]) -> list[int]:
        return [count_words(sentence) for unit in units for sentence in split_sentences(unit)]

    prose = sentence_lengths(paragraphs)
    stats["avg_sentence_words"] = round(sum(prose) / len(prose), 1) if prose else 0.0
    stats["long_sentences"] = sum(
        1 for n in prose + sentence_lengths(list_items) if n > LONG_SENTENCE_WORDS
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Статистика Markdown-статьи в JSON.")
    parser.add_argument("path", help="путь к .md или '-' для чтения из stdin")
    args = parser.parse_args(argv)

    try:
        if args.path == "-":
            text = sys.stdin.buffer.read().decode("utf-8")
        else:
            path = Path(args.path)
            if not path.is_file():
                print(f"Файл не найден: {path}", file=sys.stderr)
                return 2
            text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Не удалось прочитать ввод как UTF-8: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(compute_stats(text), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
