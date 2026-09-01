from reviewer.consensus import build_consensus
from reviewer.schema import Finding, PassResult


def _pass(pid, findings):
    return PassResult(pass_id=pid, pass_version="test", findings=findings)


def _f(pid, quote, para, cat):
    return Finding(
        quote=quote, paragraph=para, sentence=1, category=cat,
        defect="d", fix="f", source_pass=pid,
    )


def test_two_of_three_is_high():
    p1 = _pass("p1", [_f("p1", "Тест", 1, "logic")])
    p2 = _pass("p2", [_f("p2", "Тест", 1, "logic")])
    p3 = _pass("p3", [])
    items, clean = build_consensus([p1, p2, p3])
    assert len(items) == 1
    assert items[0].priority == "high"
    assert set(items[0].confirmed_by) == {"p1", "p2"}


def test_one_of_three_is_low():
    p1 = _pass("p1", [_f("p1", "Тест", 1, "facts")])
    p2 = _pass("p2", [])
    p3 = _pass("p3", [])
    items, clean = build_consensus([p1, p2, p3])
    assert items[0].priority == "low"
    assert "reader" in clean
    assert "style" in clean


def test_clean_categories_when_all_empty():
    p1 = _pass("p1", [])
    p2 = _pass("p2", [])
    p3 = _pass("p3", [])
    items, clean = build_consensus([p1, p2, p3])
    assert items == []
    assert set(clean) == {"facts", "logic", "style", "reader"}


def test_failed_pass_removes_ownership_from_clean():
    p1 = PassResult(pass_id="p1", pass_version="t", failed=True, failure_reason="x")
    p2 = _pass("p2", [])
    p3 = _pass("p3", [])
    _, clean = build_consensus([p1, p2, p3])
    assert "facts" not in clean
    assert "style" not in clean
    assert "logic" in clean
    assert "reader" in clean
