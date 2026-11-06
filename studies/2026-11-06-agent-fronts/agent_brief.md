# Brief: analyse the surface fronts of one storm system (first-guess fronts)

You are a surface analyst at the Ocean Prediction Center drawing the first-guess fronts for one storm system on a
GFS analysis. Each case folder holds what a forecaster sees, and nothing else:

- `case.txt`: basin, valid time, the system's analysed low (given), other lows in the ring, the ring radius, and the
  system's stationary fronts (given, already drawn; never scored).
- `panel_msl.png` (MSLP every 4 hPa, 1000-500 thickness dashed, GFS 10 m barbs), `panel_img.png` (air-mass RGB or IR,
  when there is one), `panel_te850.png`, `panel_te700.png` (theta-e shaded every 3 K), `panel_dp3.png` (3 h pressure
  change), `panel_wind.png` (GFS 10 m speed). Every panel has a labelled lat/lon grid, the L(s) and the dashed ring.
- `examples/`: two similar past cases from other weeks with their analysed fronts drawn (`exN_msl.png`, `exN_te850.png`)
  and listed as coordinates (`answers.txt`). Use them to calibrate where analysts put fronts relative to the fields.
- Tools (run from any directory): `python3 TOOLS <case_dir> section LAT1 LON1 LAT2 LON2` (850 theta-e, 10 m wind
  direction/speed and MSLP every ~50 nm along a line: use it across a suspected front to find the wind shift and the
  warm edge of the theta-e drop), `python3 TOOLS <case_dir> gradmax LAT LON [RADIUS_NM]`, and
  `python3 TOOLS <case_dir> troughs`. Longitudes are + east / - west.

## What to draw
Only this system's COLD, WARM and OCCLUDED fronts (the L and stationary fronts are given; troughs are ignored).
Conventions the analysis follows:
- A front sits on the WARM edge of the theta-e (thickness) gradient, at the wind shift and in the pressure trough,
  not in the middle of the gradient.
- Cold front: veer from SW to W/NW across it, theta-e falls behind it, usually trailing equatorward from the triple point.
- Warm front: backing ahead, falls in the 3 h tendency ahead of it, cloud shield poleward; runs from the triple point
  east or south-east.
- Occluded front: from the low out to the triple point, along the 700 hPa warm tongue (TROWAL) wrapping into the low.
  A mature low may have only an occlusion plus a cold front; a young wave only a cold and a warm front meeting at the low.
- Shapiro-Keyser lows (bent-back warm front, T-bone) are coded as occluded or warm.

## How it is scored (the front drill's own scorer, the same as a forecaster)
Position: full credit within 150 nm of the analysed front, none beyond 300 nm. Type is worth twice position and only
counts when the front is matched (occluded vs cold half credit; cold vs warm none). A missed front costs the most,
weighted by its length and nearness to the low. An extra front with no match costs a quarter of a front when at least
half of it is inside the ring (at most one front in all). So: draw every front you believe is there, get the type
right, and don't scatter guesses inside the ring.

## Output
Write `answer.json` in the case folder:
```
{"case": "<id>",
 "fronts": [{"type": "cold"|"warm"|"occluded", "pts": [[lat, lon], ...], "why": "one line of evidence"}, ...],
 "note": "anything that made the case hard (optional)"}
```
Points every ~100 nm (4-12 per front), in order along the front, lon + east / - west. They are joined with a smooth curve.

## Rules
Work only from the files in your case folders and the tool. Do not open any other file on disk (the drill deck,
its manifest or key, the repository, other case folders' answers): the point is a blind first guess.
