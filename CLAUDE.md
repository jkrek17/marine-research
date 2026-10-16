# Working in this repository

Research for the marine forecast desk: models, ensembles, ASCAT and buoys, scored in forecaster terms. Results feed the marine wind page and GFE tools in jkrek17/awips-tools, but only after Jason agrees. Several threads run studies at once, so the shared code, data and rules live here.

## Build for the long term (Jason, 2026-10-16)
If something can be made reusable and efficient, that comes first. Downloads, truth and scores come from `rk/`; a study that needs a new one adds it to `rk/` (with a test) rather than writing a private copy, and its design card says what is reused and what is new.

## First
1. Read `STUDIES.md` and `LESSONS.md`.
2. Run `git config core.hooksPath .githooks`.
3. For any study, load the `research-study` skill (`.claude/skills/research-study/SKILL.md`).

## Where things go
- Code and small results (CSV, markdown, PNG under 1 MB): `studies/<yyyy-mm-dd>-<name>/`.
- Shared library: `rk/` (interface in `rk/CONTRACT.md`; change the contract first).
- Fields, truth tables, ASCAT: the shared data store, `RK_DATA` (default `/mnt/project-files/research-data`), through `rk.store` and `rk.truth`. Never in git.

## Wait for Jason
- Any change to awips-tools, hf-low or a public page that comes out of a study.
- Pulls expected to stream more than ~50 GB: give the estimate and what the store already has.

## Merging (Jason, 2026-10-16)
Pull requests here merge themselves once the tests and `tools/check_repo.py` pass; tell Jason in one line what landed.

## Never
- Commit data, caches, tokens or files over 10 MB, or use `git add -A` / `git add .`.
- Hardcode `/home/...` or `/tmp/...` paths; find the repo from `__file__` and data from `rk.paths`.
- Run heavy downloads during the marine wind build windows (`rk.fetch` waits them out) or beside a verification backfill.
- Tune on the held-out weeks (`rk.cases.held_out`).

## Last
- Update the study's row in `STUDIES.md`; add any lesson to `LESSONS.md`.
- Run `python3 tools/check_repo.py` and the tests (`for t in tests/test_*.py; do python3 $t; done`) before opening a pull request.
- Numbers in the commit body.
