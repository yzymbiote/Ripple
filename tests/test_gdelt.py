"""GDELT news collector with a fake API (no network)."""
from ripple.collectors import gdelt


class FakeResp:
    def __init__(self, data, status=200, text="{}"):
        self._data, self.status_code, self.text = data, status, text

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


def test_collect_dedupes_and_stores(conn, monkeypatch):
    arts = [{"url": "https://ex.com/a", "title": "Helium shortage hits Korean chip fabs", "seendate": "20261119T101500Z", "domain": "ex.com"},
            {"url": "https://ex2.com/b", "title": "Helium shortage hits Korean chip fabs!", "seendate": "20261119T111500Z", "domain": "ex2.com"},
            {"url": "https://ex.com/c", "title": "TSMC expands CoWoS capacity", "seendate": "20261120T080000Z", "domain": "ex.com"}]
    calls = []

    def fake_get(self, url, params=None, **kw):
        calls.append(params["query"])
        return FakeResp({"articles": arts if len(calls) == 1 else []})

    monkeypatch.setattr(gdelt.requests.Session, "get", fake_get)
    out = gdelt.collect(conn, sleep=lambda s: None)
    assert out["new_documents"] == 2 and out["duplicates"] == 1  # near-identical headline grouped
    assert all("sourcelang:english" in q for q in calls)
    assert len(calls) == len(range(0, len(gdelt.search_terms(conn)), gdelt.TERMS_PER_QUERY))
    rows = conn.execute("SELECT published_at, doc_type FROM documents WHERE source='gdelt' ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [("2026-11-19", "news"), ("2026-11-20", "news")]
    assert gdelt.collect(conn, sleep=lambda s: None)["new_documents"] == 0  # same URLs never stored twice


def test_search_terms_are_specific():
    import sqlite3
    from ripple import db
    from ripple.seed import seed
    c = db.connect(":memory:"); db.init(c); seed(c)
    terms = gdelt.search_terms(c)
    assert "Meta Platforms" in terms and "Meta" not in terms and "Taiwan" not in terms
