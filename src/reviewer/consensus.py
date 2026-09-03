"""Merge findings from three passes into consensus items."""
from collections import defaultdict

from .preprocess import normalize
from .schema import Category, ConsensusItem, Finding, PassResult

CATEGORY_OWNERS: dict[Category, set[str]] = {
    "facts": {"p1"},
    "logic": {"p1", "p2"},
    "style": {"p1"},
    "reader": {"p3"},
}


def _key(f: Finding) -> tuple[str, int, str]:
    return (normalize(f.quote), f.paragraph, f.category)


def build_consensus(
    passes: list[PassResult],
) -> tuple[list[ConsensusItem], list[Category]]:
    all_findings: list[Finding] = []
    for pr in passes:
        if pr.failed:
            continue
        all_findings.extend(pr.findings)

    groups: dict[tuple[str, int, str], list[Finding]] = defaultdict(list)
    for f in all_findings:
        groups[_key(f)].append(f)

    items: list[ConsensusItem] = []
    for key, findings in groups.items():
        passes_seen = sorted({f.source_pass for f in findings})
        priority = "high" if len(passes_seen) >= 2 else "low"
        first = findings[0]
        items.append(ConsensusItem(
            quote=first.quote,
            paragraph=first.paragraph,
            sentence=first.sentence,
            category=first.category,
            confirmed_by=passes_seen,  # type: ignore[arg-type]
            priority=priority,
            defects=[f"{f.source_pass}: {f.defect}" for f in findings],
            fixes=[f"{f.source_pass}: {f.fix}" for f in findings if f.fix],
        ))

    priority_rank = {"high": 0, "low": 1}
    items.sort(key=lambda i: (priority_rank[i.priority], i.paragraph, i.sentence or 0))

    clean: list[Category] = []
    active_passes = {pr.pass_id for pr in passes if not pr.failed}
    for cat, owners in CATEGORY_OWNERS.items():
        responsible = owners & active_passes
        if not responsible:
            continue
        found_in_cat = any(
            f.category == cat and f.source_pass in responsible
            for f in all_findings
        )
        if not found_in_cat:
            clean.append(cat)

    return items, clean
