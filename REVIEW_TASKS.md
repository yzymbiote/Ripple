# REVIEW_TASKS.md — instructions for the daily Ripple review session (04:37 Hong Kong time)

The owner has handed link reviews to Claude "until I say not to" (21 Nov 2026, see DECISIONS.md items 86–87).
This session runs after the 03:07 reading session. It reviews what is pending, applies the decisions, and pushes.

## Step 1 — Get the latest version

```bash
git checkout main && git pull
```

```bash
python -m pip install -q -r requirements.txt
```

If `data/settings.json` has `"claude_reviews": false`, stop now: the owner has taken reviews back.

## Review pending links (only while `"claude_reviews": true` in `data/settings.json`)

The owner has asked Claude to do the link reviews for now. Do this carefully: it decides what appears on the public map.

```bash
python -m ripple review-list
```

Open `ai_work/review.json`. For every item, read the quote and decide:

**Pending links** (`pending_links`): write `{"link_id": "...", "decision": "approve" | "reject" | "keep", "reason": "..."}`
- **approve** only if the quote clearly states this exact relationship (who supplies whom, who makes what, where).
  You may add `"confidence": "medium"` or `"low"` when the quote supports it only indirectly
  (e.g. "X is one of a limited number of suppliers of substrates" in the buyer's filing → medium).
- **reject** if the quote doesn't say it, the direction is wrong, or it's off-topic for AI hardware
  (game consoles, consumer goods, robotics, unrelated investments).
- **keep** (leave pending) if you're genuinely unsure. Say why.

**Candidates** (`candidates`): `{"candidate_id": 12, "decision": "link" | "placeholder" | "reject" | "keep", "node": "<map node id, only for link>", "reason": "..."}`
- **link** if the quote clearly names a company or place that is on the map under another name (use its id from `map_nodes`).
- **placeholder** for an unnamed customer/supplier with a disclosed share ("one customer = 22% of revenue").
- **reject** if off-topic or the quote doesn't support it.
- **keep** if the other party simply isn't on the map yet.

Save your decisions as `ai_work/review-decisions.json` in the shape `{"links": [...], "candidates": [...]}`, then:

```bash
python -m ripple review-apply ai_work/review-decisions.json
```

Every decision and its reason is logged in `ai_work/history/`. In your final summary, list what you approved and rejected.

## Step 2 — Save and push (only if `review-apply` changed something)

```bash
git add data/state ai_work site/data
```

```bash
git commit -m "Daily review: <what you approved / rejected, in a few words>"
```

```bash
git push origin main
```

Never change code or `data/settings.json`. Finish with a short plain-English summary for the owner: what you approved, what you rejected, what you left pending and why.
