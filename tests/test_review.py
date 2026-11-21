"""Review queue actions (no web server needed)."""
import pytest

from ripple import review_server


@pytest.fixture
def rconn(conn, monkeypatch):
    monkeypatch.setattr(review_server, "_save", lambda c: c.commit())
    conn.execute("INSERT INTO documents (id, source, doc_type, company_id, published_at, collected_at, text) "
                 "VALUES ('doc_000001','sec_edgar','10-K','nvidia','2026-02-25','2026-11-01','x')")
    conn.execute("INSERT INTO links (id, from_node, to_node, type, confidence, first_seen, last_confirmed) "
                 "VALUES ('link_000001','tsmc','nvidia','supplies','high','2026-02-25','2026-02-25')")
    conn.execute("INSERT INTO link_sources (link_id, document_id, quote, quote_verified) VALUES ('link_000001','doc_000001','q',1)")
    conn.execute("INSERT INTO link_candidates (document_id, filer_node, other_party, type, direction, what, quote, quote_verified, status) "
                 "VALUES ('doc_000001','nvidia','Hon Hai Precision Industry Co., Ltd.','supplies','other_to_filer','assembly','We engage Hon Hai.',1,'needs_review')")
    return conn


def test_approve_reject_edit(rconn):
    assert review_server.act_on_link(rconn, "link_000001", {"action": "approve"}) == {"ok": True}
    assert rconn.execute("SELECT status FROM links").fetchone()[0] == "approved"
    out = review_server.act_on_link(rconn, "link_000001", {"action": "edit", "fields": {
        "from_node": "tsmc", "to_node": "nvidia", "type": "supplies", "what": "AI chips", "share": "19", "confidence": "high"}})
    assert out == {"ok": True}
    assert tuple(rconn.execute("SELECT what, share FROM links").fetchone()) == ("AI chips", 19.0)
    assert "error" in review_server.act_on_link(rconn, "link_000001", {"action": "edit", "fields": {
        "from_node": "nope", "to_node": "nvidia", "type": "supplies", "confidence": "high"}})
    review_server.act_on_link(rconn, "link_000001", {"action": "reject"})
    assert rconn.execute("SELECT status FROM links").fetchone()[0] == "rejected"


def test_unverified_link_cannot_be_approved(rconn):
    rconn.execute("UPDATE link_sources SET quote_verified=0")
    assert "error" in review_server.act_on_link(rconn, "link_000001", {"action": "approve"})


def test_candidate_becomes_pending_link_and_remembers_alias(rconn):
    cid = rconn.execute("SELECT id FROM link_candidates").fetchone()[0]
    assert review_server.act_on_candidate(rconn, cid, {"action": "link", "other_node": "foxconn", "add_alias": True}) == {"ok": True}
    link = rconn.execute("SELECT * FROM links WHERE from_node='foxconn'").fetchone()
    assert link["to_node"] == "nvidia" and link["status"] == "pending_review"
    assert "Hon Hai" in rconn.execute("SELECT aliases FROM nodes WHERE id='foxconn'").fetchone()[0]
    assert rconn.execute("SELECT status FROM link_candidates").fetchone()[0] == "linked"


def test_unnamed_candidate_can_be_shown_as_placeholder(rconn):
    rconn.execute("INSERT INTO link_candidates (document_id, filer_node, other_party, type, direction, share, quote, quote_verified, status) "
                  "VALUES ('doc_000001','nvidia',NULL,'supplies','filer_to_other',22,'one direct customer represented 22%',1,'needs_review')")
    named = rconn.execute("SELECT id FROM link_candidates WHERE other_party IS NOT NULL").fetchone()[0]
    unnamed = rconn.execute("SELECT id FROM link_candidates WHERE other_party IS NULL").fetchone()[0]
    assert "error" in review_server.act_on_candidate(rconn, named, {"action": "placeholder"})
    assert review_server.act_on_candidate(rconn, unnamed, {"action": "placeholder"}) == {"ok": True}
    from ripple import export_site
    assert export_site.build(rconn, include_sample=False)["unnamed"][0]["share"] == 22


def test_daily_review_apply_logs_and_respects_rules(rconn, tmp_path, monkeypatch):
    from ripple import daily_review, queue
    monkeypatch.setattr(queue, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(daily_review, "HISTORY_DIR", tmp_path)
    cid = rconn.execute("SELECT id FROM link_candidates").fetchone()[0]
    out = daily_review.apply(rconn, {
        "links": [{"link_id": "link_000001", "decision": "approve", "confidence": "medium", "reason": "quote names TSMC"}],
        "candidates": [{"candidate_id": cid, "decision": "reject", "reason": "not on map, off-topic"}]})
    assert out["counts"] == {"approve": 1, "reject": 1} and out["errors"] == []
    row = rconn.execute("SELECT status, confidence FROM links WHERE id='link_000001'").fetchone()
    assert tuple(row) == ("approved", "medium")
    assert list(tmp_path.glob("*-review-log.json"))
