# Which forecast cores reach hurricane force? The blend peak already sorts them

*2026-10-18 · every 00/12 UTC cycle Nov 2025 - Mar 2026, both basins, lead days 1-3 · every forecast core (core probability >= 0.35, at least 20 cells) that ASCAT saw well · truth: ASCAT real 10 m, HF core = at least 3 seen cells >= 64 kt · pre-set rule: `design.md`*

## The answer
Jason: "you cant blindly add 13 kts to every core ... we need to map across all ascat." So this scored every forecast core ASCAT saw, not just the archive's lows, and asked what tells the hurricane-force cores from the rest.

**The blend's peak wind in the core already separates them about as well as anything we fitted.**

| Held-out weeks | ROC area | Atlantic only |
|---|---|---|
| Blend peak in the core (r10 max) | 0.91 | 0.89 |
| Core probability peak | 0.89 | 0.85 |
| Fitted model (depth, ensemble 64 kt chance, area, and more) | 0.91 | 0.89 |

The fitted model fails the pre-set rule: it beats the core probability peak by +0.02 [-0.11, +0.10], and the blend peak by -0.01. Depth does carry signal on its own (deeper low, more HF; ROC about 0.75), but nothing beyond the winds.

**Chance that a core reaches hurricane force, by the blend peak (all 641 cores; held-out in brackets):**

| Blend peak in the core | HF cores |
|---|---|
| under 45 kt | 2% [0%] |
| 45-50 kt | 7% [7%] |
| 50-55 kt | 43% [51%] |
| 55 kt or more | 75% [77%] |

The same climb shows by core probability (3% under 0.9, 55% at 0.995 or above) and by the ensemble chance of 64 kt (2% at zero, 80% at 0.15 or more).

## What it means for a lift
- **A blind lift is wrong, as Jason said.** Under 50 kt blend peak, 95% of cores never reach hurricane force.
- **But a gate is available from the forecast itself.** As untuned examples on held-out weeks: a blend peak of 50 kt or more flags 57 cores, catching 35 of the 39 HF cores (90%) with 39% false alarms; 55 kt or more catches 44% with 23% false alarms.
- So a lift, if any, should be conditional on the blend peak (or the chance of HF built from it), not applied to every core, and the 64 kt it draws carries a 25-40% false-alarm rate even then. A chance-of-hurricane-force shading built from the blend peak may be the more honest product.

## How solid
An independent recheck reproduced every number and spot-checked the core finder on two cycles from the store.
- **Few independent storms.** The 39 held-out HF cores come from about 7 storms; one (9-10 Dec) gives 21. The whole winter has about 25 HF storms. Dropping any held-out week moves the ROC areas by up to 0.04; without that December week the rate table is 5% / 40% / 72%.
- **The core probability was trained on this winter's Atlantic ASCAT** (at 48 kt), so its 0.89 is partly in-sample. The blend peak isn't trained on ASCAT, which makes it the cleaner number.
- **"Every core ASCAT saw" means cores ASCAT saw well:** at least 100 seen cells and 30% of the core. Only 641 of 3,463 cores qualified; the floor favours larger cores, and in the Atlantic only 00/12 UTC valid times are seen.
- **The label grows with how much ASCAT saw:** bigger cores have more cells to reach 3 at 64 kt. With the label as "at least 1% of seen cells", the blend peak's held-out ROC is 0.89 and the core probability's 0.88.
- **Big merged cores:** 25 scored cores are over 2,000 cells and 23 of them are HF; some join several wind peaks.
- **The Pacific can't be judged:** 7 HF cores all winter (103 cores).
- The fitted model's flagging table in `final_results.md` uses a threshold set on in-sample predictions, so its 46% hit / 14% false-alarm figure flatters it; at the same number of flags, a 55 kt blend peak does about as well.
- ASCAT is unsettled above 56 kt.

## Files
`cores.py` (core table, `cores.csv`), `fit.py` (`tune_results.md`; `--final` once: `final_results.md`, `final_results.json`), `design.md`.
