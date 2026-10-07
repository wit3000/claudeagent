import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_SCRIPT = REPO_ROOT / "editorial-skills" / "seo-copywriter-ru" / "scripts" / "lint_text.py"
BAD_ARTICLE = REPO_ROOT / "tests" / "fixtures" / "balms_bad.md"


def load_lint():
    spec = importlib.util.spec_from_file_location("lint_text", LINT_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["lint_text"] = module  # dataclasses look the module up by name
    spec.loader.exec_module(module)
    return module


lint_text = load_lint()


def categories(text):
    return {(f.level, f.category) for f in lint_text.lint(text)}


def quotes(text, category):
    return [f.quote for f in lint_text.lint(text) if f.category == category]


def test_stop_list_phrase_is_error():
    found = lint_text.lint("Важно отметить, что компания осуществляет доставку.\n")
    assert {f.quote.lower() for f in found if f.level == "error"} >= {"важно отметить", "осуществляет"}


def test_register_word_is_warning():
    assert quotes("## Как подобрать бальзам под свою задачу\n", "слово не из темы") == ["задачу"]


def test_markers_and_links_are_ignored():
    text = 'Цена [нужны данные: цена "от"] на [сайте](https://a.ru/x-1 "t").\n'
    assert lint_text.lint(text) == []


def test_typography():
    found = quotes('Срок 3-5 суток - "быстро", цена 15 руб. и pH 4.5.\n', "типографика")
    assert set(found) >= {"3-5", " - ", '"', "руб.", "4.5"}


def test_polite_form_mid_sentence_only():
    assert quotes("Мы пришлём Вам расчёт.\n", "типографика") == ["Вам"]
    assert quotes("Вам пришлём расчёт.\n", "типографика") == []


def test_choppy_paragraph_without_links():
    text = "Кондиционер для волос. Объём 200 мл. Есть масло ши. Нет парабенов. Подходит всем.\n"
    found = categories(text)
    assert ("warn", "рубленый ритм") in found
    assert ("warn", "нет связок") in found


def test_linked_paragraph_passes():
    text = (
        "Сухие волосы путаются после мытья. Им не хватает влаги, поэтому нужен бальзам с маслами. "
        "Например, подойдёт средство с маслом ши. Но на тонких волосах его наносят только на кончики.\n"
    )
    found = categories(text)
    assert ("warn", "нет связок") not in found
    assert ("warn", "рубленый ритм") not in found


def test_template_labels_and_attribution():
    card = "### Бальзам\n\nПроизводитель обещает блеск. По отзывам, мягкость.\n\n- Кому подойдёт: всем.\n"
    found = lint_text.lint(card * 3)
    assert any(f.category == "шаблон" and "×3" in f.quote for f in found)
    assert sum(f.category == "оговорки" for f in found) == 3


def test_repeated_wording_across_paragraphs():
    sentence = "Флакона на двести миллилитров на длинные волосы хватит ненадолго."
    assert quotes(f"{sentence}\n\nДругой абзац. {sentence}\n", "повтор мысли")


def test_notes_block_is_skipped():
    text = "Текст статьи.\n\n---\n\n## Заметки к сдаче\n\nВажно отметить, что осуществляем.\n"
    assert lint_text.lint(text) == []


def test_failed_article_is_caught():
    found = lint_text.lint(BAD_ARTICLE.read_text(encoding="utf-8"))
    cats = {f.category for f in found}
    assert {"стоп-лист", "слово не из темы", "шаблон", "нет связок", "оговорки", "типографика"} <= cats
    assert sum(f.quote.lower().startswith("задач") for f in found) >= 3


def run(*args, stdin=""):
    return subprocess.run([sys.executable, str(LINT_SCRIPT), *args],
                          input=stdin.encode("utf-8"), capture_output=True, timeout=30)


def test_cli_exit_codes(tmp_path):
    clean = tmp_path / "clean.md"
    clean.write_text("Перевозим грузы из Москвы в Красноярск.\n", encoding="utf-8")
    assert run(str(clean)).returncode == 0
    assert run(str(BAD_ARTICLE)).returncode == 1
    assert run(str(tmp_path / "nope.md")).returncode == 2


def test_cli_json():
    result = run("-", "--json", stdin="Компания осуществляет доставку.\n")
    data = json.loads(result.stdout)
    assert data[0]["level"] == "error"
    assert result.returncode == 1


def test_rewritten_article_is_clean():
    good = lint_text.lint((REPO_ROOT / "tests" / "fixtures" / "balms_rewrite.md").read_text(encoding="utf-8"))
    bad = lint_text.lint(BAD_ARTICLE.read_text(encoding="utf-8"))
    assert not any(f.level == "error" for f in good)
    assert not {f.category for f in good} & {"шаблон", "нет связок", "рубленый ритм", "оговорки"}
    assert len(good) * 2 < len(bad)
