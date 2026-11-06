# Agentic first-guess fronts: design card

*Pilot. For Jason's yes before any run. Sibling of the front drill (`studies/2026-11-06-front-drill/`, draft PR #75), which supplies the cases and the scorer.*

**Question** (Jason's words, 2026-11-06 in the frontal trainer thread): "could we train 'first guess' fronts from this work?"; "what would be the agentic way to do this. not rules based"; then "sure" to a 50-case pilot.

**What it is:** Claude plays the front drill. For each case it gets what a trainee gets (the same six panels as images: MSLP + thickness + 10 m barbs, imagery, 850 and 700 theta-e, 3 h pressure tendency, 10 m wind; the L and the stationary fronts given; the ring), plus a few look-up tools a forecaster does by eye, and it hands back cold, warm and occluded fronts as point lists with one line of reasoning per front. No trained weights: it reasons from the maps, with two or three worked examples (maps plus the analysed answer) from similar past cases.

**What would change if the answer is yes:** a first-guess front layer the analyst edits instead of drawing from scratch; later (not in this pilot, each needs Jason's go) a front overlay on the marine wind page and a "beat the first guess" score in the drill.

**Truth:** the Unified Surface Analysis as coded by WPC (CODSUS), the drill's own truth. Scored by the drill's own scorer (`page/app.js` `scoreCase`, run unchanged under node), so the agent is scored exactly like a forecaster: position full credit within 150 nm, none at 300 nm; type worth twice position; missed fronts cost most; only the case's system scored.

**Baselines to beat** (same cases, same scorer):
1. Thermal front parameter (TFP) on 850 theta-e: the textbook objective front finder. Lines where TFP crosses zero with a strong enough gradient, typed cold/warm by the 10 m wind blowing across the line toward cold or warm air, occluded where the 700 theta-e ridge reaches the low. Thresholds tuned on the deck minus the 50 test cases.
2. Persistence: the analysed fronts from 6 h earlier, moved with the low. Shown for reference; the agent does not see the earlier analysis (a forecast-hour first guess will not have one).

**Win means** (decided now): the agent's mean drill score beats TFP by 10 points or more (0-100 scale) on the 50 test cases, paired by case with a bootstrap 90% interval above zero; and it costs under $0.50 per analysis. If it wins, propose running all 522 and a forecast-hour test; if it ties or loses, report where it went wrong (type, position, missed) and stop.

**Cases:** 50 drawn at random (seed fixed) from the 522-case deck, 30 N Atlantic and 20 N Pacific, all from the held-out weeks (`rk.cases.held_out`: 78 of the 522 cases, 54 Atlantic and 24 Pacific). TFP thresholds and the agent prompt are tuned only on the other 444. Worked examples come only from tune weeks and never from the same low within 48 h of a test case (the same storm would hand over the answer).

**Agent:** Claude Opus 5.5 through the Claude API (Python SDK, adaptive thinking, effort medium; Sonnet 5.5 played on the same 50 for a cost comparison). Tools: `cross_section(start, end)` (850 theta-e, 10 m wind direction and speed, MSLP along a line), `pressure_troughs()` (kinks in the isobars inside the ring), `gradient_max(lat, lon, radius)` (strongest theta-e gradient near a point), `submit_fronts(...)`. A cap of 12 tool turns per case. Points it gives are curved and scored exactly as a trainee's taps.

**Data:** none new. Panels are drawn from the deck's own fields (`deck/<id>.bin`, `_am.jpg` / `_ir.jpg`); no GFS, GOES or ASCAT pull. Claude API spend for the pilot: estimated $0.20-0.40 per case on Opus 5.5 (six panel images ~4k tokens, two worked examples ~8k, cached; ~8 turns; thinking ~5-8k output tokens), so about $15-20 for 50 cases, about $25-30 with the Sonnet comparison. Hard cap $40.

**Run as done (Jason 2026-11-06: "why do we need a key. can you run the test"):** the pilot ran inside the Claude Code session with no API key. Ten Claude agents played five cases each from blind case folders (panels, given lows and stationary fronts, worked examples, tool) and were told to open nothing else. A scripted API run (key as `ANTHROPIC_API_KEY`) is the step after, for exact cost and repeat runs.

**Reused / new:**
- Reused: the drill deck and manifest, `page/app.js` scoring (loaded under node, not copied), `rk.fronts.smooth`, `rk.diag.theta_e`, the drill's box geometry.
- New in `rk/`: `rk/frontfind.py` (TFP front finder on a lat-lon box, with a test), so any later study can use it.
- New here: `panels.py` (deck case -> PNG panels), `agent.py` (tool loop), `score.py` (node bridge to `scoreCase`), `run.py`.

**Methods tried, simplest first:** each must beat the one before it to stay in.
1. TFP baseline.
2. Agent, maps only (zero-shot).
3. Agent + worked examples from similar cases (similar = same basin, nearest low pressure and front-type count).
4. Agent + tools.
The full agent is 4; 2 and 3 run on the same 50 only if 4 beats TFP, to say what the examples and tools add.

**Known traps:** same-storm leakage across 6 h neighbours (handled above); the coded analysis draws Shapiro-Keyser bent-back fronts as occluded or warm, so type errors there are partly truth noise; the deck boxes are 0.5 deg, coarser than the analyst's maps; a 50-case score has a wide interval, so the verdict is "worth scaling", not "operational".

**Out of scope:** trained models (CNN on older CODSUS, needs a big pull and Jason's go), forecast hours, troughs, highs, publishing anything.
