#!/usr/bin/env python3
"""Deploy this repo to a Hugging Face Space in one command.

Usage:
    python scripts/deploy_hf.py --space theklyou/triple-pass-reviewer
    python scripts/deploy_hf.py --space user/name --message "fix parser"

Token resolution order: --hf-token, HF_TOKEN, HUGGINGFACE_TOKEN, huggingface-cli login cache.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Only these paths reach the Space. Everything else stays local.
ALLOW_PATTERNS = [
    "app.py",
    "requirements.txt",
    "README.md",
    "src/**",
]

IGNORE_PATTERNS = [
    "**/__pycache__/**",
    "**/*.pyc",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/tests/**",
    "**/.env",
    "**/.env.*",
    "**/data/**",
    "**/logs/**",
    "**/out/**",
    "**/*.db",
]

MAX_ATTEMPTS = 3


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def resolve_token(cli_token: str | None) -> str | None:
    return (
        cli_token
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_TOKEN")
        or None  # HfApi falls back to the CLI login cache
    )


def preflight() -> list[str]:
    """Verify the files we are about to upload actually exist."""
    problems = []
    for required in ("app.py", "requirements.txt", "README.md"):
        if not (REPO_ROOT / required).is_file():
            problems.append(f"missing {required}")
    if not (REPO_ROOT / "src" / "reviewer" / "__init__.py").is_file():
        problems.append("missing src/reviewer/__init__.py")
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    if not readme.lstrip().startswith("---"):
        problems.append("README.md has no YAML frontmatter (HF Spaces needs it)")
    elif "sdk: gradio" not in readme.split("---")[1]:
        problems.append("README.md frontmatter does not declare 'sdk: gradio'")
    return problems


def upload(space: str, token: str | None, message: str) -> str:
    from huggingface_hub import HfApi
    from huggingface_hub.utils import HfHubHTTPError

    api = HfApi(token=token)
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            api.upload_folder(
                repo_id=space,
                repo_type="space",
                folder_path=str(REPO_ROOT),
                allow_patterns=ALLOW_PATTERNS,
                ignore_patterns=IGNORE_PATTERNS,
                commit_message=message,
            )
            return f"https://huggingface.co/spaces/{space}"
        except (HfHubHTTPError, OSError) as e:
            last_error = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            # Auth and not-found errors will not fix themselves on retry.
            if status in (401, 403, 404):
                raise
            if attempt < MAX_ATTEMPTS:
                delay = 2 ** attempt
                print(f"  upload failed ({e.__class__.__name__}), retry in {delay}s…",
                      file=sys.stderr)
                time.sleep(delay)

    raise RuntimeError(f"upload failed after {MAX_ATTEMPTS} attempts") from last_error


def main() -> int:
    ap = argparse.ArgumentParser(description="Deploy to a Hugging Face Space.")
    ap.add_argument("--space", required=True, help="Target Space, e.g. user/name")
    ap.add_argument("--hf-token", default=None, help="HF write token (or set HF_TOKEN)")
    ap.add_argument("--message", default=None, help="Commit message")
    ap.add_argument("--skip-preflight", action="store_true",
                    help="Upload even if preflight checks complain")
    args = ap.parse_args()

    problems = preflight()
    if problems:
        for p in problems:
            print(f"preflight: {p}", file=sys.stderr)
        if not args.skip_preflight:
            print("Aborting. Fix the above or pass --skip-preflight.", file=sys.stderr)
            return 2

    message = args.message or f"deploy: {git_sha()}"
    token = resolve_token(args.hf_token)

    print(f"Uploading to Space {args.space} ({message})…")
    try:
        url = upload(args.space, token, message)
    except ImportError:
        print("huggingface_hub is not installed. Run: pip install huggingface_hub",
              file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 — surface the real reason to the operator
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (401, 403):
            print("Auth failed. Create a WRITE token at "
                  "https://huggingface.co/settings/tokens and pass --hf-token "
                  "or set HF_TOKEN.", file=sys.stderr)
        elif status == 404:
            print(f"Space {args.space} not found. Create it first at "
                  "https://huggingface.co/new-space (SDK: Gradio).", file=sys.stderr)
        else:
            print(f"Deploy failed: {e}", file=sys.stderr)
        return 1

    print(f"Done. Space: {url}")
    print("Build status: open the Space and watch the Logs tab (~1-2 min).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
