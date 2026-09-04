"""Gradio entry point for Hugging Face Spaces (free Gradio SDK)."""
import asyncio
import html
import os
import sys
import time
from collections import deque
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

from reviewer import history
from reviewer.orchestrator import review as run_review
from reviewer.providers import get_provider
from reviewer.schema import ReviewReport
from reviewer.textutils import one_line

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "groq").strip().lower()
try:
    _key_env = get_provider(LLM_PROVIDER).api_key_env
except ValueError:
    _key_env = "GROQ_API_KEY"
_key = os.environ.get(_key_env, "")
print(
    f"[boot] provider={LLM_PROVIDER} · {_key_env} set: {'yes' if _key else 'NO'} "
    f"(len={len(_key)})",
    flush=True,
)


def _key_present() -> bool:
    return bool(os.environ.get(_key_env))


if HAS_SPACES:
    @spaces.GPU(duration=1)
    def _zerogpu_probe():
        """Never called at runtime; exists only to satisfy ZeroGPU startup check."""
        return "ok"


MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "20000"))
PROCESS_MAX_PER_HOUR = int(os.environ.get("PROCESS_MAX_PER_HOUR", "30"))

# Process-wide sliding-window rate limit (protects the API key from runaway loops).
_call_times: deque[float] = deque()


def _rate_limited() -> bool:
    now = time.time()
    while _call_times and now - _call_times[0] > 3600:
        _call_times.popleft()
    if len(_call_times) >= PROCESS_MAX_PER_HOUR:
        return True
    _call_times.append(now)
    return False


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
    m = _re.match(
        r"Pass (p\d) truncated: output hit the token limit, some findings may be missing",
        w,
    )
    if m:
        pid = m.group(1)
        return (
            f"{PASS_LABELS.get(pid, pid)}: ответ модели обрезан по лимиту длины — "
            f"часть замечаний могла потеряться. Уменьшите объём текста или "
            f"поднимите `LLM_MAX_TOKENS`."
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
        parts.append(f"- {html.escape(one_line(d))}")
    if it.fixes:
        parts.append("")
        parts.append("**Как исправить:**")
        for f in it.fixes:
            parts.append(f"- {html.escape(one_line(f))}")
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

    # Footer: what produced this report (helps reproduce results).
    provider = getattr(report, "provider", "") or "—"
    out.append("")
    out.append("---")
    out.append(
        f"<sub>Провайдер: {provider} · Модель: {report.model_id} · "
        f"Версия промта: {report.pass_version}</sub>"
    )

    return "\n".join(out)


def _prose_only(raw: str) -> str:
    """Strip the machine JSON block and retry markers, leaving readable prose."""
    import re as _re
    if not raw:
        return ""
    # Drop the fenced ```json ... ``` contract block(s).
    text = _re.sub(r"```json.*?```", "", raw, flags=_re.DOTALL | _re.IGNORECASE)
    # Drop the internal retry/nudge separator lines.
    lines = [
        ln for ln in text.splitlines()
        if ln.strip() not in ("---retry---", "---nudge-retry---")
    ]
    return "\n".join(lines).strip()


def _fmt_full_passes(report: ReviewReport) -> str:
    """Human-readable prose each pass produced, for the collapsible accordion."""
    out: list[str] = []
    for p in report.passes:
        out.append(f"## {PASS_LABELS.get(p.pass_id, p.pass_id)}")
        out.append("")
        raw = (p.raw_response or "").strip()
        if not raw:
            body = "_Прогон не дал ответа._"
        else:
            prose = _prose_only(raw)
            body = prose if prose else "_Прогон не дал структурированного ответа._"
        out.append(body)
        out.append("")
    return "\n".join(out)


def _base_url(request: gr.Request | None) -> str:
    if request is None:
        return ""
    try:
        host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        proto = request.headers.get("x-forwarded-proto", "https")
        if host:
            return f"{proto}://{host}"
    except Exception:  # noqa: BLE001
        pass
    return ""


def review_text(text: str, text_id: str, request: gr.Request = None,
                progress=gr.Progress()):
    empty_share = ""
    empty_full = ""
    if not text or not text.strip():
        return "⚠️ Пустой текст.", empty_share, empty_full
    if len(text) > MAX_TEXT_CHARS:
        return (
            f"⚠️ Текст слишком длинный: {len(text)} символов при лимите {MAX_TEXT_CHARS}. "
            f"Разбейте его на части и проверьте по отдельности."
        ), empty_share, empty_full
    if not _key_present():
        return (
            f"⚠️ Сервер не настроен: не задан {_key_env} "
            f"(провайдер {LLM_PROVIDER})."
        ), empty_share, empty_full
    if _rate_limited():
        return (
            f"⚠️ Достигнут лимит {PROCESS_MAX_PER_HOUR} проверок в час. "
            f"Подождите немного и повторите."
        ), empty_share, empty_full

    tid = text_id.strip() or "adhoc"
    progress(0.05, desc="Готовлю текст…")

    def _on_progress(done: int, total: int, pass_id: str) -> None:
        frac = 0.1 + 0.8 * done / total
        label = PASS_LABELS.get(pass_id, pass_id)
        progress(frac, desc=f"Готов: {label} ({done} из {total})")

    try:
        report = asyncio.run(run_review(text, tid, on_progress=_on_progress))
    except Exception as e:  # noqa: BLE001 — show the operator the real reason
        return f"⚠️ Ошибка при проверке: {type(e).__name__}: {e}", empty_share, empty_full
    progress(1.0, desc="Готово")

    md = _fmt_report(report)
    full = _fmt_full_passes(report)
    high = sum(1 for c in report.consensus if c.priority == "high")
    low = sum(1 for c in report.consensus if c.priority == "low")
    job_id = history.save(tid, high, low, md)

    base = _base_url(request)
    share = f"🔗 Прямая ссылка на этот отчёт: {base}/?job={job_id}" if base else ""
    return md, share, full


def _load_history() -> list[list]:
    rows = history.recent(30)
    return [[r[0], r[1], r[2].replace("T", " "), r[3], r[4]] for r in rows]


def _open_from_url(request: gr.Request):
    """On page load, if ?job=<id> is present, show that stored report."""
    try:
        job_id = dict(request.query_params).get("job", "") if request else ""
    except Exception:  # noqa: BLE001
        job_id = ""
    if job_id:
        md = history.get(job_id)
        if md:
            return md
    return gr.update()


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
    with gr.Tabs():
        with gr.Tab("Проверка"):
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
                    btn = gr.Button("Проверить в 3 прогона", variant="primary",
                                    size="lg")
                with gr.Column(scale=3):
                    share_line = gr.Markdown("")
                    report_md = gr.Markdown(label="Отчёт")
                    with gr.Accordion("Полные ответы прогонов", open=False):
                        full_passes_md = gr.Markdown("")

        with gr.Tab("История") as history_tab:
            gr.Markdown(
                "Последние проверки на этом сервере. На бесплатном хостинге "
                "история сбрасывается при перезапуске сервиса."
            )
            refresh_btn = gr.Button("Обновить список")
            history_df = gr.Dataframe(
                headers=["job_id", "ID текста", "Когда", "🔴", "🟡"],
                datatype=["str", "str", "str", "number", "number"],
                interactive=False,
                wrap=True,
            )
            open_id = gr.Textbox(
                label="Открыть отчёт по job_id (скопируйте из таблицы)",
                placeholder="например, a1b2c3d4e5f6",
            )
            open_btn = gr.Button("Открыть отчёт")
            history_report = gr.Markdown("")

    btn.click(review_text, [text_in, text_id_in],
              [report_md, share_line, full_passes_md])

    refresh_btn.click(_load_history, None, history_df)
    history_tab.select(_load_history, None, history_df)
    open_btn.click(lambda jid: history.get(jid.strip()) or "_Отчёт не найден._",
                   open_id, history_report)

    # On first load, honour ?job=<id> to deep-link a specific report.
    demo.load(_open_from_url, None, report_md)


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        ssr_mode=False,
    )
