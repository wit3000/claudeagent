import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_editorial_skills.py"
STATS_SCRIPT = REPO_ROOT / "editorial-skills" / "seo-copywriter-ru" / "scripts" / "text_stats.py"
SKILLS = ("seo-copywriter-ru", "seo-editor-ru", "seo-fresh-reader-ru")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load_module("build_editorial_skills", BUILD_SCRIPT)
text_stats = load_module("text_stats", STATS_SCRIPT)


def zip_hashes(out):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.glob("*.zip"))}


# --- build of the real editorial-skills folder ---


def test_build_real_skills(tmp_path):
    out = tmp_path / "out"
    assert build.main(["--out", str(out)]) == 0

    zips = sorted(p.name for p in out.glob("*.zip"))
    assert zips == [f"{name}.zip" for name in SKILLS]

    names = {}
    for skill in SKILLS:
        with zipfile.ZipFile(out / f"{skill}.zip") as zf:
            names[skill] = zf.namelist()
            assert names[skill] == sorted(names[skill])
            assert all(n.startswith(f"{skill}/") for n in names[skill])
            assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in zf.infolist())
            assert not any("__pycache__" in n or n.endswith(".pyc") for n in names[skill])

    assert "seo-copywriter-ru/references/stop-list.md" in names["seo-copywriter-ru"]
    assert "seo-editor-ru/references/stop-list.md" in names["seo-editor-ru"]
    assert not any(n.endswith("stop-list.md") for n in names["seo-fresh-reader-ru"])
    assert "seo-editor-ru/scripts/text_stats.py" in names["seo-editor-ru"]
    assert "seo-editor-ru/scripts/lint_text.py" in names["seo-editor-ru"]


def test_build_is_deterministic(tmp_path):
    out = tmp_path / "out"
    assert build.main(["--out", str(out)]) == 0
    first = zip_hashes(out)
    assert build.main(["--out", str(out)]) == 0
    assert zip_hashes(out) == first
    assert len(first) == 3


def test_check_real_skills_passes(capsys):
    assert build.main(["--check"]) == 0
    assert "OK seo-editor-ru" in capsys.readouterr().out


def test_shared_stop_list_not_committed_into_skills():
    found = sorted(p.relative_to(REPO_ROOT).as_posix()
                   for p in (REPO_ROOT / "editorial-skills").rglob("stop-list.md"))
    assert found == ["editorial-skills/_shared/stop-list.md"]


# --- validation on synthetic skills ---


def make_skill(root, folder="demo-skill", name=None, description="Тестовый навык для проверки.",
               extra_fields="", body="Тело навыка.\n", files=()):
    skill = root / folder
    (skill / "references").mkdir(parents=True)
    name = folder if name is None else name
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra_fields}---\n\n{body}",
        encoding="utf-8",
    )
    for rel in files:
        (skill / rel).write_text("x", encoding="utf-8")
    return skill


def test_check_valid_synthetic_skill(tmp_path):
    make_skill(tmp_path, body="См. references/a.md.\n", files=("references/a.md",))
    assert build.main(["--src", str(tmp_path), "--check"]) == 0


def test_block_description_is_parsed(tmp_path):
    skill = tmp_path / "demo-skill"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: >\n  Первая строка\n  вторая строка.\n---\nТело\n",
        encoding="utf-8",
    )
    fields, body = build.parse_frontmatter((skill / "SKILL.md").read_text(encoding="utf-8"))
    assert fields["description"] == "Первая строка вторая строка."
    assert body == ["Тело"]
    assert build.main(["--src", str(tmp_path), "--check"]) == 0


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "other-skill"}, "does not match folder"),
        ({"folder": "Demo-Skill"}, "must match"),
        ({"folder": "claude-helper"}, "must not contain 'claude'"),
        ({"description": "а" * 1025}, "limit is 1024"),
        ({"description": "Используй для <html> страниц"}, "'<' or '>'"),
        ({"body": "Подробности в references/x.md.\n"}, "missing file references/x.md"),
        ({"extra_fields": "version: 1\n"}, "unsupported frontmatter fields: version"),
        ({"files": ("references/stop-list.md",)}, "must not be committed"),
    ],
    ids=["name-mismatch", "uppercase", "claude", "long-description", "angle-bracket",
         "missing-reference", "extra-field", "committed-stop-list"],
)
def test_check_rejects_broken_skill(tmp_path, capsys, kwargs, message):
    make_skill(tmp_path, **kwargs)
    assert build.main(["--src", str(tmp_path), "--check"]) == 1
    assert message in capsys.readouterr().err


def test_wrapped_plain_description_is_checked(tmp_path):
    make_skill(tmp_path, description="Первая строка\n  вторая <строка>")
    assert build.main(["--src", str(tmp_path), "--check"]) == 1


def test_build_refuses_to_clear_foreign_out_dir(tmp_path, capsys):
    make_skill(tmp_path / "src")
    out = tmp_path / "out"
    out.mkdir()
    (out / "notes.txt").write_text("keep me", encoding="utf-8")
    assert build.main(["--src", str(tmp_path / "src"), "--out", str(out)]) == 1
    assert (out / "notes.txt").exists()
    assert "not build output" in capsys.readouterr().err


# --- text_stats.py ---

ARTICLE = """\
# Заголовок статьи

Первый абзац из **пяти** слов.

## Первый раздел

- пункт один;
- пункт два;
- пункт три.

| Колонка | Значение |
|---|---|
| ячейка | 10 |

## Второй раздел

### Подраздел

1. первый шаг
2. второй шаг
3. третий шаг

Последний абзац тут.

---

## Заметки к сдаче

### Объём и структура

- лишнее слово один
- лишнее слово два
"""

ARTICLE_TEXT = [
    "Заголовок статьи", "Первый абзац из пяти слов.", "Первый раздел",
    "пункт один;", "пункт два;", "пункт три.", "Колонка Значение", "ячейка 10",
    "Второй раздел", "Подраздел", "первый шаг", "второй шаг", "третий шаг",
    "Последний абзац тут.",
]


def test_text_stats_counts_article():
    stats = text_stats.compute_stats(ARTICLE)
    assert stats["h1"] == 1
    assert stats["h2"] == 2
    assert stats["h3"] == 1
    assert stats["lists"] == 2
    assert stats["tables"] == 1
    assert stats["words"] == sum(len(s.split()) for s in ARTICLE_TEXT) == 31
    assert stats["chars_no_spaces"] == len("".join(ARTICLE_TEXT).replace(" ", ""))
    assert stats["avg_sentence_words"] == 4.0
    assert stats["long_sentences"] == 0


def test_text_stats_ignores_notes_words():
    with_notes = text_stats.compute_stats(ARTICLE)
    without_notes = text_stats.compute_stats(ARTICLE.split("\n---\n")[0])
    assert with_notes == without_notes


def test_text_stats_long_sentence():
    sentence = " ".join(["Слово"] + ["слово"] * 25) + "."
    stats = text_stats.compute_stats(f"Короткое предложение тут. {sentence}\n")
    assert stats["long_sentences"] == 1
    assert stats["avg_sentence_words"] == 14.5


def run_stats(*args, stdin=""):
    return subprocess.run(
        [sys.executable, str(STATS_SCRIPT), *args],
        input=stdin.encode("utf-8"), capture_output=True, timeout=30,
    )


def test_text_stats_cli_file(tmp_path):
    article = tmp_path / "article.md"
    article.write_text(ARTICLE, encoding="utf-8")
    result = run_stats(str(article))
    assert result.returncode == 0
    assert json.loads(result.stdout)["words"] == 31


def test_text_stats_empty_input_gives_zeros():
    result = run_stats("-", stdin="")
    assert result.returncode == 0
    assert all(value == 0 for value in json.loads(result.stdout).values())


def test_text_stats_missing_file(tmp_path):
    result = run_stats(str(tmp_path / "nope.md"))
    assert result.returncode == 2
    assert result.stderr
