# Decisions and assumptions

Choices I made while you were away, so you can check or reverse them.

## General
1. **Claude Opus instead of Fable.** Everywhere the plan says Claude Fable (the ripple explainer, job 3), the code uses `claude-opus-5-5`, as you asked. Jobs 1 and 2 use `claude-haiku-5-5`, as the plan says. All three model names can be changed in `.env` without touching code.
2. **Python + SQLite**, as the plan's "Suggested stack" says. One file: `data/ripple.db`. It is *not* uploaded to GitHub (it can always be rebuilt with `python -m ripple init`, and downloaded filings make it large).
3. **Settings live in environment variables / a local `.env` file** (template: `.env.example`). `.env` is in `.gitignore`, so keys never get uploaded.

## Database
4. All seven tables from the plan's "Data model" exist. I added two helper tables: `document_sections` (the cut-out Item 1 / Item 1A / customer notes, so the AI reads only those) and `ai_usage` (tokens per AI call, because the plan says to log tokens per job).
5. A few extra columns: `links.is_sample` and `events.is_sample` (to clearly mark hand-made SAMPLE data), `documents.external_id` (e.g. the SEC accession number, so the same filing is never stored twice), `nodes.extra` (SEC company number, Korean/Japanese stock codes), `impacts.path_links`, `how_much`, `timing`, `what_would_change_this` (fields the ripple explainer returns), and `events.summary` / `biggest_unknowns`.
6. **"The database refuses a link without a source"** is enforced by database triggers: a link can't be *inserted* as approved, can't be *changed* to approved unless it has a source whose quote was verified word for word, and its last verified source can't be deleted.
7. `followups.checked_at` stores `1d`, `1w` or `1m` (which check it is), since the plan describes it as "1 day, 1 week or 1 month after the event".

## Seed data
8. 38 companies + 13 places/materials/parts = **51 nodes** (plan: "about 50"). On top of the 10 listed in the plan I added LNG and CoWoS packaging (both appear in the plan's expected helium paths) and Qatar.
9. Layer names are stored short: `memory`, `packaging` (= packaging & chipmaking), `power` (= power & cooling), `materials`, `buyers`.
10. Linde's home country is set to IE (Linde plc is incorporated in Ireland) even though it trades in the US.
11. Unimicron files with Taiwan's MOPS (no API key needed but not built yet); Besi, Siemens Energy, Schneider and Prysmian are marked `ir_pdf` (the plan's manual PDF folder); QatarEnergy is state-owned and files nothing.

## SEC collector and section cutter (Phase 1)
12. The SEC collector stays at **8 requests per second** (SEC's limit is 10) and retries politely on "too many requests" errors.
13. For **foreign filers** (TSMC, ASE) there are no 10-Qs; they file 20-F (annual) and 6-K (current/quarterly). The collector treats 6-K like 8-K. 
14. "8-K from the last 4 quarters" = 8-Ks filed in the last 12 months, at most 8 per company by default (some companies file dozens; change with `--max-8k`). Only the main 8-K document is stored, not its attachments (press releases are exhibits) — a possible later improvement.
15. Raw downloaded HTML is also kept, gzipped, in `data/raw/` (not uploaded to GitHub) so every claim can be traced to exactly what was downloaded.
16. For a 20-F, "Item 1" is taken from **Item 4 (Information on the Company)** and "Item 1A" from **Item 3.D (Risk Factors)** — the 20-F equivalents.
17. Short documents (8-K, 6-K under 60,000 characters) are stored whole as a `full` section. 10-Qs get their Part II Item 1A (risk factors) plus customer-concentration sentences.
18. "Customer-concentration notes" are found by sentence search across the whole filing: a sentence is kept if it mentions a customer/supplier/vendor/foundry/sole source AND a share, "accounted for", "depend", "limited number of", etc. This catches the notes to the financial statements wherever they are. It lets some noise through (that's cheaper than missing a real link).

## Ripple tracer (Phase 3 code)
19. **Which way trouble flows:** `supplies` and `produces` pass trouble forward (supplier -> customer, producer -> material); `uses` and `makes_in` pass it backward (material -> company that uses it, place -> company that makes things there).
20. **Exposure score (0–100):** each link gets a strength = confidence weight (high 1.0 / medium 0.75 / low 0.45) × share factor (disclosed % scaled 0.35–1.0; unknown = 0.5) × alternatives factor (1 / (1 + 0.5 × number of other sources of the same thing)). A path's strength is the product of its links. A company's score combines all its paths (1 − product of (1 − path strength)), with a 15% bump if it is in the same country as the event. These numbers are starting points to tune once real events can be compared with what happened.
21. Paths can't loop back through a node or through another affected node. At most 5,000 paths per starting node (a safety cap; the current map is far smaller).
22. "Who might benefit" is found by code as a *candidate* list only: companies that also produce a hit material/part but are not on any path (e.g. Linde and Air Products for helium). The AI explainer decides the actual direction.
23. **SAMPLE links:** 51 hand-made links in `data/sample/sample_links.json`, all stored with `is_sample=1`, quotes start with "SAMPLE:", shares are made up. They're backed by one SAMPLE document so the "approved needs a verified source" rule still holds. One sample link (Micron -> AMD) is dated after March 2026 on purpose to test the "only links from before the event" filter. Remove them with `python -m ripple load-sample --remove`.
