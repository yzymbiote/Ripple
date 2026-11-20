# Ripple — handover notes

(Work in progress — this file is updated after each step.)

## Done so far
- **Phase 0:** project folders, database with every table, 51 seed nodes (all 38 companies + places and materials).
- **Phase 1 (SEC part):** SEC EDGAR collector + section cutter. Tested on Micron, Amkor, TSMC, Vertiv and Nvidia: 36 filings downloaded, and Item 1 / Item 1A / customer-concentration sections cut out of each. All 23 SEC company numbers checked against SEC's own list.
- **Ripple tracer:** finds every path up to 4 steps from an event and scores each company's exposure (0–100). Tested with 51 hand-made SAMPLE links (clearly marked; not real evidence). 16 automated tests pass.

## How to run it
You need Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

```bash
python -m ripple init
```

```bash
python -m ripple status
```

Download SEC filings (needs `SEC_USER_AGENT` set, see `.env.example`):

```bash
python -m ripple sec-collect --companies micron,amkor
```

Leave out `--companies` to fetch all 23 SEC filers (takes a few minutes). Then cut out the useful parts:

```bash
python -m ripple cut-sections
```

Try the ripple tracer on the sample helium shock (only links known before March 2026):

```bash
python -m ripple load-sample
```

```bash
python -m ripple trace ras_laffan,helium --before 2026-03-01
```

Run the automated tests:

```bash
python -m pytest
```

## What you need to do yourself
- Nothing yet.
