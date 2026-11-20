"""Match names found in text to nodes on the map, using each node's aliases.

"HON HAI PRECISION IND CO LTD" -> needs an alias; tickers and names are matched
case-insensitively, ignoring punctuation and company suffixes (Inc., Co., Ltd. ...).
Anything that matches nothing (or more than one node) goes to the review queue.
"""
from __future__ import annotations

import json
import re
import sqlite3

SUFFIXES = r"\b(incorporated|inc|corp|corporation|co|company|ltd|limited|plc|llc|ag|se|sa|spa|s\.p\.a|nv|n\.v|holdings?|group|technology|technologies)\b"


def norm_name(s: str) -> str:
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[.,'’()\"]", " ", s)
    s = re.sub(SUFFIXES, " ", s)
    return re.sub(r"\s+", " ", s).strip()


class NameIndex:
    def __init__(self, conn: sqlite3.Connection):
        self.by_name: dict[str, set[str]] = {}
        self.names: dict[str, str] = {}
        for r in conn.execute("SELECT id, name, aliases, ticker FROM nodes"):
            self.names[r["id"]] = r["name"]
            keys = [r["name"], r["id"].replace("_", " ")] + json.loads(r["aliases"] or "[]")
            if r["ticker"]:
                keys.append(r["ticker"].split(".")[0])
            for k in keys:
                nk = norm_name(k)
                if len(nk) >= 2:
                    self.by_name.setdefault(nk, set()).add(r["id"])

    def match(self, name: str | None) -> str | None:
        """Return a node id if `name` matches exactly one node, else None."""
        if not name:
            return None
        hits = self.by_name.get(norm_name(name), set())
        return next(iter(hits)) if len(hits) == 1 else None

    def find_in_text(self, text: str) -> list[str]:
        """Every node whose name or alias appears in the text (whole words)."""
        t = " " + norm_name(text) + " "
        found = set()
        for key, ids in self.by_name.items():
            if len(key) < 3:
                continue
            if f" {key} " in t:
                found |= ids
        return sorted(found)
