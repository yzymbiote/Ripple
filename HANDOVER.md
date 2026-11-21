# Ripple — handover notes

## Summary of the latest session (zero-cost AI setup)

All 9 steps you asked for are done, committed and pushed on branch `claude/awesome-maxwell-57hsme`, and there's a pull request into `main` (https://github.com/yzymbiote/Ripple/pull/1).

**One important correction first.** The website was **not** actually in GitHub before today. The starting `.gitignore` (GitHub's standard Python template) silently ignores any folder called `site/`, so the website files were never committed, although my last summary said they were pushed. I've removed that line, and the whole website is in GitHub now. The details are in DECISIONS.md, item 75.

What's new:

1. **All 23 SEC companies collected.** 289 filings (10-K/20-F, 10-Qs, 8-K/6-Ks), cut into 407 sections.
2. **Zero-cost AI setup.** No API key, no payment.
   - Every day, code prepares a **small work queue** (`ai_work/queue.json`):
     - up to 15 filing excerpts, trimmed to the relevant paragraphs;
     - up to 30 news items or 8-Ks that mention the map, pre-filtered by code;
     - up to 3 events to explain, most severe first.
   - A **scheduled Claude Code session on your normal plan** (Sonnet, 3am HK time) follows **`AI_TASKS.md`** and writes its answers to `ai_work/results.json`.
   - `python -m ripple ai-import` then runs every answer through the checkers: quotes must appear word for word, names must match the map, no invented companies.
   - If the queue is empty, the session stops straight away.
   - A free-model backup (OpenRouter or Gemini) exists but is **off**. The paid API route is also **off**.
   - The map's state is saved as small text files in `data/state/`, so every fresh machine can rebuild it.
3. **First job-1 run done by me, following AI_TASKS.md.**
   - I read 29 filing excerpts and checked 8 news/8-K items. None of the news items was a real supply event.
   - **15 real links are waiting in the review queue** as pending. For example: TSMC supplies Broadcom (about 95% of its contract manufacturers' wafers); Unimicron supplies ASE (substrates); Quanta uses copper and transformers; Air Products uses helium; Micron produces HBM; TSMC and Micron make chips in Taiwan.
   - **30 more candidates need a person.** Most are unnamed customers with a share ("one direct customer represented 22% of revenue"), or companies not on the map yet (Hon Hai/Foxconn, Wistron, Sony).
   - Every quote passed the word-for-word check. **Nothing was approved.**
4. **Review queue page.** Run `python -m ripple review` on your computer. A private page opens where you approve, reject or edit links, or match a candidate to a company on the map. Every click saves.
5. **GDELT news collector.** Free, no key. It searches news about everything on the map in 4 grouped searches, respecting GDELT's speed limit, and merges near-identical headlines.
6. **New pages, same design:**
   - places and materials pages (who produces it, who uses it);
   - an interactive **map explorer** (`map.html`);
   - a **Monday brief** (`brief.html`) that drafts itself from the data, with buttons to copy it as a newsletter, copy it as a social thread, or print it.
7. **GitHub Actions "Daily collect"** runs at 21:23 HK time, before the 3am session:
   - it collects filings and news, builds the queue, updates the site data and commits it;
   - if a collector fails, GitHub emails you instead of failing silently;
   - it costs nothing.
8. **GitHub Pages workflow.** The site gets a free public address after you merge and switch on Pages: https://yzymbiote.github.io/Ripple/. Sample data stays clearly labelled SAMPLE until real approved links and events exist, then disappears by itself.
9. **Pull request** opened from the branch into `main` (link below).

There are 37 automated tests, and all pass. Every assumption is numbered in **DECISIONS.md** (items 47–75 are new). Pull request: https://github.com/yzymbiote/Ripple/pull/1

---

## Working agreement (for any Claude session)
- **Daily review:** the owner says "pre-review today's links" → Claude lists approve/reject with reasons → owner says "ok" → Claude applies it and **pushes straight to `main`** (no pull request).
- **Small fixes:** Claude pushes straight to `main` and says what changed. Bigger new features: pull request first.
- Claude never approves links without the owner's ok.

## Part 1 — What you need to do (in this order)

### Step 1. Merge the pull request
On GitHub, open the pull request "Ripple: zero-cost daily AI setup, review queue, news, new pages" and click **Merge pull request**. Everything below needs the code on `main`.

### Step 2. Add your SEC contact line as a GitHub secret (free, one time)
The daily GitHub run needs it to download SEC filings.
1. On GitHub, open the repository, then **Settings**.
2. In the left menu: **Secrets and variables → Actions**.
3. Click **New repository secret**.
4. Name: `SEC_USER_AGENT`. Value: your contact line, e.g. `Ripple research your-email@example.com`.
5. Click **Add secret**.

### Step 3. Switch on GitHub Pages (free public website)
1. Repository **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**.
3. Go to the **Actions** tab, click **Publish site** on the left, then **Run workflow**. After a minute or two the site is live at **https://yzymbiote.github.io/Ripple/**.

(If the repository is private, GitHub Pages needs a paid GitHub plan. In that case leave it off; nothing else depends on it.)

### Step 4. Allow the daily jobs to push to `main`
Both the GitHub Actions run and the 3am session save their results by pushing to `main`.
- Check **Settings → Rules / Branches**. If `main` has a rule that blocks direct pushes, the daily runs can't save. Either leave `main` unprotected, or add an exception for GitHub Actions.
- Also check **Settings → Actions → General → Workflow permissions** and select **Read and write permissions**.

### Step 5. Set up the 3am scheduled Claude Code session
This is the step that does the AI work on your normal Claude plan. It's based on the current docs (code.claude.com/docs/en/routines). The site may say "routines" or "scheduled tasks"; they're the same thing.

1. Go to **https://claude.ai/code/routines**.
2. Click **New task** (on some accounts it says **New routine**).
3. **Name:** `Ripple daily AI`
4. **Prompt / Instructions:** copy and paste this whole box:

   ```
   You are Ripple's daily AI session. Work in the GitHub repository yzymbiote/Ripple on the main branch.
   Open AI_TASKS.md and follow it exactly, step by step.
   If `python -m ripple ai-status` says there is no work (status "empty" or "imported"), stop immediately and do nothing else.
   Keep it small: do only the tasks in ai_work/queue.json, using only the text given in each task.
   You have my permission to commit and push to main, but only the folders data/state, ai_work and site/data.
   Never approve links, never change code, never open pull requests.
   Finish with a short summary of what you found.
   ```

5. **Trigger:** choose **Schedule**, then **Daily**, and set the time to **3:07 AM**.
   - The docs say preset times use **your local time zone**. If your computer is set to Hong Kong time, 3:07 is right. A few minutes past the hour avoids the busy top of the hour.
   - If your computer is **not** on Hong Kong time, choose **Custom** instead and enter exactly: `CRON_TZ=Asia/Hong_Kong 7 3 * * *`
6. Open **Advanced settings → General**:
   - **Repository:** choose `yzymbiote/Ripple`.
   - **Cloud environment:** the **Default** environment is fine. It needs no keys, and its standard "Limited" network access already allows installing Python packages and pushing to GitHub.
7. **Model:** in the model selector next to the prompt box, choose **Sonnet**. If an **Effort** option is shown, pick a low or medium setting; the work is simple.
8. Click **Create**.
9. To test it now instead of waiting for 3am, open the task and click **Run now**. Watch it under **History**.

To **pause** it later, use the on/off switch at the top of the task's page. To change or remove it, open the menu next to its name and choose **Edit** or **Delete**.

Notes:
- Each run counts toward your normal Claude usage. With the limits in `ripple/queue.py` a run reads roughly 20,000 tokens of filings plus up to 30 short news items, and it stops at once if there's nothing to do.
- If GitHub isn't connected when a run is due, the run is skipped. After 72 hours the task switches itself off.

### Step 6. Review the 15 pending links (and the 30 candidates)
Nothing reaches the public map until you approve it.

**On your own computer** (needs Python 3.10+ and a copy of the repository; GitHub Desktop is the easiest way to get one):

```bash
pip install -r requirements.txt
```

```bash
python -m ripple review
```

Your browser opens the review page. For each link, read the quote, then click **Approve**, **Reject**, or **Edit**. In **Need a name**, match a candidate to a company on the map, or reject it. When you're done, press Ctrl+C in the terminal, then commit and push the `data/state` folder (in GitHub Desktop: **Commit to main**, then **Push origin**).

**Or without installing anything:** open a session at claude.ai/code on this repository and ask, for example, "Show me the pending Ripple links with their quotes", then "Approve link_000002 and link_000007, reject link_000004, then commit and push data/state". The session can run the same review functions.

---

## Part 2 — How the daily cycle works

| When (HK time) | What | Where |
|---|---|---|
| 21:23 (day before) | Collect SEC filings and GDELT news, cut sections, pre-filter, build `ai_work/queue.json`, update site data, commit | GitHub Actions (free) |
| 01:30 or so | Publish the site | GitHub Actions (free) |
| 03:07 | Read the queue, do jobs 1–3, write `ai_work/results.json`, run `ai-import`, commit and push | Your scheduled Claude Code session (your plan) |
| Any time | Approve or reject links | You, on the review page |

Job 3 (explaining an event's ripple) only has something to work with once you have **approved** links, because the tracer only follows approved links.

---

## Part 3 — Commands (for reference)

Everything is run as `python -m ripple <command>`. The main ones:

| Command | What it does |
|---|---|
| `daily-collect` | Everything GitHub Actions runs each day |
| `ai-prepare` | Build today's AI work queue |
| `ai-status` | Is there AI work? (exit code 3 = no) |
| `ai-import` | Check and import `ai_work/results.json` |
| `ai-backup` | OPTIONAL: answer the queue with a free model (off by default; see below) |
| `review` | Open the private review page |
| `state-save` / `state-load` | Save the map to `data/state/` or rebuild the database from it |
| `sec-collect`, `cut-sections`, `collect-foreign opendart/edinet` | Individual collectors |
| `trace ras_laffan,helium --before 2026-03-01` | Trace a ripple over approved links |
| `export-site` | Rewrite the website's data file |
| `load-sample` | Load the hand-made SAMPLE links into the database (testing only; `--remove` takes them out) |

Run the tests:

```bash
python -m pytest
```

Look at the site without hosting: double-click `site/index.html`.

### Optional: free-model backup (off)
Only if the Claude session is ever unavailable. Put these lines in a `.env` file:
- `RIPPLE_BACKUP_AI=openrouter` or `RIPPLE_BACKUP_AI=gemini`
- `OPENROUTER_API_KEY=...` or `GEMINI_API_KEY=...` (both free sign-ups)

Then run `python -m ripple ai-backup`, then `python -m ripple ai-import`.

Free models are weaker, but the same checkers throw out bad answers. Free tiers may keep what you send; everything sent is public filings and headlines.

### Paid API route (off)
Still there (`python -m ripple ai ...`). It needs `ANTHROPIC_API_KEY` and `RIPPLE_AI_ENABLED=1`. You said you won't use it, so leave it off.

---

## Part 4 — What's still blocked or not done

- **GDELT throttling.** GDELT limits automated use, and from this server it sometimes refused one of the four searches even at 10 seconds apart. The collector keeps whatever it got and tries again the next day. If it gets worse, the plan's Google News RSS feeds are a free fallback.
- **OpenDART (Korea) and EDINET (Japan)** still need free keys. If you get them, add them as GitHub secrets `OPENDART_API_KEY` and `EDINET_API_KEY`, and the daily run switches them on automatically.
- **Taiwan monthly revenue (MOPS)**, and the PDF folder for the European annual reports, are not built yet.
- **New companies** can't be added from the review page yet. Hon Hai/Foxconn, Wistron, Sony and others are waiting as candidates. Add them to `data/seed/nodes.json` (Phase 6 "next ring"), then match the candidates on the review page.
- **Price follow-ups** (1 day / 1 week / 1 month) need a free stock-price source. Not built yet, so "what happened next" and the brief's "how calls turned out" only show SAMPLE numbers.
- **Backlog.** About 200 filing sections are still unread. At about 15 a day, the daily session works through them, most valuable first, in roughly two weeks.

## Part 5 — Where things are

| Folder / file | What it is |
|---|---|
| `AI_TASKS.md` | Instructions the 3am session follows |
| `ai_work/` | Today's queue, the session's results, and a history of reports |
| `data/state/` | The saved map: links, sources, decisions, events (committed every day) |
| `data/seed/nodes.json` | The 38 companies + places and materials |
| `data/sample/` | Hand-made SAMPLE links and events (shown on the site only until real data exists) |
| `ripple/` | All the Python code |
| `ripple/queue.py` | Builds and imports the daily AI queue (daily limits are at the top) |
| `review/` | The private review page (not published) |
| `site/` | The public website (published by GitHub Pages) |
| `.github/workflows/` | Daily collect, publish site, tests |
| `DECISIONS.md` | Every assumption, numbered |

---

## Earlier session (for the record)

Phase 0 (database and 51 seed nodes), the SEC collector and section cutter, the ripple tracer with tests, the website design, the three AI jobs with checkers, and the OpenDART/EDINET collectors (off until keys are added). See DECISIONS.md items 1–46.
