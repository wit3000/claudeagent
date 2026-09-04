"""Small text helpers shared across rendering paths."""


def one_line(text: str) -> str:
    """Collapse internal whitespace so a multi-line value stays one list item."""
    return " ".join(text.split())
