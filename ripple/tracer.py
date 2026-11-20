"""Ripple tracer: path-finding and exposure scoring (plain code, no AI).

How a problem travels along each kind of link:

    supplies   A -> B   trouble at A reaches its customer B
    produces   A -> M   trouble at producer A reaches material/part M
    uses       C -> M   trouble with material M reaches the company C that uses it
    makes_in   C -> P   trouble at place P reaches company C that produces there

So we build an "impact graph" whose arrows point the way trouble flows, then
walk outward from the affected nodes up to 4 steps and collect every path
(e.g. helium -> sk_hynix -> nvidia -> microsoft).

Exposure score (0-100) for a company at the end of paths:
- every link gets a strength between 0 and 1 from
    * confidence  (high 1.0, medium 0.75, low 0.45)
    * share       (disclosed % of revenue/supply; unknown counts as middling)
    * alternatives (how many other sources of the same thing the receiver has)
- a path's strength is the product of its link strengths (longer = weaker)
- a company's exposure combines all its paths:  1 - product(1 - path strength)
- small bonus (location) if the company sits in the same country as the event.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.75, "low": 0.45}
UNKNOWN_SHARE_FACTOR = 0.5
STEP_LIMIT = 4
LOCATION_BONUS = 1.15
MAX_PATHS_PER_SOURCE = 5000


@dataclass
class Link:
    id: str
    from_node: str
    to_node: str
    type: str
    what: str | None
    share: float | None
    confidence: str
    first_seen: str | None
    last_confirmed: str | None
    is_sample: bool = False
    quotes: list[dict] = field(default_factory=list)

    def impact_direction(self) -> tuple[str, str]:
        """(upstream, downstream): the way trouble flows along this link."""
        if self.type in ("supplies", "produces"):
            return self.from_node, self.to_node
        return self.to_node, self.from_node  # uses, makes_in: trouble flows from the thing to the company


def load_links(conn: sqlite3.Connection, before: str | None = None, include_sample: bool = True,
               statuses: tuple[str, ...] = ("approved",)) -> list[Link]:
    sql = f"SELECT * FROM links WHERE status IN ({','.join('?' * len(statuses))})"
    params: list = list(statuses)
    if before:
        sql += " AND first_seen IS NOT NULL AND first_seen < ?"
        params.append(before)
    if not include_sample:
        sql += " AND is_sample = 0"
    links = []
    for r in conn.execute(sql, params):
        quotes = [dict(q) for q in conn.execute(
            """SELECT s.quote, s.quote_verified, s.document_id, d.url, d.doc_type, d.published_at
               FROM link_sources s JOIN documents d ON d.id = s.document_id WHERE s.link_id = ?""", (r["id"],))]
        links.append(Link(r["id"], r["from_node"], r["to_node"], r["type"], r["what"], r["share"],
                          r["confidence"], r["first_seen"], r["last_confirmed"], bool(r["is_sample"]), quotes))
    return links


def load_nodes(conn: sqlite3.Connection) -> dict[str, dict]:
    out = {}
    for r in conn.execute("SELECT * FROM nodes"):
        d = dict(r)
        d["aliases"] = json.loads(d["aliases"] or "[]")
        d["extra"] = json.loads(d["extra"] or "{}")
        out[d["id"]] = d
    return out


def impact_graph(links: list[Link], nodes: dict[str, dict] | None = None) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for nid, n in (nodes or {}).items():
        g.add_node(nid, **{k: n.get(k) for k in ("kind", "name", "layer", "country", "ticker")})
    for link in links:
        up, down = link.impact_direction()
        g.add_edge(up, down, key=link.id, link=link)
    # number of alternative sources for each (receiver, thing) pair
    for _, down, key, data in g.edges(keys=True, data=True):
        link: Link = data["link"]
        thing = (link.what or link.type).lower()
        same = [d["link"] for _, _, d in g.in_edges(down, data=True)
                if (d["link"].what or d["link"].type).lower() == thing]
        data["alternatives"] = max(0, len(same) - 1)
    return g


def build_graph(conn: sqlite3.Connection, before: str | None = None, include_sample: bool = True) -> nx.MultiDiGraph:
    return impact_graph(load_links(conn, before, include_sample), load_nodes(conn))


def link_strength(link: Link, alternatives: int = 0) -> float:
    conf = CONFIDENCE_WEIGHT.get(link.confidence, 0.45)
    if link.share is None:
        share = UNKNOWN_SHARE_FACTOR
    else:
        share = 0.35 + 0.65 * min(max(link.share, 0.0), 50.0) / 50.0
    alt = 1.0 / (1.0 + 0.5 * alternatives)
    return conf * share * alt


def find_paths(g: nx.MultiDiGraph, sources: list[str], max_steps: int = STEP_LIMIT) -> list[list[tuple[str, str, str]]]:
    """Every simple path (as a list of (from, to, link_id) steps) from the sources, up to max_steps links."""
    paths: list[list[tuple[str, str, str]]] = []
    source_set = set(sources)
    for src in sources:
        if src not in g:
            continue
        count = 0
        stack: list[tuple[str, list[tuple[str, str, str]], set[str]]] = [(src, [], {src})]
        while stack:
            node, path, seen = stack.pop()
            if path:
                paths.append(path)
                count += 1
                if count >= MAX_PATHS_PER_SOURCE:
                    break
            if len(path) >= max_steps:
                continue
            for _, nxt, key in g.out_edges(node, keys=True):
                if nxt in seen or nxt in source_set:
                    continue
                stack.append((nxt, path + [(node, nxt, key)], seen | {nxt}))
    return paths


def path_strength(g: nx.MultiDiGraph, path: list[tuple[str, str, str]]) -> float:
    s = 1.0
    for u, v, key in path:
        data = g.edges[u, v, key]
        s *= link_strength(data["link"], data.get("alternatives", 0))
    return s


def path_confidence(g: nx.MultiDiGraph, path: list[tuple[str, str, str]]) -> str:
    """The weakest link decides the path's confidence."""
    order = ["low", "medium", "high"]
    return min((g.edges[u, v, k]["link"].confidence for u, v, k in path), key=order.index)


def trace(g: nx.MultiDiGraph, sources: list[str], max_steps: int = STEP_LIMIT,
          companies_only: bool = True) -> list[dict]:
    """Trace a ripple. Returns one entry per reached node, most exposed first."""
    origin_countries = {g.nodes[s].get("country") for s in sources if s in g and g.nodes[s].get("country")}
    by_node: dict[str, list[tuple[float, list]]] = defaultdict(list)
    for path in find_paths(g, sources, max_steps):
        end = path[-1][1]
        by_node[end].append((path_strength(g, path), path))
    results = []
    for nid, scored in by_node.items():
        attrs = g.nodes[nid]
        if companies_only and attrs.get("kind") != "company":
            continue
        combined = 1.0 - math.prod(1.0 - s for s, _ in scored)
        if attrs.get("country") in origin_countries:
            combined = min(1.0, combined * LOCATION_BONUS)
        scored.sort(key=lambda x: (-x[0], len(x[1])))
        best_s, best = scored[0]
        results.append({
            "node_id": nid,
            "name": attrs.get("name"),
            "layer": attrs.get("layer"),
            "exposure_score": round(100 * combined, 1),
            "path": [best[0][0]] + [v for _, v, _ in best],
            "path_links": [k for _, _, k in best],
            "steps": len(best),
            "path_count": len(scored),
            "path_confidence": path_confidence(g, best),
            "all_paths": [{"path": [p[0][0]] + [v for _, v, _ in p], "links": [k for _, _, k in p],
                           "strength": round(s, 4)} for s, p in scored[:10]],
        })
    results.sort(key=lambda r: (-r["exposure_score"], r["steps"], r["node_id"]))
    return results


def possible_winners(g: nx.MultiDiGraph, sources: list[str], reached: set[str]) -> list[dict]:
    """Companies that make the same thing as a hit node but are NOT on any path.

    Example: helium is hit; Linde and Air Products also produce helium from other
    sources, so they might benefit. Direction is left 'unclear' for the explainer to judge.
    """
    hit = set(sources) | reached
    out = {}
    for thing in hit:
        if thing not in g or g.nodes[thing].get("kind") not in ("material", "part"):
            continue
        for producer, _, data in g.in_edges(thing, data=True):
            link: Link = data["link"]
            if link.type != "produces" or producer in hit or g.nodes[producer].get("kind") != "company":
                continue
            out[producer] = {"node_id": producer, "name": g.nodes[producer].get("name"),
                             "reason": f"also produces {g.nodes[thing].get('name')}", "link_id": link.id}
    return list(out.values())


def link_index(g: nx.MultiDiGraph) -> dict[str, Link]:
    return {k: d["link"] for _, _, k, d in g.edges(keys=True, data=True)}
