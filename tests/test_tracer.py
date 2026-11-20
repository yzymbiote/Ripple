"""Tests for the ripple tracer, using the hand-made SAMPLE links."""
import pytest

from ripple import sample, tracer


@pytest.fixture
def g(conn):
    sample.load_sample_links(conn)
    return tracer.build_graph(conn, before="2026-03-01")


def by_id(results):
    return {r["node_id"]: r for r in results}


def test_sample_links_are_approved_and_marked(conn):
    sample.load_sample_links(conn)
    rows = conn.execute("SELECT status, is_sample FROM links").fetchall()
    assert rows and all(r["status"] == "approved" and r["is_sample"] == 1 for r in rows)


def test_helium_reaches_korean_and_taiwanese_chipmakers_within_3_steps(g):
    res = by_id(tracer.trace(g, ["ras_laffan", "helium"]))
    for company in ("sk_hynix", "samsung", "tsmc"):
        assert company in res and res[company]["steps"] <= 3


def test_paths_never_exceed_4_steps_and_follow_real_links(g):
    links = tracer.link_index(g)
    for r in tracer.trace(g, ["ras_laffan", "helium"], max_steps=4):
        assert 1 <= r["steps"] <= 4
        for p in r["all_paths"]:
            assert len(p["links"]) <= 4
            assert all(lid in links for lid in p["links"])


def test_cloud_buyers_reached_through_chips(g):
    res = by_id(tracer.trace(g, ["helium"]))
    assert res["microsoft"]["path"][:2] == ["helium", "tsmc"] or res["microsoft"]["path"][:2] == ["helium", "sk_hynix"]
    assert res["microsoft"]["steps"] == 3
    # direct users are more exposed than their customers' customers
    assert res["tsmc"]["exposure_score"] > res["microsoft"]["exposure_score"]


def test_step_limit(g):
    res = by_id(tracer.trace(g, ["ras_laffan"], max_steps=2))
    assert "microsoft" not in res  # 4+ steps away
    assert "qatarenergy" in res


def test_before_filter_drops_later_links(conn):
    sample.load_sample_links(conn)
    later = tracer.build_graph(conn)  # no date filter: includes micron -> amd (first seen 2026-06)
    earlier = tracer.build_graph(conn, before="2026-03-01")
    assert later.number_of_edges() == earlier.number_of_edges() + 1
    amd_paths_later = {tuple(p["path"]) for p in by_id(tracer.trace(later, ["helium"]))["amd"]["all_paths"]}
    amd_paths_earlier = {tuple(p["path"]) for p in by_id(tracer.trace(earlier, ["helium"]))["amd"]["all_paths"]}
    assert ("helium", "micron", "amd") in amd_paths_later
    assert ("helium", "micron", "amd") not in amd_paths_earlier


def test_alternative_helium_producers_are_possible_winners(g):
    reached = {r["node_id"] for r in tracer.trace(g, ["ras_laffan", "helium"], companies_only=False)}
    winners = {w["node_id"] for w in tracer.possible_winners(g, ["ras_laffan", "helium"], reached)}
    assert {"linde", "air_products"} <= winners
    assert "tsmc" not in winners


def test_link_strength_rules():
    L = tracer.Link
    strong = L("a", "x", "y", "supplies", "HBM", 40.0, "high", None, None)
    weak = L("b", "x", "y", "supplies", "HBM", 2.0, "low", None, None)
    unknown = L("c", "x", "y", "supplies", "HBM", None, "high", None, None)
    assert tracer.link_strength(strong) > tracer.link_strength(unknown) > tracer.link_strength(weak)
    # more alternative suppliers -> less dependence
    assert tracer.link_strength(strong, alternatives=3) < tracer.link_strength(strong, alternatives=0)
    for link in (strong, weak, unknown):
        assert 0 < tracer.link_strength(link) <= 1


def test_scores_are_0_to_100_and_sorted(g):
    res = tracer.trace(g, ["ras_laffan", "helium"])
    scores = [r["exposure_score"] for r in res]
    assert all(0 <= s <= 100 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_impact_direction_of_each_link_type():
    L = tracer.Link
    assert L("1", "tsmc", "nvidia", "supplies", None, None, "high", None, None).impact_direction() == ("tsmc", "nvidia")
    assert L("2", "ras_laffan", "helium", "produces", None, None, "high", None, None).impact_direction() == ("ras_laffan", "helium")
    assert L("3", "tsmc", "helium", "uses", None, None, "high", None, None).impact_direction() == ("helium", "tsmc")
    assert L("4", "tsmc", "taiwan", "makes_in", None, None, "high", None, None).impact_direction() == ("taiwan", "tsmc")
