#!/usr/bin/env python3
"""Validate the editorial skills and package each one as a zip for claude.ai.

Usage:
    python scripts/build_editorial_skills.py
    python scripts/build_editorial_skills.py --check
    python scripts/build_editorial_skills.py --src editorial-skills --out dist/editorial-skills

Every folder in --src that does not start with "_" is a skill. Shared files are
kept once in the repo and copied into the skills that need them at build time,
so each zip is self-contained. The same input always gives byte-identical zips.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (source relative to --src, destination inside the skill, skills that receive it).
SHARED_FILES = [
    ("_shared/stop-list.md", "references/stop-list.md", ("seo-copywriter-ru", "seo-editor-ru")),
    ("seo-copywriter-ru/scripts/text_stats.py", "scripts/text_stats.py", ("seo-editor-ru",)),
    ("seo-copywriter-ru/scripts/lint_text.py", "scripts/lint_text.py", ("seo-editor-ru",)),
    ("seo-copywriter-ru/references/craft.md", "references/craft.md", ("seo-editor-ru",)),
    ("seo-copywriter-ru/references/case-balms.md", "references/case-balms.md", ("seo-editor-ru",)),
]

ALLOWED_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9-]{1,64}$")
RESERVED_NAME_WORDS = ("anthropic", "claude")
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 500
FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
# ">", "|-", ">2" and similar block-scalar headers.
BLOCK_SCALAR_RE = re.compile(r"^[>|][0-9+-]*$")
# references/<file> or scripts/<file>, but not another skill's "x/references/<file>".
PATH_RE = re.compile(r"(?<![\w./-])((?:references|scripts)/[\w./-]*\w)")

ZIP_DATE = (1980, 1, 1, 0, 0, 0)
EXCLUDED_NAMES = {"__pycache__", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc"}


class FrontmatterError(ValueError):
    pass


def parse_frontmatter(text: str) -> tuple[dict[str, str], list[str]]:
    """Return (top-level fields, body lines). Supports plain and >/| block values."""
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontmatterError("SKILL.md must start with a '---' frontmatter line")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise FrontmatterError("frontmatter is not closed with '---'") from None

    fields: dict[str, str] = {}
    fm = lines[1:end]
    i = 0
    while i < len(fm):
        line = fm[i]
        i += 1
        match = FIELD_RE.match(line)
        if not match:
            continue  # indented continuation (e.g. metadata map) or blank line
        key, value = match.group(1), match.group(2).strip()
        block: list[str] = []
        while i < len(fm) and (not fm[i].strip() or fm[i][:1].isspace()):
            block.append(fm[i].strip())
            i += 1
        if BLOCK_SCALAR_RE.match(value):
            sep = " " if value.startswith(">") else "\n"
            value = sep.join(part for part in block if part)
        elif value:
            # A plain value may wrap onto indented lines; YAML folds them with spaces.
            value = " ".join([value, *(part for part in block if part)])
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
        fields[key] = value
    return fields, lines[end + 1:]


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in path.parts) or path.suffix in EXCLUDED_SUFFIXES


def skill_dirs(src: Path) -> list[Path]:
    return sorted(
        p for p in src.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))
    )


def injected_files(skill: str) -> set[str]:
    """Paths the build adds to this skill."""
    return {dest for _, dest, targets in SHARED_FILES if skill in targets}


def forbidden_in_source(skill: str) -> set[str]:
    """Build-time copies must not be committed: the build would overwrite them.

    Copies of _shared files are forbidden in every skill, other copies only in
    the skills that receive them.
    """
    shared = {dest for source, dest, _ in SHARED_FILES if source.startswith("_shared/")}
    return shared | injected_files(skill)


def validate_skill(skill_dir: Path, *, source: bool) -> list[str]:
    errors: list[str] = []

    def err(message: str) -> None:
        errors.append(f"{skill_dir.name}: {message}")

    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        err("SKILL.md not found")
        return errors
    try:
        fields, body = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    except FrontmatterError as exc:
        err(str(exc))
        return errors

    name = fields.get("name", "")
    if not NAME_RE.match(name):
        err(f"name {name!r} must match {NAME_RE.pattern}")
    if name != skill_dir.name:
        err(f"name {name!r} does not match folder name {skill_dir.name!r}")
    for word in RESERVED_NAME_WORDS:
        if word in name:
            err(f"name {name!r} must not contain {word!r}")

    description = fields.get("description", "")
    if not description:
        err("description is empty")
    if len(description) > MAX_DESCRIPTION:
        err(f"description is {len(description)} characters, limit is {MAX_DESCRIPTION}")
    if "<" in description or ">" in description:
        err("description must not contain '<' or '>'")

    extra = sorted(set(fields) - ALLOWED_FIELDS)
    if extra:
        err(f"unsupported frontmatter fields: {', '.join(extra)}")

    if len(body) > MAX_BODY_LINES:
        err(f"SKILL.md body is {len(body)} lines, limit is {MAX_BODY_LINES}")

    will_exist = injected_files(skill_dir.name) if source else set()
    for ref in sorted(set(PATH_RE.findall("\n".join(body)))):
        if not (skill_dir / ref).is_file() and ref not in will_exist:
            err(f"SKILL.md references missing file {ref}")

    if source:
        for dest in sorted(forbidden_in_source(skill_dir.name)):
            if (skill_dir / dest).exists():
                err(f"{dest} is a build-time copy and must not be committed")
    return errors


def validate_shared_sources(src: Path, skills: set[str]) -> list[str]:
    errors = []
    for source, _, targets in SHARED_FILES:
        if skills.intersection(targets) and not (src / source).is_file():
            errors.append(f"shared file {source} not found in {src}")
    return errors


def write_zip(skill_dir: Path, zip_path: Path) -> None:
    files = sorted(
        (p.relative_to(skill_dir).as_posix(), p)
        for p in skill_dir.rglob("*")
        if p.is_file() and not is_excluded(p.relative_to(skill_dir))
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, path in files:
            info = zipfile.ZipInfo(f"{skill_dir.name}/{rel}", date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # Unix, so zips match across platforms
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())


def unsafe_out_dir(src: Path, out: Path) -> str | None:
    """Explain why --out must not be cleared, or return None if it is safe."""
    src_abs, out_abs = src.resolve(), out.resolve()
    if out_abs == src_abs or out_abs in src_abs.parents or src_abs in out_abs.parents:
        return f"--out {out} must not overlap --src {src}"
    if not out.exists():
        return None
    if not out.is_dir():
        return f"--out {out} is not a directory"
    # Clear only what a previous build left: skill folders and zips.
    for entry in out.iterdir():
        is_skill = entry.is_dir() and (entry / "SKILL.md").is_file()
        if not (is_skill or (entry.is_file() and entry.suffix == ".zip")):
            return f"--out {out} contains {entry.name}, which is not build output; not clearing it"
    return None


def build(src: Path, out: Path) -> list[str]:
    """Copy skills to out, inject shared files, re-validate and zip. Return errors."""
    skills = skill_dirs(src)
    problem = unsafe_out_dir(src, out)
    if problem:
        return [problem]
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    ignore = shutil.ignore_patterns(*EXCLUDED_NAMES, *(f"*{s}" for s in EXCLUDED_SUFFIXES))
    for skill in skills:
        shutil.copytree(skill, out / skill.name, ignore=ignore)
    for source, dest, targets in SHARED_FILES:
        for target in targets:
            if (out / target).is_dir():
                (out / target / dest).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src / source, out / target / dest)

    errors = [e for skill in skills for e in validate_skill(out / skill.name, source=False)]
    if errors:
        return errors
    for skill in skills:
        write_zip(out / skill.name, out / f"{skill.name}.zip")
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate and zip the editorial skills.")
    ap.add_argument("--src", type=Path, default=REPO_ROOT / "editorial-skills")
    ap.add_argument("--out", type=Path, default=REPO_ROOT / "dist" / "editorial-skills")
    ap.add_argument("--check", action="store_true", help="validate only, do not build")
    args = ap.parse_args(argv)

    if not args.src.is_dir():
        print(f"error: source folder {args.src} not found", file=sys.stderr)
        return 1
    skills = skill_dirs(args.src)
    if not skills:
        print(f"error: no skill folders in {args.src}", file=sys.stderr)
        return 1

    errors = validate_shared_sources(args.src, {s.name for s in skills})
    errors += [e for skill in skills for e in validate_skill(skill, source=True)]
    if not errors and not args.check:
        errors = build(args.src, args.out)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    for skill in skills:
        if args.check:
            print(f"OK {skill.name}")
        else:
            print(f"OK {skill.name} -> {args.out / (skill.name + '.zip')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
