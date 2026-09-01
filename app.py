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
from reviewer.report import render_markdown
from reviewer.schema import ReviewReport


if HAS_SPACES:
    @spaces.GPU(duration=1)
    def _zerogpu_probe():
        """Never called at runtime; exists only to satisfy ZeroGPU startup check."""
        return "ok"


MAX_TEXT_CHARS = int(os.environ.get("MAX_TEXT_CHARS", "20000"))


def _fmt_passes(report: ReviewReport) -> str:
    rows = []
    for p in report.passes:
        if p.failed:
            rows.append(f"- **{p.pass_id}** · ❌ FAILED · {p.failure_reason}")
        else:
            rows.append(
                f"- **{p.pass_id}** · {p.latency_ms} ms · "
                f"findings {len(p.findings)} · hallucinated {p.hallucinated_count}"
            )
    return "\n".join(rows)


def _fmt_finding(it) -> str:
    loc = f"Paragraph {it.paragraph}"
    if it.sentence is not None:
        loc += f", sentence {it.sentence}"
    quote = html.escape(it.quote)
    defects = "\n".join(f"- {html.escape(d)}" for d in it.defects)
    fixes = "\n".join(f"- {html.escape(f)}" for f in it.fixes) if it.fixes else ""
    parts = [
        f"### [{loc}] · {it.category} · confirmed by {', '.join(it.confirmed_by)}",
        f"> {quote}",
        "",
        "**Defects:**",
        defects,
    ]
    if fixes:
        parts += ["", "**Fixes:**", fixes]
    return "\n".join(parts)


def _fmt_report(report: ReviewReport) -> str:
    high = [c for c in report.consensus if c.priority == "high"]
    low = [c for c in report.consensus if c.priority == "low"]
    out = [
        f"### Summary",
        f"- High-priority findings: **{len(high)}**",
        f"- Low-priority findings: **{len(low)}**",
        f"- Clean categories: {', '.join(report.clean_categories) or '—'}",
        "",
        f"### Passes",
        _fmt_passes(report),
    ]
    if report.warnings:
        out += ["", "### Warnings"] + [f"- ⚠️ {w}" for w in report.warnings]
    out += ["", "### High-priority findings"]
    out += [_fmt_finding(f) for f in high] or ["_None._"]
    out += ["", "### Low-priority findings"]
    out += [_fmt_finding(f) for f in low] or ["_None._"]
    return "\n\n".join(out)


def review_text(text: str, text_id: str, progress=gr.Progress()):
    if not text or not text.strip():
        return "⚠️ Empty text.", ""
    if len(text) > MAX_TEXT_CHARS:
        return f"⚠️ Too long: {len(text)} chars (max {MAX_TEXT_CHARS}).", ""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "⚠️ Server misconfigured: ANTHROPIC_API_KEY is not set.", ""

    tid = text_id.strip() or "adhoc"
    progress(0.1, desc="Running 3 parallel passes...")
    report = asyncio.run(run_review(text, tid))
    progress(1.0, desc="Done")
    return _fmt_report(report), render_markdown(report)


SAMPLE = """Компания X запустила продукт в 2019 году. За первый год они привлекли 50 000 пользователей.

К 2020 году база выросла до 500 000, что в десять раз больше. Однако рост во втором году был скромным.

Мы уверены, что дальнейший рост неизбежен, потому что тренд очевиден."""


with gr.Blocks(title="Triple-Pass Text Reviewer") as demo:
    gr.Markdown(
        "# 🔍 Triple-Pass Text Reviewer\n"
        "Три независимых LLM-прогона (технический вычитчик · логик-придира · читатель без контекста), "
        "консенсус по правилу 2-из-3, дословная привязка цитат к тексту."
    )
    with gr.Row():
        with gr.Column(scale=2):
            text_in = gr.Textbox(
                label="Text to review",
                lines=14,
                placeholder="Вставьте текст...",
                value=SAMPLE,
            )
            text_id_in = gr.Textbox(label="Text ID (optional)", value="")
            btn = gr.Button("Run 3-pass review", variant="primary")
        with gr.Column(scale=3):
            report_md = gr.Markdown(label="Report")
            with gr.Accordion("Raw Markdown (copy for docs)", open=False):
                raw_md = gr.Textbox(label="", lines=20, show_copy_button=True)
    btn.click(review_text, [text_in, text_id_in], [report_md, raw_md])


if __name__ == "__main__":
    demo.queue().launch(
        server_name="0.0.0.0",
        server_port=int(os.environ.get("PORT", 7860)),
        ssr_mode=False,
    )
