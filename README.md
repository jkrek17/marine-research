# Marine research

Shared code, rules and templates for the forecast research behind the marine wind page and the desk's GFE tools. Every study from 13 to 16 October 2026 rebuilt the same pieces by hand (case lists, model downloads, ASCAT and buoy truth, scores, figures). They live here once.

| | |
|---|---|
| `STUDIES.md` | Every study: the question, the one-line answer, where it lives |
| `LESSONS.md` | Traps we hit, and which ones the code now guards against |
| `STYLE.md` | Figures (light), write-ups, review pages |
| `rk/` | The library: `cases`, `fetch`, `store`, `truth`, `score`, `compare`, `style` (interface: `rk/CONTRACT.md`) |
| `templates/` | Design card, findings write-up, review page |
| `tools/fill_store.py` | Fill the field store (local cache) for a range of cycles |
| `tools/publish_store.py` | Publish locally written fields to the marine-research-data releases |
| `.claude/skills/research-study/` | The study loop for Claude sessions |
| `studies/` | One folder per study from now on |

## Data
Bulk data is not in git, and the shared folder is too small for the model fields, so there are three places:

```
GitHub Releases (jkrek17/marine-research-data, public)   model fields, one release per basin and month
  fields-{natl,npac}-{YYYYMM} / {basin}_{YYYYMMDDHH}.zip   zip of that cycle's npz files (below)
RK_CACHE (default ~/.cache/marine-research)              local copy, same layout, filled on demand
  fields/{natl,npac}/{YYYYMMDDHH}/{gfs,ifs,aifs}_fFFF.npz    10 m u, v and MSLP
  fields/{natl,npac}/{YYYYMMDDHH}/{gefs,ens,aifs-ens}_fFFF.npz  member statistics: mean, spread, chance of 34/48/64 kt, MSLP mean and spread
RK_DATA (default /mnt/project-files/research-data/)      truth tables and small results
  truth/analysis/{natl,npac}/{YYYYMMDDHH}.npz                GFS and IFS analyses, open-water mask
  truth/ascat/{YYYYMMDD}.npz                                 RSS ASCAT cells for the day
  truth/obs/...                                              buoys and ships rebuilt from GDAS
```

`rk.store.load_det / load_ens / load` look in the cache, then the old `RK_DATA/fields` (kept while the move happens), then download the cycle's zip from the release and unpack it into the cache. `fill` and `rk.store.put(basin, cycle, name, **arrays)` write to the cache and mark the file unpublished; `python3 tools/publish_store.py --repo <clone of marine-research-data>` (or `RK_DATA_REPO`) sends unpublished files to the data repo, whose workflow turns them into release assets. Merging with the published asset means an extension never drops another thread's files. `RK_OFFLINE=1` stops downloads.

Boxes are the tested areas: North Atlantic 30-67N 75W-0 (12 UTC cycles) and North Pacific 30-67N 160E-115W (00 UTC cycles). Model archives on AWS start March 2025 (AIFS ENS August 2025).

## Quick start
```python
import datetime as dt
from rk import cases, store, truth, score, style

cyc = dt.datetime(2026, 1, 15, 12)
f = store.load_det("natl", cyc, "gfs", 48)            # speed in kt
a = truth.analysis("natl", cyc + dt.timedelta(hours=48))
print(score.csi(f["speed"], a["mean_speed"], 34, mask=a["mask"]))
```

Requirements: `requirements.txt`.
