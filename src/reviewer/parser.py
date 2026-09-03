"""Parse the JSON block emitted by each pass and validate findings."""
import json
import re

from .passes import ALLOWED_CATEGORIES
from .preprocess import normalize
from .schema import Finding, PassId

_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_BLOCK_LOOSE = re.compile(r"\{[^{}]*\"findings\"[^{}]*\}", re.DOTALL)


class ParseError(Exception):
    pass


def extract_json(raw: str) -> dict:
    matches = _JSON_BLOCK.findall(raw)
    if matches:
        blob = matches[-1]
    else:
        m = re.search(r"\{.*\"findings\".*\}", raw, re.DOTALL)
        if not m:
            raise ParseError("No JSON block found in model reply")
        blob = m.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError as e:
        raise ParseError(f"Malformed JSON: {e}") from e


def parse_pass(
    raw: str,
    pass_id: PassId,
    source_text: str,
    max_paragraph: int,
) -> tuple[list[Finding], int]:
    """Return (valid findings, hallucinated_count). Cross-validated."""
    data = extract_json(raw)
    findings_data = data.get("findings", [])
    if not isinstance(findings_data, list):
        raise ParseError("`findings` is not a list")

    allowed = ALLOWED_CATEGORIES[pass_id]
    norm_source = normalize(source_text)

    valid: list[Finding] = []
    hallucinated = 0
    seen_keys: set[tuple[str, int, str]] = set()

    for item in findings_data:
        if not isinstance(item, dict):
            continue
        try:
            quote = str(item["quote"]).strip()
            paragraph = int(item["paragraph"])
            sentence = item.get("sentence")
            sentence = int(sentence) if sentence not in (None, "", "null") else None
            category = str(item["category"]).strip().lower()
            defect = str(item.get("defect", "")).strip()
            fix = str(item.get("fix", "")).strip()
        except (KeyError, ValueError, TypeError):
            continue

        if category not in allowed:
            continue
        if not quote or paragraph < 1 or paragraph > max_paragraph:
            continue

        key = (normalize(quote), paragraph, category)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        if normalize(quote) not in norm_source:
            hallucinated += 1
            continue

        valid.append(Finding(
            quote=quote,
            paragraph=paragraph,
            sentence=sentence,
            category=category,  # type: ignore[arg-type]
            defect=defect,
            fix=fix,
            source_pass=pass_id,
        ))

    return valid, hallucinated
