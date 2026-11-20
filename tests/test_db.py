import sqlite3

import pytest


def test_seed_has_38_companies_and_about_50_nodes(conn):
    companies = conn.execute("SELECT COUNT(*) FROM nodes WHERE kind='company'").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    sec = conn.execute("SELECT COUNT(*) FROM nodes WHERE json_extract(extra,'$.filer')='sec'").fetchone()[0]
    assert companies == 38
    assert sec == 23
    assert 45 <= total <= 55


def _doc(conn):
    conn.execute("INSERT INTO documents (id, source, doc_type, collected_at, text) "
                 "VALUES ('doc_1','test','10-K','2026-01-01','Micron sells HBM to Nvidia.')")


def test_link_cannot_be_inserted_approved(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO links (id, from_node, to_node, type, confidence, status) "
                     "VALUES ('link_1','micron','nvidia','supplies','high','approved')")


def test_link_needs_verified_source_before_approval(conn):
    _doc(conn)
    conn.execute("INSERT INTO links (id, from_node, to_node, type, confidence) "
                 "VALUES ('link_1','micron','nvidia','supplies','high')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE links SET status='approved' WHERE id='link_1'")
    conn.execute("INSERT INTO link_sources (link_id, document_id, quote, quote_verified) "
                 "VALUES ('link_1','doc_1','Micron sells HBM to Nvidia.',0)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE links SET status='approved' WHERE id='link_1'")
    conn.execute("UPDATE link_sources SET quote_verified=1 WHERE link_id='link_1'")
    conn.execute("UPDATE links SET status='approved' WHERE id='link_1'")
    # and the last verified source can't then be removed
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM link_sources WHERE link_id='link_1'")
