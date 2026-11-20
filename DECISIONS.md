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
