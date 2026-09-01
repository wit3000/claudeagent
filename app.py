"""Gradio entry point for Hugging Face Spaces (free Gradio SDK)."""
import asyncio
import html
import os
import sys
from pathlib import Path

# Make the src/ layout importable without pip install (needed on HF Spaces).
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import gradio as gr

# HF ZeroGPU containers require at least one @spaces.GPU function at startup,
# even if we never invoke GPU (we only call Anthropic over the network).
try:
    import spaces  # type: ignore
    HAS_SPACES = True
except ImportError:
    HAS_SPACES = False

from reviewer.orchestrator import review as run_review
from reviewer.schema import ReviewReport

_key = os.environ.get("GROQ_API_KEY", "")
print(
    f"[boot] GROQ_API_KEY set: {'yes' if _key else 'NO'} "
    f"(len={len(_key)}, starts_with={_key[:5] if _key else '-'})",
    flush=True,
)


if HAS_SPACES:
    @spaces.GPU(duration=1)
    def _zerogpu_probe():
        """Never called at runtime; exists only to satisfy ZeroGPU startup check."""
        return "ok"


MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "20000"))


CATEGORY_LABELS = {
    "facts": "Факты",
    "logic": "Логика",
    "style": "Стиль",
    "reader": "Читательский взгляд",
}
CATEGORY_ORDER = ["facts", "logic", "style", "reader"]
PRIORITY_LABEL = {"high": "🔴 Высокий приоритет", "low": "🟡 Низкий приоритет"}
PASS_LABELS = {
    "p1": "Прогон 1 · Технический вычитчик",
    "p2": "Прогон 2 · Логик-придира",
    "p3": "Прогон 3 · Читатель без контекста",
}
PASS_SHORT = {"p1": "Прогон 1", "p2": "Прогон 2", "p3": "Прогон 3"}


def _translate_warning(w: str) -> str:
    """Turn the orchestrator's English warnings into human Russian."""
    import re as _re
    m = _re.match(r"Pass (p\d) unreliable: (\d+)/(\d+) findings hallucinated", w)
    if m:
        pid, hall, total = m.group(1), m.group(2), m.group(3)
        return (
            f"{PASS_LABELS.get(pid, pid)}: модель придумала цитаты, которых нет в тексте, "
            f"в {hall} случаях из {total}. Отброшены автоматически, но замечания этого прогона "
            f"на этом тексте лучше перепроверять вручную."
        )
    m = _re.match(r"Pass (p\d): (\d+) findings excluded as hallucinated", w)
    if m:
        pid, hall = m.group(1), m.group(2)
        return (
            f"{PASS_LABELS.get(pid, pid)}: {hall} замечание(-й) отброшено как галлюцинация "
            f"(цитата отсутствует в исходнике). На итог не влияет."
        )
    m = _re.match(r"Pass (p\d) failed: (.+)", w)
    if m:
        pid, reason = m.group(1), m.group(2)
        return f"{PASS_LABELS.get(pid, pid)} упал: {reason}"
    return w


def _fmt_passes(report: ReviewReport) -> str:
    rows = ["| Прогон | Статус | Задержка | Дефектов | Отброшено |",
            "|---|---|---:|---:|---:|"]
    for p in report.passes:
        label = PASS_LABELS.get(p.pass_id, p.pass_id)
        if p.failed:
            rows.append(f"| {label} | ❌ ошибка | — | — | — |")
        else:
            rows.append(
                f"| {label} | ✅ ок | {p.latency_ms} ms | "
                f"{len(p.findings)} | {p.hallucinated_count} |"
            )
    return "\n".join(rows)


def _fmt_finding(idx: int, it) -> str:
    loc = f"Абзац {it.paragraph}"
    if it.sentence is not None:
        loc += f", предл. {it.sentence}"
    quote = html.escape(it.quote)
    confirmed = ", ".join(it.confirmed_by)
    parts = [
        f"**{idx}. {loc}** · подтверждено: `{confirmed}`",
        "",
        f"> {quote}",
        "",
        "**В чём проблема:**",
    ]
    for d in it.defects:
        parts.append(f"- {html.escape(d)}")
    if it.fixes:
        parts.append("")
        parts.append("**Как исправить:**")
        for f in it.fixes:
            parts.append(f"- {html.escape(f)}")
    return "\n".join(parts)


def _fmt_report(report: ReviewReport) -> str:
    total = len(report.consensus)
    high = [c for c in report.consensus if c.priority == "high"]
    low = [c for c in report.consensus if c.priority == "low"]

    out = [
        "## Итоги проверки",
        "",
        f"- Найдено дефектов всего: **{total}**",
        f"  - 🔴 Высокий приоритет (нашли 2–3 прогона): **{len(high)}** — правь сразу.",
        f"  - 🟡 Низкий приоритет (нашёл 1 прогон): **{len(low)}** — проверь точечно.",
    ]
    if report.clean_categories:
        clean_ru = ", ".join(CATEGORY_LABELS.get(c, c) for c in report.clean_categories)
        out.append(f"- Категории без замечаний: **{clean_ru}**")
    out.append("")

    if report.warnings:
        out.append("## ⚠️ Предупреждения")
        out.append("")
        for w in report.warnings:
            out.append(f"- {_translate_warning(w)}")
        out.append("")

    out.append("## Статус прогонов")
    out.append("")
    out.append(_fmt_passes(report))
    out.append("")

    # Findings grouped by category, in canonical order, high before low inside.
    by_cat: dict[str, list] = {c: [] for c in CATEGORY_ORDER}
    for c in report.consensus:
        by_cat.setdefault(c.category, []).append(c)

    idx = 0
    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat, [])
        if not items:
            continue
        items.sort(key=lambda it: (0 if it.priority == "high" else 1,
                                   it.paragraph, it.sentence or 0))
        out.append(f"## {CATEGORY_LABELS[cat]}")
        out.append("")
        current_priority = None
        for it in items:
            if it.priority != current_priority:
                current_priority = it.priority
                out.append(f"### {PRIORITY_LABEL[current_priority]}")
                out.append("")
            idx += 1
            out.append(_fmt_finding(idx, it))
            out.append("")

    if total == 0:
        out.append("_Дефектов не обнаружено. Текст можно публиковать._")

    return "\n".join(out)


def review_text(text: str, text_id: str, progress=gr.Progress()):
    if not text or not text.strip():
        return "⚠️ Пустой текст."
    if len(text) > MAX_TEXT_CHARS:
        return f"⚠️ Слишком длинный текст: {len(text)} символов (максимум {MAX_TEXT_CHARS})."
    if not os.environ.get("GROQ_API_KEY"):
        return "⚠️ Сервер не настроен: не задан GROQ_API_KEY."

    tid = text_id.strip() or "adhoc"
    progress(0.1, desc="Запускаю три параллельных прогона…")
    report = asyncio.run(run_review(text, tid))
    progress(1.0, desc="Готово")
    return _fmt_report(report)


SAMPLE = """Компания X запустила продукт в 2019 году. За первый год они привлекли 50 000 пользователей.

К 2020 году база выросла до 500 000, что в десять раз больше. Однако рост во втором году был скромным.

Мы уверены, что дальнейший рост неизбежен, потому что тренд очевиден."""


with gr.Blocks(title="Проверка текста в 3 прогона") as demo:
    gr.Markdown(
        "# 🔍 Проверка текста в 3 прогона\n"
        "Три независимых прогона: **технический вычитчик** · **логик-придира** · "
        "**читатель без контекста**.  \n"
        "Каждый прогон обязан цитировать текст дословно — иначе дефект отбрасывается. "
        "Дефект, найденный 2–3 прогонами, считается подтверждённым и получает высокий приоритет."
    )
    with gr.Row():
        with gr.Column(scale=2):
            text_in = gr.Textbox(
                label="Текст на проверку",
                lines=14,
                placeholder="Вставьте текст сюда…",
                value=SAMPLE,
            )
            text_id_in = gr.Textbox(
                label="ID текста (необязательно)",
                placeholder="например, статья-о-запуске",
                value="",
            )
            btn = gr.Button("Проверить в 3 прогона", variant="primary", size="lg")
        with gr.Column(scale=3):
            report_md = gr.Markdown(label="Отчёт")
    btn.click(review_text, [text_in, text_id_in], [report_md])


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        ssr_mode=False,
    )
