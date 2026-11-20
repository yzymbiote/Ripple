# Ripple — handover notes

## Summary of this session

I finished all six tasks on your list. Everything is committed and pushed to GitHub on branch `claude/awesome-maxwell-57hsme`.

1. **Phase 0 — set-up.** Project folders, a settings file for keys (`.env.example`), and the SQLite database with all seven tables from the plan. Two rules from the plan are built into the database itself: a link can't be approved without a source, and that source's quote must have been verified word for word. Seed data is 51 nodes: all 38 companies, plus 13 places, materials and parts (helium, HBM, ABF film, transformers, copper, bromine, LNG, CoWoS, Ras Laffan, Qatar, Korea, Taiwan, Japan).
2. **Phase 1 — SEC collector and section cutter.** Downloads 10-K/20-F, 10-Q and 8-K/6-K filings. It reads the contact User-Agent from `SEC_USER_AGENT` and stays under SEC's speed limit (8 requests a second). I checked all 23 SEC company numbers against SEC's own list, and all match. I ran it on Micron, Amkor, TSMC, Vertiv and Nvidia: 36 filings. The section cutter pulls out Item 1, Item 1A and the customer-concentration sentences (it uses the matching parts of a 20-F, Item 4 and Item 3.D).
3. **Ripple tracer.** Finds every path up to 4 steps from an event and gives each company an exposure score from 0 to 100. The score uses confidence, disclosed share, alternative suppliers and location. It also lists possible winners, such as Linde and Air Products when helium is hit. I tested it with 56 hand-made SAMPLE links, all clearly marked. On the helium test it reaches SK hynix, Samsung and TSMC in one step, and Nvidia, AMD and the cloud companies by step 3. It also respects the "only links from before the event" rule.
4. **Website shell.** Three pages, built in the plan's dark "mission control meets magazine" style, with a light mode too:
   - **Home page:** live ticker strip, softly pulsing map, event cards with a small ripple.
   - **Event page:** headline, then the signature ripple animation. Rings spread, light travels along each link at 0.4 seconds per step, and companies glow red, green or amber. Then the ranked impacts, explanation, unknowns, what happened next, and sources.
   - **Company page:** suppliers, customers, places and materials, each with its quote, confidence and date last confirmed.

   It works on phones, has the "not investment advice" footer on every page, and shows dashed lines for low-confidence links. It reads only one data file, which currently holds SAMPLE data and is labelled as such everywhere.
5. **The three AI jobs.** Link extractor (Haiku), event checker (Haiku) and ripple explainer (**Claude Opus 5.5**, instead of Fable as you asked). Each has its prompt and a fixed reply format, and code checks every answer:
   - quotes must appear word for word in the filing;
   - companies must match the map;
   - the explainer can't invent companies, and anything it bases on general knowledge is marked low confidence.

   The jobs are **switched off** until you add a key. You can already see exactly what would be sent with `--dry-run`.
6. **OpenDART (Korea) and EDINET (Japan) collectors.** Written and **switched off** until you add keys. Korean and Japanese filings are kept in their original language, and the section cutter understands their headings.

There are 27 automated tests, and all pass. Every assumption I made is listed in **DECISIONS.md** (46 items). Read that first if something looks odd.

---

## How to look at it right now (no set-up needed)

Open **`site/index.html`** in your browser (double-click it). Click any event card to see the ripple animation. Click a company name to see its page. The **Light** button at the top right switches to light mode.

Everything you see there is **SAMPLE data** I made up to test the design. It is labelled SAMPLE on every page.

---

## How to run it

You need Python 3.10 or newer. Open a terminal in the project folder and install the libraries once:

```bash
pip install -r requirements.txt
```

Create the database and load the 51 seed nodes:

```bash
python -m ripple init
```

See what's in the database:

```bash
python -m ripple status
```

### SEC filings
This needs `SEC_USER_AGENT` set (see "What you need to do" below). Download filings for a few companies:

```bash
python -m ripple sec-collect --companies micron,amkor
```

Leave out `--companies` to fetch all 23 SEC filers (takes a few minutes). Then cut out the useful parts:

```bash
python -m ripple cut-sections
```

### The ripple tracer (with SAMPLE links)
Load the hand-made sample links and events:

```bash
python -m ripple load-sample
```

Trace the helium shock using only links known before March 2026:

```bash
python -m ripple trace ras_laffan,helium --before 2026-03-01
```

Remove all sample data once you have real links:

```bash
python -m ripple load-sample --remove
```

### The website's data file
Rewrite `site/data/data.js` from the database:

```bash
python -m ripple export-site
```

Once you have real data, leave the samples out:

```bash
python -m ripple export-site --real-only
```

### The AI jobs (switched off until you add a key)
See exactly what would be sent to Claude, without sending anything:

```bash
python -m ripple ai extract-links --dry-run --limit 1
```

```bash
python -m ripple ai explain-ripple --dry-run --event evt_sample_0001
```

After adding your key, run them for real by dropping `--dry-run`. The other jobs are `check-events`, and `extract-links-batch` for the cheaper bulk run.

### Korean and Japanese filings (switched off until you add keys)

```bash
python -m ripple collect-foreign opendart
```

```bash
python -m ripple collect-foreign edinet
```

### Automated tests

```bash
python -m pytest
```

---

## What you need to do yourself

1. **Make a `.env` file.** Copy `.env.example` to a new file called `.env` in the same folder and fill it in. It is never uploaded to GitHub.
   - `SEC_USER_AGENT`: your contact line for SEC, e.g. `Ripple research you@example.com`. It was already set in this cloud session, but your own computer needs it too.
2. **Claude API key** (needed for the AI jobs):
   - Create a key at console.anthropic.com.
   - **Set a monthly spending limit there first.** The plan asks for this, and it protects you from a bug running up a bill.
   - Put the key in `.env` as `ANTHROPIC_API_KEY`, and set `RIPPLE_AI_ENABLED=1`.
   - Check current prices on docs.claude.com before the first big run of job 1 over every filing.
3. **OpenDART key** (Korea, free): sign up at opendart.fss.or.kr, put the key in `OPENDART_API_KEY`, and set `RIPPLE_OPENDART_ENABLED=1`.
4. **EDINET key** (Japan, free): sign up at api.edinet-fsa.go.jp, put the key in `EDINET_API_KEY`, and set `RIPPLE_EDINET_ENABLED=1`.
5. **Merge the work.** When you're happy, open a pull request on GitHub from branch `claude/awesome-maxwell-57hsme` into your main branch.
6. **Look at the design.** The plan says to agree on the home and event page design before building further. Open the pages and tell the next session what to change.

I could not test the real API calls or the Korean and Japanese collectors against the live services, because I had no keys. They are tested with fake replies only. Expect small fixes the first time each one runs for real.

---

## What's next (from the build plan)

- **Rest of Phase 1:** Taiwan monthly revenue collector (MOPS: TSMC, ASE, Unimicron), and a manual PDF folder for the European annual reports (Besi, Siemens Energy, Schneider, Prysmian). Then run the SEC collector on all 23 filers.
- **Phase 2:** with your Claude key, run the link extractor over every stored section. Then build a simple private **review-queue page** to approve or reject links: candidates are already stored in `link_candidates` and new links wait as `pending_review`. The goal is at least 150 approved links.
- **Phase 3:** run the real helium test. Enter the Ras Laffan event by hand, then run `python -m ripple ai explain-ripple --event <id>`; the tracer only uses links first seen before March 2026. Compare the result with what actually happened, and tune the scoring numbers (DECISIONS.md, item 20).
- **Phase 4:** news/GDELT and SEC 8-K feed collectors, ship tracking (aisstream), and scheduled runs on GitHub Actions.
- **Phase 5:** map explorer, weekly write-up, follow-up log of price moves, and hosting the `site/` folder on GitHub Pages.

## Where things are

| Folder / file | What it is |
|---|---|
| `ripple/` | All the Python code (`python -m ripple --help` lists every command) |
| `ripple/collectors/` | SEC, OpenDART, EDINET collectors |
| `ripple/sections.py` | Section cutter |
| `ripple/tracer.py` | Path finding and exposure scoring |
| `ripple/events.py` | Turns an event into stored impacts (shared by the sample loader and AI job 3) |
| `ripple/ai/` | The three AI jobs, prompts, and the switched-off Claude client |
| `data/seed/nodes.json` | The 38 companies + places and materials |
| `data/sample/` | Hand-made SAMPLE links and events (test data only) |
| `site/` | The website; `site/data/data.js` is the only data it reads |
| `tests/` | Automated tests |
| `DECISIONS.md` | Every assumption I made, numbered |
