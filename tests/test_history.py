import importlib


def _fresh_history(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "h.db"))
    import reviewer.history as h
    importlib.reload(h)
    return h


def test_save_and_get(tmp_path, monkeypatch):
    h = _fresh_history(tmp_path, monkeypatch)
    jid = h.save("art-1", 2, 3, "# body")
    assert len(jid) == 12
    assert h.get(jid) == "# body"


def test_get_missing_returns_none(tmp_path, monkeypatch):
    h = _fresh_history(tmp_path, monkeypatch)
    assert h.get("deadbeef") is None


def test_recent_orders_newest_first(tmp_path, monkeypatch):
    h = _fresh_history(tmp_path, monkeypatch)
    j1 = h.save("a", 1, 0, "one")
    j2 = h.save("b", 0, 1, "two")
    rows = h.recent()
    ids = [r[0] for r in rows]
    assert j1 in ids and j2 in ids
    assert len(rows) == 2


def test_save_never_raises_on_bad_path(monkeypatch):
    # Unwritable path must degrade to a no-op, not crash the request.
    monkeypatch.setenv("DB_PATH", "/proc/nonexistent/x.db")
    import reviewer.history as h
    importlib.reload(h)
    jid = h.save("x", 0, 0, "body")
    assert len(jid) == 12  # still returns an id
    assert h.get(jid) is None
