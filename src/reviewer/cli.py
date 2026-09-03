"""CLI: python -m reviewer review path/to/text.txt --id my-id"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

import typer

from .orchestrator import review as run_review
from .report import render_markdown

app = typer.Typer(add_completion=False, help="Triple-pass text reviewer.")


@app.command()
def review(
    path: str = typer.Argument(..., help="Path to text file, or '-' for stdin."),
    text_id: str = typer.Option(None, "--id", help="Text identifier."),
    out_dir: str = typer.Option("out", "--out-dir"),
    model: str = typer.Option(None, "--model"),
):
    """Run three-pass review on a text file."""
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")

    if not text_id:
        text_id = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    import os
    if model:
        os.environ["MODEL_ID"] = model

    report = asyncio.run(run_review(text, text_id))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{text_id}.md").write_text(render_markdown(report), encoding="utf-8")
    (out / f"{text_id}.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    typer.echo(f"Report written to {out}/{text_id}.md and .json")

    failed_passes = [p for p in report.passes if p.failed]
    if len(failed_passes) == 3:
        raise typer.Exit(2)
    if failed_passes:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
