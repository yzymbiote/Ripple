from ripple import events, export_site, sample


def test_sample_events_only_store_impacts_on_real_paths(conn):
    sample.load_sample_links(conn)
    data = export_site.build(conn)
    link_ids = {l["id"] for l in data["links"]}
    assert len(data["events"]) == 4
    for ev in data["events"]:
        assert ev["is_sample"]
        for imp in ev["impacts"]:
            assert imp["path"][-1] == imp["node_id"]
            assert len(imp["path_links"]) == len(imp["path"]) - 1
            assert set(imp["path_links"]) <= link_ids


def test_invented_impacts_are_dropped(conn):
    sample.load_sample_links(conn)
    ev = events.get_event(conn, "evt_sample_0003")
    cands, _ = events.candidate_impacts(conn, ev)
    result = events.save_impacts(conn, ev["id"], cands, {"nvidia": {"direction": "hurt"}, "hubbell": {"direction": "hurt"}})
    assert result["dropped_invented"] == ["hubbell"]
    assert conn.execute("SELECT COUNT(*) FROM impacts WHERE event_id=? AND node_id='hubbell'", (ev["id"],)).fetchone()[0] == 0


def test_real_only_export_has_no_sample(conn):
    sample.load_sample_links(conn)
    data = export_site.build(conn, include_sample=False)
    assert data["links"] == [] and data["events"] == [] and not data["contains_sample_data"]
