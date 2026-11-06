# Front drill (frontal analysis trainer): design card

*A training game, not a scored study. Sibling of the pattern drill (`studies/2026-11-05-pattern-drill/`). Agreed with Jason in the thread "Build a frontal analysis trainer from OPC archives", 2026-11-06 11:33-11:53Z.*

**Question** (Jason's words): "another good training tool would be frontal analysis. could we use archived OPC analysis to build a database?"; "we need the full unified surface analysis at synoptic hours ... We want to focus on one storm system so we dont need a ton of time. it should be rapid fire because we dont have forever to make decisions on the desk"; "Drawing should tap points. we need several front type selections. Scoring on the distance should be generous. scoring should be stricter on front type"; "for data, we should get MSLP, 1000-850 equivilent potential temp, IR, 250 mb wind speed".

**What it is:** a web page. Each case is one storm system at one synoptic hour, maps shown, fronts hidden. The trainee taps points to lay each front, picks its type, then submits. The reveal overlays the Unified Surface Analysis fronts and lows and scores the drawing. Timed, about 60-90 s a case, many cases, session stats only (no accounts), same look as the pattern drill (cream, navy, oxblood).

**Truth:** the Unified Surface Analysis (OPC, WPC, NHC) as coded by WPC in the CODSUS bulletin (`ASUS02 KWBC`, 0.1 deg points, archived by IEM). Synoptic hours only (00, 06, 12, 18 UTC): the 03/09/15/21 bulletins are not the full ocean analysis. Types carried: cold, warm, occluded, stationary, trough; highs and lows with central pressure. Checked against OPC's two Atlantic charts for 2026-11-01 12Z: fronts and lows line up (`/mnt/project-files/frontal-trainer/opc-vs-coded-fronts-2026110112Z.png`). Coverage (checked over 28 synoptic analyses, 1-7 Dec 2025): ocean lows and fronts from about 25W to about 150W. The Atlantic HSF area is covered; the Pacific is only the north-east Pacific east of ~150W (WPC's map edge; points west of 152W south of 60N are a handful of front tails, and points to 180W are Alaska and the Bering Sea). The first estimate ("to ~170W") counted those Alaska points. 0.1 deg bulletins exist from ~2011, whole-degree back to 2005.

**Maps** (GFS analysis f000, 0.25 deg, box coarsened to 0.5 deg like the drill; imagery kept at ~0.1 deg). Jason chose MSLP, 1000-850 theta-e, IR, 250 hPa wind speed. After the expert review (below) the proposed set is five views, isobars on every one:
1. MSLP every 4 hPa with 1000-500 thickness and 10 m barbs (GFS f000; ASCAT barbs instead where a pass is within 90 min) (default).
2. Imagery: GOES air-mass RGB where it exists inside the disk (not west of ~165W / east of ~25W), IR otherwise; linear greyscale +25 to -65 C, no convective enhancement; within 30 min of the hour.
3. Theta-e at 850 hPa (Jason's 1000-850 mean is the alternative: the mean smooths the gradient and the 1000 hPa level carries sea-surface fluxes).
4. Theta-e at 700 hPa: the warm ridge wrapping into the low (TROWAL) for occlusions.
5. 3 h pressure tendency (falls ahead of the warm front, couplet at the triple point).
250 hPa isotachs as a checkbox overlay rather than their own map.

**Drawing:** tap points along a front, choose a type from cold / warm / occluded / stationary / trough, finish, start the next; undo and delete; place the low (L) by tap. Works on a phone.

**Scoring** (generous on position, strict on type):
- Analysed fronts are filled in to a point every 25 nm (coded points are a median 102 nm apart); same-type segments meeting within 30 nm are merged; truth is clipped to the box minus 1 deg and fronts with under 150 nm inside are not scored.
- Matching is one to one (one drawn line cannot claim the cold, warm and occluded fronts at a triple point). Distance is measured both ways over the overlapping part; coverage (share of the analysed length within 150 nm) gets a small weight of its own.
- Position: full credit within 150 nm, sliding to none at 300 nm.
- Type: worth twice position, and only scored when the front is matched (scaled by its position credit). Half credit for occluded vs cold near the triple point and for stationary vs a weak cold or warm front; none for cold vs warm.
- Missed fronts cost the most, weighted by length and nearness to the low. Troughs are never penalised, missed or extra (44% of coded features; drawn inconsistently).
- Low: full credit within 60 nm, none at 120 nm; either centre counts when the analysis has twin lows. Triple point as its own target later.
Constants live in one place in the page so they can be tuned after forecasters play it.

**Cases:** a case = an analysed low over open water (land mask, not a lat/lon box) inside the coverage above, with at least one non-trough front attached (an end within ~300 km), at 00/06/12/18Z, winters (Nov-Mar) 2024-25 and 2025-26 first; at most one case per low per day; balanced on front types (troughs left out of the balance). Keep a case only if: the GFS MSLP minimum is within 150 km and 4 hPa of the analysed low; no second analysed low within 500 km; and for the first deck, the low's non-trough front types match in the analyses 6 h before and after (analysts change types between charts about half the time). Box centred on the low. First deck ~200 cases.

**Parser rules** (`rk/fronts.py`): ASUS02 only; keep the last issue for a valid time (corrections); year from the header (VALID is MMDDHH); parse tokens, not lines (pressure/position pairs wrap); stop at `$$`; drop repeated points.

**Reveal:** OPC fronts and lows over the trainee's; triple point marked; one line per front type with the case's own numbers (cold: veer and theta-e drop; warm: backing and cloud shield; occluded: 700 theta-e ridge to the low; stationary: isobars along the front; trough: kink, no thermal gradient). Shapiro-Keyser cases noted as such (the coded analysis has no bent-back type; analysts draw it occluded or warm). Session stats include a front-type confusion table.

**Expert review (2026-11-06, three reviewers: surface analyst, satellite/conceptual models, verification with 24 bulletins checked):** changes above come from it. One reviewer saw fewer lows in 12Z bulletins over three days; a 28-analysis check (1-7 Dec 2025) did not repeat it (12Z 10-25 lows vs 9-33 at other hours), so no 12Z rule, but the 6 h consistency filter would catch a dropped system.

**Data:** GFS f000 records per case time (MSLP, 1000/500 hgt, T and RH at 850/700 (and 1000/925 for the mean), 250 u/v, 10 m u/v) plus MSLP 3 h earlier through `rk.fetch.gfs_global`, ~12 MB per time, ~200-400 times, a few GB streamed, resumable per-time caches under `rk.paths.data("extra", "front-drill")`. CODSUS text: one IEM request per day, cached. Well under 50 GB.

**Reused / new:**
- Reused: `rk.fetch.gfs_global`, `rk.diag` (theta_e, smooth, coarsen), `rk.satellite`, `rk.truth.ascat`, the drill's box, quantise, satellite and export code (`build_deck.py`, `page/export_site.py`), page skin.
- New in `rk/`: `rk/fronts.py` (fetch + parse CODSUS into fronts and pressure centres, cached; with a test), so any later study (front-relative ASCAT, frontal wind maxima) can use the analysed fronts.
- New here: `find_cases.py`, `build_deck.py`, `page/`.

**Publish:** its own folder on the drill site (jkrek17/pattern-drill, `/fronts/`) once Jason has played a private preview.

**Out of scope for v1:** whole-basin analysis mode, highs, pressure calls, squall lines and dry lines, years before 2021 (no GFS analyses on AWS; ERA5 would be needed).
