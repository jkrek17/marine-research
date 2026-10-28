# AI-GFS as the AI member of the GFE blend: design card

*Jason 2026-10-28: "I have the AI-GFS, not the AIFS", then 05:18Z "yes lets try it. deterministic", then 05:31Z "yea choose" on the three proposed choices (recipe, variants, win line below). Win line preset here before any run.*

**Question** (Jason): his AWIPS carries NOAA's AI-GFS (AIGFS, GraphCast-based, deterministic), not ECMWF's AIFS. Can AI-GFS take the AI model's place in the GFE blend?

**What would change if the answer is yes/no:** the AI model in the GFE deterministic blend (awips-tools GFE PR #95, `Blend_WindGustWavePmsl`, "Deterministic blend for Wind"). Yes: AI-GFS replaces AIFS at the winning weight. No: GFE uses GFS + ECMWF only, or AI-GFS at the weight that passes. The web page keeps AIFS either way. Only Jason can check a GFE change.

**Recipe scored:** the page's "Deterministic blend" (`nomem` in awips-tools `marine_wind/pipeline/build.py`), the GFE candidate: support-weighted base of the 3 current runs, where support counts the 9 runs (3 models x the current, 12 h and 24 h earlier runs at the same valid time; Gaussian kernel 5 kt), AI model weighted by `MODEL_WEIGHT`, + min(0.3 x SD of the 9 runs, 5 kt). No members, no core lift (both need ensembles). Scored only where all runs are present.

**Variants** (identical except the AI slot):
- A: GFS + ECMWF + AIFS at half weight (the recipe as it stands; the bar).
- G1: GFS + ECMWF + AI-GFS at full weight.
- G½: GFS + ECMWF + AI-GFS at half weight.
- N: GFS + ECMWF only (6 runs for support and spread).

**Truth:** ASCAT real 10 m wind (`rk.truth.ascat_target`, intercal), passes within 90 min of the valid time; buoys as a bias check at 34+ kt (report only).

**Win line (preset; the AIFS test's bar, with N as the thing to beat because AIFS is not on offer in GFE):** an AI-GFS variant (G1 or G½) goes into the GFE blend only if, against N, on held-out weeks, in BOTH basins, pooled over the scored leads:
1. gale tiles (5x5 deg, any ASCAT 34+): CSI higher, with the whole-week 95% interval of the difference above zero; and
2. storm tiles (48+): catch not lower than N's by more than 2 points; and
3. 34+ area ratio (forecast / ASCAT at seen cells) not further from 1 than N's.
If both pass, take the one with the higher gale CSI. If neither passes, GFE runs GFS + ECMWF (N). A is scored beside them to say how much of the AIFS gain AI-GFS recovers; it does not decide. Per-lead and buoy numbers are reported but do not decide.

**AI-GFS alone (description, not a decision):** bias and catch at 34/48 kt vs ASCAT for GFS, ECMWF, AIFS, AI-GFS, by basin and lead, and the cold-air split (2 m air minus skin temperature as in the stability study) to see if AI-GFS runs low in cold air like AIFS (~4 kt).

**Cases:** winter 2025-26 (1 Nov - 31 Mar), 00 and 12 UTC cycles, steps +24..+120 every 24 h; Pacific also the 06/18 UTC valid times (+30..+126). Held-out weeks per `rk.cases.held_out`. Nothing is fitted (weights preset), so tune weeks are also reported, labelled as a second look.

**Data:**
- AI-GFS on AWS `noaa-nws-graphcastgfs-pds`. The current model went live there on 2025-12-19 (the live stream equals NOAA's `hindcast_aigfsdev2.5` run to 0.00 kt from that date, and equals the operational `aigfs.*` feed in the Apr-May 2026 overlap to 0.01 kt). Source by cycle: `hindcast_aigfsdev2.5/` before 2025-12-19, `graphcastgfs.*` 2025-12-19 .. 2026-04-15, `aigfs.*` from 2026-04-16. Assumed: Jason's AWIPS AI-GFS = the operational `aigfs` feed.
- Store: GFS/IFS/AIFS 00/12 UTC runs hold +24..+144 every 6 h except 42, 66, 90, 114, 138, 150, which the 06/18 UTC lagged runs need; those are added for the three models.
- Volume: AI-GFS u, v, msl ~2.8 MB per step before 19 Dec .. Feb (packed), ~9.7 MB in March (simple packing); 22 steps x 302 runs ~ 28 GB. GFS/IFS/AIFS extra steps ~15 GB. Total ~45 GB, under the 50 GB line. Held-out weeks first (~9 GB), the rest after.

**Reused / new:** `rk.store` (new det model `aigfs`), `rk.fetch.det` (new `aigfs`, through `nwp`), `rk.truth.ascat_target`, `rk.score.tile_hits`, `rk.compare.paired`, `rk.style`. New in shared code: an `aigfs` source in awips-tools `nwp` (URL by cycle as above), and `rk.features.det_blend` (the deterministic recipe with lagged runs and model weights, constants copied from awips-tools), with tests.

**Known traps:** AIFS ~4 kt low at gales in cold air; dropping AIFS failed the Pacific false-alarm bar (gale FA .145 -> .239); Pacific ASCAT must include 06/18 UTC; score peaks on tiles, not only cells; the AWS archive switches model on 2025-12-19 (never use the live stream before that date).

**Out of scope:** AI-GFS ensemble (Jason is looking for the members); the web page; MSLP and gust weights in GFE.
