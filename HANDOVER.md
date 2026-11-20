# Ripple — handover notes

(Work in progress — this file is updated after each step.)

## Done so far
- **Phase 0:** project folders, database with every table, 51 seed nodes (all 38 companies + places and materials).
- **Phase 1 (SEC part):** SEC EDGAR collector + section cutter. Tested on Micron, Amkor, TSMC, Vertiv and Nvidia: 36 filings downloaded, and Item 1 / Item 1A / customer-concentration sections cut out of each. All 23 SEC company numbers checked against SEC's own list.

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

## What you need to do yourself
- **GitHub upload was refused.** Pushing to `yzymbiote/Ripple` returned "Claude doesn't have GitHub access". All work is committed in this session's copy of the repo on branch `claude/awesome-maxwell-57hsme` but could not be uploaded. Fix: connect GitHub at https://claude.ai/connect-github and install the Claude GitHub App on the repository, then ask me (or any session) to push the branch.
