# Marine research

Shared code, rules and templates for the forecast research behind the marine wind page and the desk's GFE tools. Every study from 13 to 16 October 2026 rebuilt the same pieces by hand (case lists, model downloads, ASCAT and buoy truth, scores, figures). They live here once.

| | |
|---|---|
| `STUDIES.md` | Every study: the question, the one-line answer, where it lives |
| `LESSONS.md` | Traps we hit, and which ones the code now guards against |
| `STYLE.md` | Figures (light), write-ups, review pages |
| `rk/` | The library: `cases`, `fetch`, `store`, `truth`, `score`, `compare`, `style` (interface: `rk/CONTRACT.md`) |
| `templates/` | Design card, findings write-up, review page |
| `tools/fill_store.py` | Fill the shared data store for a range of cycles |
| `.claude/skills/research-study/` | The study loop for Claude sessions |
| `studies/` | One folder per study from now on |

## Data
Bulk data is not in git. It lives in one shared folder, `RK_DATA` (default `/mnt/project-files/research-data/`):

```
fields/{natl,npac}/{YYYYMMDDHH}/{gfs,ifs,aifs}_fFFF.npz    10 m u, v and MSLP
fields/{natl,npac}/{YYYYMMDDHH}/{gefs,ens,aifs-ens}_fFFF.npz  member statistics: mean, spread, chance of 34/48/64 kt, MSLP mean and spread
truth/analysis/{natl,npac}/{YYYYMMDDHH}.npz                GFS and IFS analyses, open-water mask
truth/ascat/{YYYYMMDD}.npz                                 RSS ASCAT cells for the day
truth/obs/...                                              buoys and ships rebuilt from GDAS
```

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
