# AI_TASKS.md — instructions for the daily Ripple AI session

You are the scheduled Claude Code session that does Ripple's AI work, once a day at 3am Hong Kong time.
Code has already prepared a small work queue. Your job is to read it, answer it carefully following the
rules below, save your answers as JSON, and run the import command. Code then checks every answer.

**Keep it small.** Do only what is in the queue. Don't browse the web, don't read files other than the ones
named here, don't change any code, don't approve links, and don't open pull requests.

---

## Step 1 — Get the latest version and check if there is work

```bash
git checkout main && git pull
```

```bash
pip install -q -r requirements.txt
```

```bash
python -m ripple ai-status
```

- If the result says `"status": "empty"` or `"imported"` (exit code 3): **stop now.** Reply "Ripple: no AI work today." and end the session. Do nothing else.
- If it says `"status": "ready"`: continue.

## Step 2 — Read the queue

Open `ai_work/queue.json`. It has three lists:

| List | Job | Up to |
|---|---|---|
| `job1_link_extractor` | Read a filing excerpt, list supply chain relationships | ~15 excerpts |
| `job2_event_checker` | Decide if a news item / 8-K is a real supply chain event | 30 items |
| `job3_ripple_explainer` | Explain an event's ripple through the map | 3 events |

Each task has a `task_id`. Answer every task, in any order. Use **only** the text inside the task.

## Step 3 — Do the jobs

### Job 1 — Link extractor (for each task in `job1_link_extractor`)

The filing company is `company_name`; the text to read is `text`.

List every relationship the text states between the filing company and another organization, place, or material. Use only these types:
- `supplies`: one company sells goods or services to another
- `makes_in`: the company produces in a named country, region or site
- `uses`: the company depends on a named material or part
- `produces`: the company makes a named material or part

Rules:
- Only include relationships the text actually states. **No outside knowledge.**
- `quote` must be **copied character for character** from `text`: one or two whole sentences. Don't fix typos, shorten, paraphrase, or join pieces from different places. Code checks this word for word and throws out anything that doesn't match.
- `direction`: for `supplies`, `filer_to_other` means the filer sells to the other party; `other_to_filer` means the other party sells to the filer. For the other types use `filer_to_other`.
- `other_party`: the name exactly as written (e.g. "Taiwan Semiconductor Manufacturing Company Limited"). If unnamed ("a major customer", "Customer A"), use `null` and still include it.
- `share`: a number if the text gives one ("accounted for 18% of revenue" → 18), otherwise `null`.
- `what`: a few words for what flows (e.g. "HBM", "wafer foundry services", "helium"), or `null`.
- Generic statements without a named counterparty, place, or material ("we rely on suppliers") are not relationships — skip them unless they give a share for an unnamed party.
- Nothing found → `"links": []`.

### Job 2 — Event checker (for each task in `job2_event_checker`)

Read `text`. `matched_nodes` lists the map nodes it mentions (id → name).

- `is_event`: `true` only if something actually changed supply, demand, capacity, prices or rules for these nodes. Opinion pieces, stock commentary, earnings previews, price targets, analyst ratings, routine corporate filings (director changes, bond issues, dividends) are **not** events.
- `event_type`: one of `disruption`, `shortage`, `new_contract`, `policy`, `price_spike`, `capacity_change` (or `null` if not an event).
- `severity`: 1 (minor, local, short) to 5 (major, global, months), or `null` if not an event.
- `affected_nodes`: ids from `matched_nodes` that are directly hit. **Only ids from that list.**
- `one_line`: one plain sentence describing it.

### Job 3 — Ripple explainer (for each task in `job3_ripple_explainer`)

Code has already traced every path from the event through the map (`companies_reached`, with exposure scores and the source quote for every link). Judge and explain, using only that evidence.

For each company in `companies_reached` (use its `company_id` exactly):
- `direction`: `hurt`, `helped` (e.g. a competitor or alternative supplier — see `possible_winner`), or `unclear`
- `how_much`: `low`, `medium` or `high`
- `why`: one or two sentences, including what your confidence rests on
- `timing`: when the effect would show up (weeks, a quarter, a year)
- `confidence`: `high`, `medium` or `low`
- `uses_general_knowledge`: `true` if you relied on anything not in the given links and quotes (then confidence must be `low`)
- `what_would_change_this`: one thing that would make this call wrong

Then:
- `summary`: three to five plain sentences a non-expert can follow
- `biggest_unknowns`: the gaps in the map that matter most for this event

Rules: **Only companies listed in `companies_reached`** (code drops any other). No buy/sell advice — describe exposure, not trades. If a path looks weak (low confidence, tiny share), say it may not matter.

## Step 4 — Save your answers

Write **`ai_work/results.json`** in exactly this shape (copy `queue_id` from the queue):

```json
{
  "queue_id": "q20261121-180000",
  "answered_by": "claude-code-session",
  "job1": [
    {"task_id": "s123", "links": [
      {"type": "supplies", "direction": "filer_to_other", "other_party": "NVIDIA Corporation",
       "what": "HBM", "share": null, "quote": "exact sentence from the text"}
    ]}
  ],
  "job2": [
    {"task_id": "doc_000456", "is_event": false, "event_type": null, "severity": null,
     "affected_nodes": [], "one_line": "Analyst raises price target on Micron."}
  ],
  "job3": [
    {"task_id": "evt_0007", "impacts": [
      {"company": "nvidia", "direction": "hurt", "how_much": "medium", "why": "...", "timing": "a quarter",
       "confidence": "medium", "uses_general_knowledge": false, "what_would_change_this": "..."}
    ], "summary": "...", "biggest_unknowns": ["..."]}
  ]
}
```

Every task in the queue should have one entry. Empty jobs are empty lists.

## Step 5 — Import (code checks everything)

```bash
python -m ripple ai-import
```

- This runs the checkers: quotes must appear word for word, company names must match the map, no invented companies. Rejected items are fine — that's the checker doing its job. **Don't** try to "fix" rejections by changing quotes.
- If it fails because the JSON is malformed or a `task_id` is wrong, fix the **format only** and run it again.
- New links go into the review queue as `pending_review`. **Never approve links** — a person does that.

## Step 6 — Save and push

```bash
git add data/state ai_work site/data
```

```bash
git commit -m "Daily AI run: <queue_id from the queue>"
```

```bash
git push origin main
```

If pushing to `main` is refused, push to a branch called `ai-daily` instead and say so in your final reply. Then end with a one-paragraph summary: how many links were found / rejected, how many events, which events were explained.
