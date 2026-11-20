"""AI jobs tested with hand-written fake replies — no API calls are made."""
from ripple import config, sample
from ripple.ai import client, jobs
from ripple.matching import NameIndex

DOC = ("Item 1. Business. Our products are assembled by Amkor Technology, Inc. in Korea. "
       "Sales to NVIDIA Corporation accounted for 22% of net revenue in fiscal 2026. "
       "A significant customer accounted for 11% of revenue.")


def _setup(conn):
    conn.execute("INSERT INTO documents (id, source, doc_type, company_id, published_at, collected_at, text) "
                 "VALUES ('doc_000001','sec_edgar','10-K','micron','2026-10-09','2026-11-01',?)", (DOC,))
    conn.execute("INSERT INTO document_sections (document_id, section, text, keyword_hits) VALUES ('doc_000001','item_1',?,3)", (DOC,))
    return conn.execute("SELECT id FROM document_sections").fetchone()[0]


def test_ai_is_off_without_key(conn, monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", None)
    assert client.ai_ready()[0] is False
    assert "switched_off" in jobs.run(conn, "extract-links")


def test_name_matching():
    import sqlite3
    from ripple import db
    from ripple.seed import seed
    c = db.connect(":memory:"); db.init(c); seed(c)
    idx = NameIndex(c)
    assert idx.match("NVIDIA Corporation") == "nvidia"
    assert idx.match("Taiwan Semiconductor Manufacturing Co., Ltd.") == "tsmc"
    assert idx.match("Some Unknown Widget Co") is None
    assert "sk_hynix" in idx.find_in_text("Shares of SK hynix fell after the outage.")


def test_checker_verifies_quotes_matches_names_and_merges(conn):
    sid = _setup(conn)
    reply = {"links": [
        {"type": "supplies", "direction": "filer_to_other", "other_party": "NVIDIA Corporation", "what": "memory", "share": 22,
         "quote": "Sales to NVIDIA Corporation accounted for 22% of net revenue in fiscal 2026."},
        {"type": "supplies", "direction": "other_to_filer", "other_party": "Amkor Technology, Inc.", "what": "assembly", "share": None,
         "quote": "Our products are assembled by Amkor Technology, Inc. in Korea."},
        {"type": "supplies", "direction": "filer_to_other", "other_party": None, "what": None, "share": 11,
         "quote": "A significant customer accounted for 11% of revenue."},
        {"type": "supplies", "direction": "filer_to_other", "other_party": "Apple", "what": None, "share": None,
         "quote": "Apple is our biggest customer."},  # invented: not in the text
    ]}
    stats = jobs.check_and_store_links(conn, sid, reply)
    assert stats == {"linked": 2, "needs_review": 1, "rejected": 1}
    links = {(r["from_node"], r["to_node"]): r for r in conn.execute("SELECT * FROM links")}
    assert ("micron", "nvidia") in links and ("amkor", "micron") in links
    assert all(r["status"] == "pending_review" for r in links.values())  # first pass: a person reviews every link
    assert links[("micron", "nvidia")]["share"] == 22
    # running again on another document merges into the same link with two sources
    conn.execute("INSERT INTO documents (id, source, doc_type, company_id, published_at, collected_at, text) "
                 "VALUES ('doc_000002','sec_edgar','10-Q','micron','2026-12-01','2026-12-02',?)", (DOC,))
    conn.execute("INSERT INTO document_sections (document_id, section, text, keyword_hits) VALUES ('doc_000002','item_1a',?,3)", (DOC,))
    sid2 = conn.execute("SELECT id FROM document_sections WHERE document_id='doc_000002'").fetchone()[0]
    jobs.check_and_store_links(conn, sid2, {"links": reply["links"][:1]})
    assert conn.execute("SELECT COUNT(*) FROM links WHERE from_node='micron' AND to_node='nvidia'").fetchone()[0] == 1
    lid = links[("micron", "nvidia")]["id"]
    assert conn.execute("SELECT COUNT(*) FROM link_sources WHERE link_id=?", (lid,)).fetchone()[0] == 2
    assert conn.execute("SELECT last_confirmed FROM links WHERE id=?", (lid,)).fetchone()[0] == "2026-12-01"
    # verified source exists, so a reviewer can now approve it
    conn.execute("UPDATE links SET status='approved' WHERE id=?", (lid,))


def test_event_checker_rules(conn):
    conn.execute("INSERT INTO documents (id, source, doc_type, published_at, collected_at, text) "
                 "VALUES ('doc_000010','gdelt','news','2026-11-19','2026-11-19','Fire at SK hynix fab')")
    eid = jobs.store_event_check(conn, "doc_000010", ["sk_hynix"], {
        "is_event": True, "event_type": "disruption", "severity": 4,
        "affected_nodes": ["sk_hynix", "tsmc"], "one_line": "A fire hit an SK hynix fab."})
    ev = conn.execute("SELECT * FROM events WHERE id=?", (eid,)).fetchone()
    assert ev["affected_nodes"] == '["sk_hynix"]'  # tsmc wasn't mentioned, so it is dropped
    assert jobs.store_event_check(conn, "doc_000010", ["sk_hynix"], {
        "is_event": False, "event_type": None, "severity": None, "affected_nodes": [], "one_line": "Opinion"}) is None


def test_explainer_output_is_checked(conn):
    sample.load_sample_links(conn)
    event, cands, req = jobs.ripple_explainer_request(conn, "evt_sample_0001", before="2026-03-01")
    assert req["model"] == "claude-opus-5-5" and req["thinking"] == {"type": "adaptive"}
    assert "Do not give buy or sell advice" in req["messages"][0]["content"]
    reply = {"impacts": [
        {"company": "tsmc", "direction": "hurt", "how_much": "high", "why": "uses helium", "timing": "weeks",
         "confidence": "high", "uses_general_knowledge": True, "what_would_change_this": "storage"},
        {"company": "Hubbell", "direction": "hurt", "how_much": "low", "why": "invented", "timing": "a year",
         "confidence": "low", "uses_general_knowledge": False, "what_would_change_this": "x"}],
        "summary": "Short summary.", "biggest_unknowns": ["helium stocks"]}
    result = jobs.store_explanation(conn, "evt_sample_0001", cands, reply)
    assert result["dropped_invented"] == ["hubbell"]
    row = conn.execute("SELECT * FROM impacts WHERE event_id='evt_sample_0001' AND node_id='tsmc'").fetchone()
    assert row["confidence"] == "low"  # general knowledge -> low confidence
