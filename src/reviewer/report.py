"""Render ReviewReport as Markdown."""
from .schema import ReviewReport
from .textutils import one_line


def render_markdown(report: ReviewReport) -> str:
    lines: list[str] = []
    lines.append(f"# Review report — {report.text_id}")
    lines.append(
        f"Model: `{report.model_id}` · Pass version: `{report.pass_version}` "
        f"· Generated: {report.created_at.isoformat()}"
    )
    lines.append("")

    high = [c for c in report.consensus if c.priority == "high"]
    low = [c for c in report.consensus if c.priority == "low"]

    lines.append("## Summary")
    lines.append(f"- High-priority findings: **{len(high)}**")
    lines.append(f"- Low-priority findings: **{len(low)}**")
    lines.append(f"- Clean categories: {', '.join(report.clean_categories) or '—'}")
    lines.append("")

    if report.warnings:
        lines.append("## Warnings")
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## Passes")
    for pr in report.passes:
        status = "FAILED" if pr.failed else "ok"
        lines.append(
            f"- **{pr.pass_id}** [{status}] · latency {pr.latency_ms} ms · "
            f"tokens in/out {pr.tokens_in}/{pr.tokens_out} · "
            f"findings {len(pr.findings)} · hallucinated {pr.hallucinated_count}"
        )
    lines.append("")

    def _render_group(title: str, items):
        lines.append(f"## {title}")
        if not items:
            lines.append("_None._\n")
            return
        for it in items:
            loc = f"Paragraph {it.paragraph}"
            if it.sentence is not None:
                loc += f", sentence {it.sentence}"
            confirmed = ", ".join(it.confirmed_by)
            lines.append(f"### [{loc}] · {it.category} · confirmed by {confirmed}")
            lines.append(f"> {it.quote}")
            lines.append("")
            lines.append("**Defects:**")
            for d in it.defects:
                lines.append(f"- {one_line(d)}")
            if it.fixes:
                lines.append("")
                lines.append("**Suggested fixes:**")
                for f in it.fixes:
                    lines.append(f"- {one_line(f)}")
            lines.append("")

    _render_group("High-priority findings", high)
    _render_group("Low-priority findings", low)

    return "\n".join(lines)
