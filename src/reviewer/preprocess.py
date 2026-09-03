"""Paragraph and sentence numbering. Adds [Paragraph N] and [N.M] markers."""
import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[^\s])")


def split_sentences(paragraph: str) -> list[str]:
    paragraph = paragraph.strip()
    if not paragraph:
        return []
    parts = _SENTENCE_SPLIT.split(paragraph)
    return [p.strip() for p in parts if p.strip()]


def number_text(raw: str) -> tuple[str, dict[int, list[str]]]:
    """Return numbered text and an index {paragraph_no: [sentence_texts]}."""
    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT.split(raw.strip()) if p.strip()]
    index: dict[int, list[str]] = {}
    numbered_parts: list[str] = []
    for pi, para in enumerate(paragraphs, start=1):
        sentences = split_sentences(para)
        index[pi] = sentences
        marked = " ".join(
            f"[{pi}.{si}] {s}" for si, s in enumerate(sentences, start=1)
        )
        numbered_parts.append(f"[Paragraph {pi}]\n{marked}")
    return "\n\n".join(numbered_parts), index


_NORMALIZE_WS = re.compile(r"\s+")
_QUOTE_MAP = str.maketrans({
    "«": '"', "»": '"', "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    " ": " ", " ": " ", " ": " ",
})


_EXTRA_MAP = str.maketrans({
    # dashes → hyphen (models love to swap — for -)
    "—": "-", "–": "-", "‒": "-", "―": "-", "−": "-",
    # ё → е so a quote that drops the diaeresis still matches
    "ё": "е", "Ё": "е",
})


def normalize(s: str) -> str:
    """Loosely normalize so a quote still matches after cosmetic model edits.

    Handles: case, whitespace runs, curly/guillemet quotes, dash variants,
    non-breaking spaces, and ё→е. Widens what counts as a verbatim quote just
    enough to survive weak models without accepting genuine fabrications.
    """
    s = s.translate(_QUOTE_MAP).translate(_EXTRA_MAP)
    return _NORMALIZE_WS.sub(" ", s).strip().lower()


def strip_markers(numbered: str) -> str:
    s = re.sub(r"\[Paragraph \d+\]\s*", "", numbered)
    s = re.sub(r"\[\d+\.\d+\]\s*", "", s)
    return s
