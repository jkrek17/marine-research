# GFE without ECMWF ensembles: findings

**Answer:** with GFS + ECMWF deterministic runs and GEFS 34/48/64 kt shares, the GFE can come close to the page on storm force. The 0.5 deg GEFS grid AWIPS holds costs almost nothing against 0.25 deg on any of the three.

1. **Storm core lift: passes.** A core model retrained on GFS/IFS + GEFS clues lifts the GFS + ECMWF deterministic blend by 5 kt where its chance is >= 0.67. Storm-tile catch rises from 36% to 59% (Atlantic) and from 22% to 36% (Pacific), at 0.63 / 0.43x ASCAT's storm area. That is the same catch as the page's Core Lifted (60% / 36%), which uses all three ensembles. It does carry more false storm tiles (18% vs 12% Atlantic, 28% vs 23% Pacific). Gale scores are unchanged. A simpler rule with no trained model (+5 kt where GEFS 48 kt share within ~1 deg >= 25%) does nearly as well: 57% / 38% catch at 0.66 / 0.51x area.
2. **Gale-core lift: fails in the Pacific.** It adds about 10 points of ASCAT gale cells caught in both basins. The Pacific gale area reaches 1.37x ASCAT, over the 1.3 cap (Atlantic 1.21). This is the same Pacific overshoot the 10-17 gale-core study saw.
3. **Chances:**
   - **Gale:** the GEFS gale chance needs its own remap. Raw GEFS 30% is about 17% true in the Atlantic and 15% in the Pacific (days 1-2, against the ASCAT box). The remap passes in both basins at every lead.
   - **Storm, Atlantic:** the remap passes. Raw 30% is about 56% true, and Brier skill goes .41 -> .47 at days 1-2.
   - **Storm, Pacific:** the remap fails, because raw GEFS is already about reliable there (error .006) and the fitted curves are unstable on ~2.5k tune events. Use raw GEFS storm chances in the Pacific.
   - **Hurricane force:** stays raw and labelled "not calibrated".
   - **Cost of the missing ensembles:** GEFS alone trails the page's pooled, refitted storm chance by about .06 Brier skill (Atlantic .47 vs .53, Pacific .28 vs .34, days 1-2).
4. **HF line gated on GEFS: passes on the held-out weeks, but weaker on the tune weeks.** The rule is the strongest of GFS/ECMWF + 20 kt, kept where at least 1 GEFS member reaches 64 kt within ~1 deg.
   - Held-out Atlantic: it catches the same lows as the page's pooled gate, 25 of 29 within 150 km (86%), at 0.90x its area. It also has fewer areas with no low (62% vs 73%).
   - Tune weeks: it caught 71% of lows (69 of 97). The row-level recheck put it at 67% against the pooled gate's 81% on the same rows, so on the larger sample the GEFS gate misses more.
   - Stricter gates (2 or 3 members) lose too many lows.
   - Pacific: untestable (3 held-out lows).

**Recommendation for GFE:**
- Storm lift on the deterministic blend: the trained GEFS model, or the no-model GEFS 48 kt share rule if a trained model is hard to carry in a smart tool. They are within 2 points of each other.
- Gale-core lift: none yet in the Pacific.
- Chances: GEFS remaps for gale (both basins) and Atlantic storm; raw GEFS for Pacific storm; raw 64 kt as a flag.
- HF line: the 1-member GEFS gate, with the note that on the tune weeks it missed more lows than the pooled gate.

Truth: ASCAT real 10 m wind (intercal); the box mean for chances, 48+/34+ within ~50 km and 5x5 deg tiles for cores; hf-low archive lows within 150 km for HF. Data: winter 2025-26; held-out ISO weeks 2025-45, 2025-50, 2026-02, 2026-07 and 2026-12.
- Cores: Atlantic 350 cases (00/12 UTC valid, +24..+120); Pacific 700 cases (adds the 06/18 UTC valid times).
- Chances: Atlantic 70 held-out cycles, Pacific 105.
- HF: the warning study's case set (00/12 UTC, +24/+48 h).

Thresholds were set on tune weeks only. The storm lift threshold t = 0.67 was chosen so the storm area matched live Core Lifted's on tune cells; gale-core t = 0.6. CV on tune: storm model Brier skill .405 / ROC .93 (raw GEFS 48 kt share .29 / .88).

**Caveats:**
- **Sample:** five held-out weeks; the intervals are coarse.
- **Low-level clues:** GFS only. IFS low-level files are missing for part of the winter, so this is not the live definition.
- **0.5 deg:** the stored 0.25 deg shares subsampled to 0.5 deg points and interpolated back (`rk.features.half_deg`), not NCEP's own 0.5 deg probability product.
- **AWIPS definition, assumed:** the AWIPS GEFS probabilities are sustained 10 m wind member shares.
- **Live table:** which page chance table is live (current or 10-17 refit) was not re-checked.

**Check:** a second agent recomputed the core and HF numbers from the per-case rows and the chance pass/fail from results.csv, without reading the write-ups. Core: every number matched to the third decimal, including the week-bootstrap intervals. HF: the held-out "same catch as pooled at ~0.87-0.90x area" matched; counted by rows rather than lows, the tune-week gap (67% vs 81%) is the one quoted above. Chances: pass/fail matched.

Files: `chances/verdict.md`, `core/verdict.md`, `hf/verdict.md` and their CSVs.
