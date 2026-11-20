"""The zero-cost AI route: prepare queue -> (session answers) -> import through checkers; and state save/load."""
import json

import pytest

from ripple import queue, state

TEXT = ("Item 1. Business\nWe sell our products to many customers worldwide.\n"
        "Sales to NVIDIA Corporation accounted for 22% of our net revenue in fiscal 2026, and we depend on this customer.\n"
        "Our wafers are manufactured by Taiwan Semiconductor Manufacturing Company Limited under a supply agreement.\n"
        "We had a nice picnic.\n")


@pytest.fixture
def qdir(tmp_path, monkeypatch):
    monkeypatch.setattr(queue, "WORK_DIR", tmp_path)
    monkeypatch.setattr(queue, "QUEUE_FILE", tmp_path / "queue.json")
    monkeypatch.setattr(queue, "RESULTS_FILE", tmp_path / "results.json")
    monkeypatch.setattr(queue, "HISTORY_DIR", tmp_path / "history")
    return tmp_path


def _filing(conn):
    conn.execute("INSERT INTO documents (id, source, doc_type, company_id, published_at, collected_at, text) "
                 "VALUES ('doc_000001','sec_edgar','10-K','micron','2026-10-09','2026-11-01',?)", (TEXT,))
    conn.execute("INSERT INTO document_sections (document_id, section, text, keyword_hits) VALUES ('doc_000001','customer_concentration',?,4)", (TEXT,))


def test_empty_queue(conn, qdir):
    out = queue.prepare(conn)
    assert out["status"] == "empty"
    assert queue.status()["status"] == "empty"


def test_queue_roundtrip(conn, qdir):
    _filing(conn)
    out = queue.prepare(conn)
    assert out["status"] == "ready" and out["job1_sections"] == 1
    q = json.loads((qdir / "queue.json").read_text())
    task = q["job1_link_extractor"][0]
    assert "picnic" not in task["text"]  # the excerpt keeps only relevant paragraphs
    results = {"queue_id": q["queue_id"], "job1": [{"task_id": task["task_id"], "links": [
        {"type": "supplies", "direction": "filer_to_other", "other_party": "NVIDIA Corporation", "what": "memory", "share": 22,
         "quote": "Sales to NVIDIA Corporation accounted for 22% of our net revenue in fiscal 2026, and we depend on this customer."},
        {"type": "supplies", "direction": "other_to_filer", "other_party": "Taiwan Semiconductor Manufacturing Company Limited",
         "what": "wafers", "share": None,
         "quote": "Our wafers are manufactured by Taiwan Semiconductor Manufacturing Company Limited under a supply agreement."},
        {"type": "supplies", "direction": "filer_to_other", "other_party": "Apple", "what": None, "share": None,
         "quote": "Apple buys most of our chips."}]}], "job2": [], "job3": [{"task_id": "evt_9999"}]}
    report = queue.import_results(conn, results)
    assert report["job1"][0]["linked"] == 2 and report["job1"][0]["rejected"] == 1
    assert report["ignored"] == ["job3 answer for unknown task evt_9999"]
    pairs = {(r["from_node"], r["to_node"], r["status"]) for r in conn.execute("SELECT * FROM links")}
    assert pairs == {("micron", "nvidia", "pending_review"), ("tsmc", "micron", "pending_review")}
    assert queue.status()["status"] == "imported"
    assert "error" in queue.import_results(conn, results)  # can't import twice


def test_wrong_queue_id_refused(conn, qdir):
    _filing(conn)
    queue.prepare(conn)
    assert "error" in queue.import_results(conn, {"queue_id": "old", "job1": []})


def test_state_save_and_load(conn, tmp_path):
    _filing(conn)
    conn.execute("INSERT INTO links (id, from_node, to_node, type, confidence) VALUES ('link_000001','micron','nvidia','supplies','high')")
    conn.execute("INSERT INTO link_sources (link_id, document_id, quote, quote_verified) VALUES ('link_000001','doc_000001','Sales to NVIDIA',1)")
    conn.execute("UPDATE links SET status='approved' WHERE id='link_000001'")
    state.add_alias(conn, "nvidia", "NVIDIA CORP")
    state.save(conn, tmp_path)
    assert "text" not in (tmp_path / "documents.jsonl").read_text()  # filing text isn't saved
    from ripple import db
    fresh = db.connect(":memory:")
    counts = state.load(fresh, tmp_path)
    assert counts["links"] == 1
    assert fresh.execute("SELECT status FROM links").fetchone()[0] == "approved"
    assert fresh.execute("SELECT text FROM documents").fetchone()[0] is None
    assert "NVIDIA CORP" in fresh.execute("SELECT aliases FROM nodes WHERE id='nvidia'").fetchone()[0]


def test_backup_is_off_by_default(monkeypatch):
    from ripple.ai import backup
    monkeypatch.delenv("RIPPLE_BACKUP_AI", raising=False)
    assert backup.provider()[0] is None
    assert "switched_off" in backup.run()
