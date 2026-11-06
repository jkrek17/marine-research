# Front drill (frontal analysis trainer): design card

*A training game, not a scored study. Sibling of the pattern drill (`studies/2026-11-05-pattern-drill/`). Agreed with Jason in the thread "Build a frontal analysis trainer from OPC archives", 2026-11-06 11:33-11:53Z.*

**Question** (Jason's words): "another good training tool would be frontal analysis. could we use archived OPC analysis to build a database?"; "we need the full unified surface analysis at synoptic hours ... We want to focus on one storm system so we dont need a ton of time. it should be rapid fire because we dont have forever to make decisions on the desk"; "Drawing should tap points. we need several front type selections. Scoring on the distance should be generous. scoring should be stricter on front type"; "for data, we should get MSLP, 1000-850 equivilent potential temp, IR, 250 mb wind speed".

**What it is:** a web page. Each case is one storm system at one synoptic hour, maps shown, fronts hidden. A soft dashed ring marks the system to analyse ("Analyse the system inside the ring: place its low and draw its fronts"). The trainee taps points to lay each of its fronts, picks the type, then submits. The reveal overlays the Unified Surface Analysis fronts and lows and scores the drawing. Timed, about 60-90 s a case, many cases, session stats only (no accounts), same look as the pattern drill (cream, navy, oxblood).

**Truth:** the Unified Surface Analysis (OPC, WPC, NHC) as coded by WPC in the CODSUS bulletin (`ASUS02 KWBC`, 0.1 deg points, archived by IEM). Synoptic hours only (00, 06, 12, 18 UTC): the 03/09/15/21 bulletins are not the full ocean analysis. Types carried: cold, warm, occluded, stationary, trough; highs and lows with central pressure. Checked against OPC's two Atlantic charts for 2026-11-01 12Z: fronts and lows line up (`/mnt/project-files/frontal-trainer/opc-vs-coded-fronts-2026110112Z.png`). Coverage (checked over 28 synoptic analyses, 1-7 Dec 2025): ocean lows and fronts from about 25W to about 150W. The Atlantic HSF area is covered; the Pacific is only the north-east Pacific east of ~150W (WPC's map edge; points west of 152W south of 60N are a handful of front tails, and points to 180W are Alaska and the Bering Sea). The first estimate ("to ~170W") counted those Alaska points. 0.1 deg bulletins exist from ~2011, whole-degree back to 2005.

**Maps** (GFS analysis f000, 0.25 deg, box coarsened to 0.5 deg like the drill; imagery kept at ~0.1 deg). Jason chose MSLP, 1000-850 theta-e, IR, 250 hPa wind speed. After the expert review (below) Jason approved this set of five views (12:01Z), isobars on every one:
1. MSLP every 4 hPa with 1000-500 thickness and 10 m barbs (GFS f000; ASCAT barbs instead where a pass is within 90 min) (default).
2. Imagery: GOES air-mass RGB only for a case low at or south of 55N and inside the disk (east of ~25W is outside it); GridSat IR otherwise (the RGB goes false purple near the disk edge at high latitude: 39 of 141 case lows were north of 60N); linear greyscale +25 to -65 C, no convective enhancement; within 30 min of the hour.
3. Theta-e at 850 hPa (chosen over the 1000-850 mean: the mean smooths the gradient and the 1000 hPa level carries sea-surface fluxes).
4. Theta-e at 700 hPa: the warm ridge wrapping into the low (TROWAL) for occlusions.
5. 3 h pressure tendency (falls ahead of the warm front, couplet at the triple point).
250 hPa isotachs as a checkbox overlay rather than their own map.

**Drawing:** tap points along a front, choose a type from cold / warm / occluded / stationary / trough, finish, start the next; undo and delete; place the low (L) by tap. Works on a phone.

**Scoring** (generous on position, strict on type):
- Analysed fronts are filled in to a point every 25 nm (coded points are a median 102 nm apart); same-type segments meeting within 30 nm are merged; truth is clipped to the box minus 1 deg and fronts with under 150 nm inside are not scored.
- Only the case low's SYSTEM is scored ("The system", below): other fronts in the box are shown greyed at the reveal as "other systems, not scored" and are never missed or extra. A drawn front with no match is penalised as extra only when at least half of it lies inside the ring; fronts drawn outside the ring cost nothing.
- Matching is one to one (one drawn line cannot claim the cold, warm and occluded fronts at a triple point). Distance is measured both ways over the overlapping part; coverage (share of the analysed length within 150 nm) gets a small weight of its own.
- Position: full credit within 150 nm, sliding to none at 300 nm.
- Type: worth twice position, and only scored when the front is matched (scaled by its position credit). Half credit for occluded vs cold near the triple point and for stationary vs a weak cold or warm front; none for cold vs warm.
- Missed fronts cost the most, weighted by length and nearness to the low. Troughs are never penalised, missed or extra (44% of coded features; drawn inconsistently).
- Low: credit for the analysed low in the ring nearest to the trainee's L: full within 60 nm, none at 120 nm; either centre counts when the analysis has twin lows. The ring is centred 0-120 nm (deterministic per case id) off the true low and has radius `sys_r_nm`, so it does not give the L away. Triple point as its own target later.
Constants live in one place in the page so they can be tuned after forecasters play it.

**Cases:** a case = an analysed low over open water (land mask, not a lat/lon box) inside the coverage above, with at least one non-trough front attached (an end within ~300 km), at 00/06/12/18Z, winters (Nov-Mar) 2024-25 and 2025-26 first, ATLANTIC ONLY (Jason 12:01Z: "Atlantic only is fine"); at most one case per low per day; balanced on front types (troughs left out of the balance). Keep a case only if: the GFS MSLP minimum is within 150 km and 4 hPa of the analysed low; no second analysed low within 500 km; and for the first deck, the low's non-trough front types match in the analyses 6 h before and after (analysts change types between charts about half the time). Box centred on the low. First deck ~200 cases.

**The system** (Jason, 2026-11-06: one storm system per case; the first deck scored every non-trough front in the 25 x 40 deg box, up to 8 fronts and 8 lows from several systems). `build_deck.py` (`frontlib.mark_system`) flags each truth front `"sys": true` when it belongs to the case low's system: a non-trough front with an end within 300 km of the low, then, repeatedly, any front (a trough too) with an end within 60 nm of a point of a non-trough system front (the cold front trailing from the triple point of an occlusion, a stationary continuation); troughs are attached this way but never extend the system. `sys_r_nm` is the farthest system point from the low plus 60 nm, capped at 900. A case is dropped when its system has under 250 nm of non-trough front after clipping. Hints are written for the system's front types only. 2026-11-06 deck: 134 of 143 picked cases kept (9 dropped); scored fronts per case 1: 73, 2: 32, 3: 24, 4 or more: 5; greyed non-system fronts 0-9 per case.

**Parser rules** (`rk/fronts.py`): ASUS02 only; keep the last issue for a valid time (corrections); year from the header (VALID is MMDDHH); parse tokens, not lines (pressure/position pairs wrap); stop at `$$`; drop repeated points.

**Reveal:** OPC fronts and lows over the trainee's (the system's in full colour, other systems thin and grey, "not scored"); the hint footer says analysts draw a front on the warm edge of the temperature change and at the wind shift, not in the middle of the theta-e gradient; triple point marked; one line per front type with the case's own numbers (cold: veer and theta-e drop; warm: backing and cloud shield; occluded: 700 theta-e ridge to the low; stationary: isobars along the front; trough: kink, no thermal gradient). Shapiro-Keyser cases noted as such (the coded analysis has no bent-back type; analysts draw it occluded or warm). Session stats include a front-type confusion table.

**Expert review (2026-11-06, three reviewers: surface analyst, satellite/conceptual models, verification with 24 bulletins checked):** changes above come from it. One reviewer saw fewer lows in 12Z bulletins over three days; a 28-analysis check (1-7 Dec 2025) did not repeat it (12Z 10-25 lows vs 9-33 at other hours), so no 12Z rule, but the 6 h consistency filter would catch a dropped system.

**Data:** GFS f000 records per case time (MSLP, 1000/500 hgt, T and RH at 850/700, 250 u/v, 10 m u/v) plus MSLP 3 h earlier through `rk.fetch.gfs_global`, ~12 MB per time, ~200-400 times, a few GB streamed, resumable per-time caches under `rk.paths.data("extra", "front-drill")`. CODSUS text: one IEM request per day, cached. Well under 50 GB.

**Reused / new:**
- Reused: `rk.fetch.gfs_global`, `rk.diag` (theta_e, smooth, coarsen), `rk.satellite`, `rk.truth.ascat`, the drill's box, quantise, satellite and export code (`build_deck.py`, `page/export_site.py`), page skin.
- New in `rk/`: `rk/fronts.py` (fetch + parse CODSUS into fronts and pressure centres, cached; with a test), so any later study (front-relative ASCAT, frontal wind maxima) can use the analysed fronts.
- New here: `find_cases.py`, `build_deck.py`, `page/`.

**Publish:** its own folder on the drill site (jkrek17/pattern-drill, `/fronts/`) once Jason has played a private preview.

**Out of scope for v1:** whole-basin analysis mode, highs, pressure calls, squall lines and dry lines, years before 2021 (no GFS analyses on AWS; ERA5 would be needed).

## Deck format (contract between `build_deck.py` and the page)

Same box as the pattern drill: 0.5 deg, 51 x 81 cells (25 x 40 deg), centred on the analysed low; one snapshot per case (the analysis hour).

`deck/manifest.json`:
```
{"version": 1, "res": 0.5, "ny": 51, "nx": 81,
 "fields": [{"key": "msl", "name": "...", "units": "hPa", "offset": 930, "scale": 0.5}, ...],
 "cases": [{"id": "f0001", "lat0": 62.0, "lon0": 300.0,      # north-west cell centre, lon 0-360
            "low": {"lat": .., "lon": .., "hpa": ..},          # analysed low (truth)
            "lows": [{"lat":..,"lon":..,"hpa":..}, ...],        # every analysed low in the box (twin centres)
            "fronts": [{"type": "cold"|"warm"|"occluded"|"stationary"|"trough",
                        "pts": [[lat, lon], ...],
                        "sys": true|false}, ...],           # merged, densified 25 nm, clipped to the box minus 1 deg; sys: belongs to the case low's system
            "sys_r_nm": 692,                                    # ring radius around the case low, nm
            "img": "am"|"ir"|null, "ascat": true|false,
            "hints": {"cold": "...", ...}}]}                    # one line per non-trough front type of the system, numbers from the case
```
Fields in order (uint8, value = offset + scale x byte, 255 missing): `msl` (930, 0.5 hPa), `thk` (470, 0.5 dam), `u10`, `v10` (-40, 0.32 m/s), `te850` (240, 0.5 K), `te700` (240, 0.5 K), `dp3` (3 h MSLP change, -12.7, 0.1 hPa), `wspd250` (0, 1 kt), `ascat_spd` (0, 1 kt, 255 unseen), `ascat_dir` (0, 2 deg), `land` (0/1).
`img` is "am" only when the case low is at or south of 55N and the box centre is inside the GOES-East disk (not east of 25W), "ir" (GridSat IR) otherwise, null when neither exists. A manifest without `sys` / `sys_r_nm` (an older deck) is read by the page as all fronts in the system and no ring.

`deck/<id>.bin` = the fields in that order, each `ny x nx`, row 0 north. `deck/<id>_am.jpg` or `_ir.jpg`: imagery at 0.1 deg over the box's cell-edge extent (250 x 400 px), as the drill. `key.csv` (not published) maps ids to valid times.
