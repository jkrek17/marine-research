"""Forecaster briefing for the 2026-11-16 MSLP blend study: 2 pages + appendix (worked cases) + backup (tables).

Sources (every number in the brief): findings.md and results/*.csv in this folder. Where a number is typed into the
text it is asserted against the CSV below (check() calls), with the file named in a comment:
  by_lead_raw2.csv   mean-analysis truth, both basins, all winter weeks: position, median, RMSE, strong-low bias, false lows
  win_rule.csv       member vote minus ECMWF position (12Z cases): 34 / 67 / 64 km
  diffs_vs_ifs_vote_eq.csv / win_rule.csv  vote and ECMWF position on the same 12Z cases
  strong_depth.csv   vote strong-low bias (12Z)
  outlier_risk.csv   share of drops where the dropped run was closest
  noise_floor.csv    GFS analysis vs IFS analysis
  partb_circles.csv, partb_range.csv, partb_alt.csv, partb_params.json   Part B (day 5-7 probability)
  worked_cases_detail.csv, worked_cases.csv   the worked cases (make_figs.py, select_cases.py)
  findings.md        Brier skill (+0.21/+0.17/+0.10), warp effect (within 5 km), depth fix (about 2 hPa),
                     circle radii (391/751, 440/764, 480/777), support circles (231-326 vs 634-642 km), 7-13% drops (X = 300 km)
Outputs: figs/brief_charts.png, report.md, and the PDF (default /mnt/project-files/mslp-blend-d7/mslp-blend-briefing.pdf).
Usage: python3 make_brief.py [--pdf PATH]
"""
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, Image,
                                PageBreak, KeepTogether, HRFlowable)

RES = HERE / "results"
FIGS = HERE / "figs"
CREAM, NAVY, OX, SAND, MID = "#F6F0E1", "#16294D", "#6B1D2A", "#E8DFC8", "#6F7A93"
DEFAULT_PDF = "/mnt/project-files/mslp-blend-d7/mslp-blend-briefing.pdf"
LEADS = (24, 48, 72, 96, 120, 144, 168)

# ------------------------------------------------------------------ data
B = pd.read_csv(RES / "by_lead_raw2.csv")
B = B[(B.truth == "mean") & (B.basin == "all")].set_index(["entry", "lead"])


def b(entry, lead, col):
    return float(B.loc[(entry, lead), col])


WR = pd.read_csv(RES / "win_rule.csv").set_index(["entry", "lead"])
VOTE = pd.read_csv(RES / "diffs_vs_ifs.csv")
VOTE = VOTE[(VOTE.entry == "vote") & (VOTE.truth == "mean") & (VOTE.basin == "all") & (VOTE.subset == "main")].set_index("lead")
SD = pd.read_csv(RES / "strong_depth.csv").set_index(["entry", "lead"])
OR = pd.read_csv(RES / "outlier_risk.csv")
NF = pd.read_csv(RES / "noise_floor.csv")
CIRC = pd.read_csv(RES / "partb_circles.csv")
RNG = pd.read_csv(RES / "partb_range.csv")
ALT = pd.read_csv(RES / "partb_alt.csv")
PP = {int(k): v for k, v in json.load(open(RES / "partb_params.json")).items()}
CASES = pd.read_csv(RES / "worked_cases_detail.csv")


def check(label, got, want, tol=0.5):
    if abs(got - want) > tol:
        raise SystemExit("MISMATCH %s: csv %.2f vs text %.2f" % (label, got, want))


# numbers typed in the text, checked against the CSVs (file in the comment)
check("ECMWF day 4 pos", b("ifs", 96, "pos_km"), 285)                      # by_lead_raw2.csv, findings.md table
check("GFS day 4 pos", b("gfs", 96, "pos_km"), 300)
check("ECMWF day 7 pos", b("ifs", 168, "pos_km"), 439)
check("blend strong bias d7", b("m_gi", 168, "strong_bias"), 11.7, 0.06)   # findings.md
check("ECMWF strong bias d7", b("ifs", 168, "strong_bias"), 8.0, 0.06)
check("GFS strong bias d7", b("gfs", 168, "strong_bias"), 10.0, 0.06)
check("extra fill d7 ~4", b("m_gi", 168, "strong_bias") - b("ifs", 168, "strong_bias"), 4.0, 0.5)
check("vote strong bias d7", float(SD.loc[("vote", 168), "strong_bias"]), 7.6, 0.06)     # strong_depth.csv
for lead in LEADS:   # blend beats both inputs on RMSE at every lead
    assert b("m_gi", lead, "rmse") < b("ifs", lead, "rmse") and b("m_gi", lead, "rmse") < b("gfs", lead, "rmse")
# GFS+ECMWF mean vs ECMWF position: ties at day 1, 6, 7; 9-20 km worse at days 2-5
dgi = {l: b("m_gi", l, "pos_km") - b("ifs", l, "pos_km") for l in LEADS}
assert all(abs(dgi[l]) < 9 for l in (24, 144, 168)) and all(9 <= dgi[l] <= 20.5 for l in (48, 72, 96, 120)), dgi
# ECMWF false lows 0.5-2.5, GFS+ECMWF mean 0.2-1.75
assert round(b("ifs", 24, "false_per_map"), 1) == 0.5 and round(b("ifs", 168, "false_per_map"), 1) == 2.5
assert round(b("m_gi", 24, "false_per_map"), 1) == 0.2 and round(b("m_gi", 168, "false_per_map"), 2) == 1.75
# AIFS vs GFS+ECMWF mean on RMSE: closer from day 2 on, worse at day 1
AIFS_GAP = [b("m_gi", l, "rmse") - b("aifs", l, "rmse") for l in LEADS]
assert AIFS_GAP[0] < 0 and all(g > 0 for g in AIFS_GAP[1:])
AIFS_LO, AIFS_HI = min(AIFS_GAP[1:]), max(AIFS_GAP[1:])
# day 1-2 depend on the truth analysis (by_lead_raw2.csv, truth rows)
BT = pd.read_csv(RES / "by_lead_raw2.csv"); BT = BT[BT.basin == "all"].set_index(["truth", "entry", "lead"])
check("GFS beats ECMWF vs GFS analysis d1", BT.loc[("gfs", "ifs", 24), "pos_km"] - BT.loc[("gfs", "gfs", 24), "pos_km"], 22, 1.0)
check("GFS beats ECMWF vs GFS analysis d2", BT.loc[("gfs", "ifs", 48), "pos_km"] - BT.loc[("gfs", "gfs", 48), "pos_km"], 11, 1.0)
check("ECMWF beats GFS vs IFS analysis d1", BT.loc[("ifs", "gfs", 24), "pos_km"] - BT.loc[("ifs", "ifs", 24), "pos_km"], 50, 1.5)
check("vote d5", -WR.loc[("vote", 120), "dpos"], 34, 0.5)
check("vote d6", -WR.loc[("vote", 144), "dpos"], 67, 0.5)
check("vote d7", -WR.loc[("vote", 168), "dpos"], 64, 0.5)
check("vote false lows d5", WR.loc[("vote", 120), "dfalse"], 0.18, 0.006)
check("vote false lows d7", WR.loc[("vote", 168), "dfalse"], 0.19, 0.01)
check("noise floor mean pos", float(NF[(NF.lead == 24)].pos_km.iloc[0]), 130, 1.0)   # noise_floor.csv (findings.md: 119-130)
od = OR[(OR.cand == "od") & (OR.setting == "X=300") & (OR.basin == "all") & (OR.model == "all")].set_index("lead")
assert 0.07 <= od.share_closest.min() < 0.075 and 0.13 < od.share_closest.max() <= 0.135     # outlier_risk.csv: 7-13%
OD_LOSS = [b("od", l, "pos_km") - b("ifs", l, "pos_km") for l in LEADS]
check("outlier-drop loses to ECMWF, min", min(OD_LOSS), 69, 1.0)
check("outlier-drop loses to ECMWF, max", max(OD_LOSS), 115, 1.0)
check("ensemble means cost ~60 km at day 1", b("al", 24, "pos_km") - b("m_gi", 24, "pos_km"), 63, 3.0)
check("warp within 5 km (warp_effect.csv, over open water excluded)", float(pd.read_csv(RES / "warp_effect.csv").query("not over_water_only").dpos_km.abs().max()), 5, 5.0)
a_pos = ALT[(ALT.subset == "winter") & (ALT.truth == "mean") & (ALT.basin == "both") & (ALT.kind == "pos")].set_index("lead")
ci = CIRC[(CIRC.subset == "winter") & (CIRC.truth == "mean") & (CIRC.basin == "both")].set_index("lead")
rg = RNG[(RNG.subset == "winter") & (RNG.truth == "mean") & (RNG.basin == "both") & (RNG.direction == "forecast_low")].set_index("lead")
check("circle 50 d5", PP[120]["r50"], 391, 1.0)
check("circle 80 d7", PP[168]["r80"], 777, 1.0)
check("high-support circle d5", PP[120]["rt"][2][0], 231, 1.0)
check("high-support circle d7", PP[168]["rt"][2][0], 327, 1.0)
check("range d6 cover", 100 * rg.loc[144, "cov80"], 84, 0.5)
check("range width d5", rg.loc[120, "width80"], 15, 0.5)
check("range width d7", rg.loc[168, "width80"], 20, 0.5)


def r1(x):   # round half up to 1 decimal
    import math
    return math.floor(x * 10 + 0.5 + 0.06) / 10


# existence chance runs low in winter: mean forecast chance vs frequency (partb_verdict.csv), 4 to 6 points
PV = pd.read_csv(RES / "partb_verdict.csv")
PV = PV[(PV.subset == "winter") & (PV["product"] == "exist") & (PV.basin == "both")].set_index("lead")
EX_LOW = [100 * (PV.loc[l, "freq"] - PV.loc[l, "mean_p"]) for l in (120, 144, 168)]
assert 3.5 <= min(EX_LOW) and max(EX_LOW) <= 6.5, EX_LOW


# ------------------------------------------------------------------ charts


def charts(path):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5})
    fig, ax = plt.subplots(1, 2, figsize=(7.35, 1.8), dpi=200)
    fig.patch.set_facecolor(CREAM)
    d = [l / 24 for l in LEADS]
    for a in ax:
        a.set_facecolor("#FBF8EF")
        for s in ("top", "right"):
            a.spines[s].set_visible(False)
        for s in ("left", "bottom"):
            a.spines[s].set_color(NAVY)
        a.tick_params(colors=NAVY, labelsize=7)
        a.grid(axis="y", color=SAND, lw=0.6)
        a.set_xticks(range(1, 8))
        a.set_xlabel("forecast day", color=NAVY, fontsize=7.5)
    p = ax[0]
    p.plot(d, [b("ifs", l, "pos_km") for l in LEADS], color=NAVY, lw=1.8, label="ECMWF")
    p.plot(d, [b("gfs", l, "pos_km") for l in LEADS], color=MID, lw=1.3, ls="--", label="GFS")
    p.plot(d, [b("m_gi", l, "pos_km") for l in LEADS], color=OX, lw=1.5, label="GFS+ECMWF mean")
    p.plot([5, 6, 7], [VOTE.loc[l, "pos_c"] for l in (120, 144, 168)], color=OX, marker="D", ms=4.5, lw=0, label="member vote (12Z)")
    p.plot([5, 6, 7], [VOTE.loc[l, "pos_ref"] for l in (120, 144, 168)], color=NAVY, marker="D", mfc="none", ms=4.5, lw=0, label="ECMWF, same 12Z cases")
    p.set_ylabel("mean position error, km", color=NAVY, fontsize=7.5)
    p.set_title("Position: ECMWF best to day 4, vote day 5-7", loc="left", fontsize=7.8, color=NAVY, fontweight="bold")
    p.legend(frameon=False, fontsize=6.3, labelcolor=NAVY, loc="upper left")
    q = ax[1]
    q.plot(d, [b("ifs", l, "strong_bias") for l in LEADS], color=NAVY, lw=1.8, label="ECMWF")
    q.plot(d, [b("gfs", l, "strong_bias") for l in LEADS], color=MID, lw=1.3, ls="--", label="GFS")
    q.plot(d, [b("m_gi", l, "strong_bias") for l in LEADS], color=OX, lw=1.5, label="GFS+ECMWF mean")
    q.plot(d, [b("ens", l, "strong_bias") for l in LEADS], color="#9A9585", lw=1.1, ls=":", label="ECMWF ensemble mean")
    q.set_ylabel("too shallow, hPa (lows < 980)", color=NAVY, fontsize=7.5)
    q.set_title("Depth: the means fill lows most", loc="left", fontsize=7.8, color=NAVY, fontweight="bold")
    q.legend(frameon=False, fontsize=6.3, labelcolor=NAVY, loc="upper left")
    fig.tight_layout(pad=0.6, w_pad=1.6)
    fig.savefig(path, facecolor=CREAM)
    plt.close(fig)


def chart_pos(path):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 7.5})
    fig, p = plt.subplots(figsize=(4.4, 1.55), dpi=200)
    fig.patch.set_facecolor(CREAM)
    p.set_facecolor("#FBF8EF")
    for sp in ("top", "right"):
        p.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        p.spines[sp].set_color(NAVY)
    p.tick_params(colors=NAVY, labelsize=7)
    p.grid(axis="y", color=SAND, lw=0.6)
    p.set_xticks(range(1, 8))
    p.set_xlabel("forecast day", color=NAVY, fontsize=7.5)
    d = [l / 24 for l in LEADS]
    p.plot(d, [b("ifs", l, "pos_km") for l in LEADS], color=NAVY, lw=1.8, label="ECMWF")
    p.plot(d, [b("gfs", l, "pos_km") for l in LEADS], color=MID, lw=1.3, ls="--", label="GFS")
    p.plot(d, [b("m_gi", l, "pos_km") for l in LEADS], color=OX, lw=1.5, label="GFS+ECMWF mean")
    p.plot([5, 6, 7], [VOTE.loc[l, "pos_c"] for l in (120, 144, 168)], color=OX, marker="D", ms=4.5, lw=0, label="member vote (12Z)")
    p.plot([5, 6, 7], [VOTE.loc[l, "pos_ref"] for l in (120, 144, 168)], color=NAVY, marker="D", mfc="none", ms=4.5, lw=0, label="ECMWF, same 12Z cases")
    p.set_ylabel("mean position error, km", color=NAVY, fontsize=7.5)
    p.set_title("Position: ECMWF best to day 4, vote day 5-7", loc="left", fontsize=7.8, color=NAVY, fontweight="bold")
    p.legend(frameon=False, fontsize=6.3, labelcolor=NAVY, loc="upper left")
    fig.tight_layout(pad=0.6)
    fig.savefig(path, facecolor=CREAM)
    plt.close(fig)


# ------------------------------------------------------------------ text (shared by PDF and report.md)
TITLE = "Best MSLP forecast to day 7: where to lean, how to show it"
SUB = ("Briefing for Jason, OPC marine desk, 16 November 2026. Winter 2025-26 (1 November to 31 March), North Atlantic and "
       "North Pacific, 00Z and 12Z runs. Truth: the mean of the GFS and IFS analyses. “ECMWF” is the IFS deterministic.")
BOTTOM = [
    "Lean on ECMWF, with GFS close, to place lows out to day 4. Draw the isobars from the GFS+ECMWF mean, but take each low’s depth from the "
    "runs’ own depths, not from the blended field, which fills strong lows. From day 5 the member vote places lows best, but it needs members that are not on AWIPS.",
    "Converging the field on the best low adds almost nothing, and the blend left after dropping the odd model loses to ECMWF. Both worries are real: even ECMWF is %d km out on the average low by day 7 "
    "(a missed low counts as 1000 km), and every source is shallow on strong lows at day 7 (ECMWF %.1f, GFS %.1f hPa), so expect the real low to be several hPa deeper than any label."
    % (round(b("ifs", 168, "pos_km")), b("ifs", 168, "strong_bias"), b("gfs", 168, "strong_bias")),
]
AWIPS = [
    "Isobars from the GFS+ECMWF mean.",
    "Lows placed with ECMWF, GFS close behind.",
    "The day 5-7 member vote, with its chances, circles and depth range, needs ECMWF ENS and AIFS ENS members. Those are not on AWIPS.",
    "A GEFS-only vote was not tested. CMC and UKMET were not tested either: they are not in the store.",
]
KPS = [
    ("Days 1-4: lean on ECMWF, with GFS close behind. ECMWF’s mean error is %d km at day 4 (GFS %d km)." % (round(b("ifs", 96, "pos_km")), round(b("gfs", 96, "pos_km"))),
     "Days 1-2 are a tie: against the GFS analysis GFS wins by 22 and 11 km, against the ECMWF analysis ECMWF wins by about 50 km. "
     "ECMWF is clearly ahead from day 3. It draws more lows (0.5 to 2.5 false per map, against 0.2 to 1.75 for the GFS+ECMWF mean), and a missed low counts as 1000 km. "
     "The GFS+ECMWF mean ties ECMWF at day 1, 6 and 7 and is 9 to 20 km worse at days 2 to 5.",
     None),
    ("The GFS+ECMWF mean gives the best isobars of the AWIPS runs but fills strong lows, about %d hPa more than ECMWF by day 7." % round(b("m_gi", 168, "strong_bias") - b("ifs", 168, "strong_bias")),
     "It is closer to the analysis than GFS or ECMWF at every lead. AIFS alone is closer than the mean from day 2 on (by %.2f to %.2f hPa) but worse at day 1 (%.2f against %.2f), and it is not on AWIPS. "
     "A depth fix in the field recovers only 0.2 to 0.8 hPa on the two-run mean (about 2 hPa on blends of 3 or more runs), so label instead. "
     "Every source is shallow on strong lows at day 7 (ECMWF +%.1f, GFS +%.1f, vote +%.1f hPa; a missed low is charged the field value at its centre). "
     "No depth-threshold chance (990, 980, 970 hPa) is ready to show: the checks failed." % (AIFS_LO, AIFS_HI, b("aifs", 24, "rmse"), b("m_gi", 24, "rmse"), b("ifs", 168, "strong_bias"), b("gfs", 168, "strong_bias"), float(SD.loc[("vote", 168), "strong_bias"])),
     None),
    ("Converging on the best low and fitting the field around it is not worth it: it moves the mean low position by under 5 km.",
     "Pulling each run’s low to the consensus spot before averaging leaves the lows within 5 km of the plain mean. Ensemble means in the blend lower the field error but cost about 60 km "
     "in position, because they wash out the weaker lows. Keep the simple mean.",
     None),
    ("Dropping the model that drifts from the consensus is usually the right call: the dropped model was the closest to the analysis only %d-%d%% of the time." % (round(100 * od.share_closest.min()), round(100 * od.share_closest.max())),
     "But the blend left behind still contains the ensemble means and loses to ECMWF by %d to %d km. Tested on GFS, ECMWF, AIFS and AI-GFS only. "
     "Weighting by recent skill is no help either (Recent MSLP skill study, 13 Oct 2026)." % (round(min(OD_LOSS)), round(max(OD_LOSS))),
     None),
    ("Days 5-7: the member vote likely places the lows best, %d to %d km closer than ECMWF, but this is likely, not proven." % (round(-WR.loc[("vote", 120), "dpos"]), round(-WR.loc[("vote", 144), "dpos"])),
     "It was chosen on overlapping weeks, so this is not a blind test (Day 5-7 pressure study, 16 Oct 2026, repeated on this winter). It draws about %.2f more false lows per map than ECMWF, "
     "and Pacific day 5 is a tie. It uses GEFS, ECMWF ENS and AIFS ENS members, with the GFS, ECMWF and AIFS runs as light voters." % WR.loc[("vote", 120), "dfalse"],
     None),
]
SAMPLE = "Sample: one winter, 23 weeks, both basins, 00Z and 12Z runs; the member vote is 12Z only."

PROB_HEAD = ["Day 5-7 member vote, winter, 12Z", "Day 5", "Day 6", "Day 7"]
PROB_ROWS = [
    ["Chance the low exists: better than always forecasting the average rate by (0 = no better)", "0.21", "0.17", "0.10"],
    ["10-90% depth range holds the analysed depth (aim 80%)"] + ["%d%%" % round(100 * rg.loc[l, "cov80"]) for l in (120, 144, 168)],
    ["50% position circle: radius (share that verified)"] + ["%d km (%d%%)" % (round(PP[l]["r50"]), round(100 * ci.loc[l, "cov50"])) for l in (120, 144, 168)],
    ["80% position circle: radius (share that verified)"] + ["%d km (%d%%)" % (round(PP[l]["r80"]), round(100 * ci.loc[l, "cov80"])) for l in (120, 144, 168)],
    ["Alternative low (at least 20% of members, over 300 km away): shown / right"] +
    ["%d%% / %d%%" % (round(100 * a_pos.loc[l, "alt_per_low"]), round(100 * a_pos.loc[l, "verified"])) for l in (120, 144, 168)],
]
PROB_NOTES = [
    "Chance it exists is reliable at day 5; at day 6-7 the top bins miss; in winter it runs 4 to 6 points low. The analysis is 1.0 to 1.7 hPa deeper than the vote median; ranges are wide (15 to 20 hPa).",
    "50% circle: 231 to 327 km for lows most members carry, 634 to 642 km for lows few carry. A far-away alternative is right 1 time in 3 (chance 7-9%).",
]
DISPLAY = [
    "Plain isobars every 4 hPa from the GFS+ECMWF mean, with G and E marks where GFS and ECMWF put their own lows.",
    "Days 1-4: label each low with depth only, from the runs’ own depths. No range or chance was verified there.",
    "Days 5-7: label depth, 10-90% range and chance the low exists, “L 947 (936-974) 63%”, and draw a position circle sized by member support (solid 50%, dashed 80%). "
    "This needs members not on AWIPS. Leaving off lows under 30% chance is a guess to test.",
    "An alternative low only when at least 20% of members put one more than 300 km away (open diamond with its share).",
    "Depth-threshold chances (990, 980, 970 hPa) are left off because they failed their checks.",
    "A proposal only: mock-up screenshots first, nothing live until you agree (GFE: a normal MSLP grid, chances in a table).",
]
LIMITS = [
    "Position gaps under about 25 km cannot be told apart, and day 1-2 gaps sit inside the %d km average low-position difference between the GFS and IFS analyses." % round(float(NF[NF.lead == 24].pos_km.iloc[0]), -1),
    "Chance of a low deeper than 970 hPa shows no skill, and below 960 hPa there are too few lows to verify.",
    "Days 1-4 and 00Z have no stored members, so no probability there until a member pull (needs your go). AI-GFS has too few cases (158 runs) to choose.",
    "Pressure only, against the two analyses (no ERA5); wind is not tested here (Pressure to wind, 13 Oct 2026, found no gain).",
]

# worked cases chosen for the brief (page 2) and the appendix
BRIEF_CASES = ["natl-deep-2025-12-11", "npac-deep-2025-11-08", "natl-split-2026-01-27"]
APPX_CASES = ["npac-split-2026-02-02"]


def cr(cid):
    r = CASES[CASES.case == cid].iloc[0]
    return r


def case_title(cid):
    r = cr(cid)
    basin = "North Atlantic" if r.basin == "natl" else "North Pacific"
    kind = ("deepest analysed low of %s" % pd.Timestamp(r.valid.replace("Z", ":00")).strftime("%B")) if r.kind == "deep" else "largest GFS-ECMWF split at day 5"
    return "%s, %s. Day 5 from %s, valid %s." % (basin, kind, pd.Timestamp(r.cycle.replace("Z", ":00")).strftime("%d %b %Y %HZ"),
                                                 pd.Timestamp(r.valid.replace("Z", ":00")).strftime("%d %b %Y %HZ"))


def case_text(cid):
    r = cr(cid)
    f = lambda x: "%d" % round(x)
    t = ("Analysis %s hPa; lowest pressure near it: GFS %s, ECMWF %s, GFS+ECMWF mean %s, ECMWF ensemble mean %s. " %
         (f(r.an_hpa), f(r.gfs_hpa), f(r.ifs_hpa), f(r.gi_hpa), f(r.ens_hpa)))
    if r.members and not pd.isna(r.get("vote_hpa")):
        t += ("Vote: L %s (%s-%s), %d%% chance, %s km off; analysis %s the 50%% circle, %s the range." %
              (f(r.vote_hpa), f(r.vote_q10), f(r.vote_q90), round(100 * r.vote_chance), f(r.vote_dist_km),
               "inside" if r.in50 else "outside", "inside" if r.an_in_range else "outside"))
    return t


_t3 = pd.read_csv(RES / "worked_split_top3.csv")
_t3 = _t3[(_t3.basin == "natl") & (_t3.cycle == "2026-01-22 12:00:00")].iloc[0]


def _pos(lat, lon):
    return "%.1fN %d%s" % (lat, round(360 - lon) if lon > 180 else round(lon), "W" if lon > 180 else "E")


SPLIT_POS = (_pos(_t3.gfs_lat, _t3.gfs_lon), _pos(_t3.ifs_lat, _t3.ifs_lon))
CASE_NOTES = {
    "natl-deep-2025-12-11": "The deepest storm of the winter. The vote missed it (%d km off, %d hPa shallow) and so did ECMWF (%d hPa, %d km off); only GFS had it." % (
        round(cr("natl-deep-2025-12-11").vote_dist_km), round(cr("natl-deep-2025-12-11").vote_hpa - cr("natl-deep-2025-12-11").an_hpa),
        round(cr("natl-deep-2025-12-11").ifs_hpa), round(cr("natl-deep-2025-12-11").ifs_dist_km)),
    "npac-deep-2025-11-08": "Good: vote low, circle and range all caught it; the ensemble mean filled it by about 20 hPa.",
    "natl-split-2026-01-27": "GFS and ECMWF put their lows %d km apart (GFS %s, ECMWF %s); the vote settled near the analysed low but was %d hPa too deep." % (
        round(float(cr("natl-split-2026-01-27").split_km), -1), SPLIT_POS[0], SPLIT_POS[1],
        round(cr("natl-split-2026-01-27").an_hpa - cr("natl-split-2026-01-27").vote_hpa)),
}
_V = CASES[CASES.members & CASES.vote_hpa.notna()]
OUT50, NVOTE = int((~_V.in50.astype(bool)).sum()), len(_V)
CASE_SUMMARY = ("Worked cases (page 2): of the %d with a member vote, the analysed low was outside the 50%% circle in %d; "
                "the deepest storm of the winter (11 Dec, 937 hPa) was missed by the vote and by ECMWF." % (NVOTE, OUT50))


# ------------------------------------------------------------------ PDF
PW, PH = letter
M = 0.6 * inch


def bg(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(HexColor(CREAM))
    canvas.rect(0, 0, PW, PH, stroke=0, fill=1)
    canvas.setFillColor(HexColor(NAVY))
    canvas.rect(0, PH - 0.22 * inch, PW, 0.22 * inch, stroke=0, fill=1)
    canvas.setFillColor(HexColor(OX))
    canvas.rect(0, PH - 0.25 * inch, PW, 0.03 * inch, stroke=0, fill=1)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(HexColor(MID))
    label = {1: "Brief, page 1 of 2", 2: "Brief, page 2 of 2", 3: "Appendix: worked cases", 4: "Backup: tables"}.get(doc.page, "continued")
    canvas.drawString(M, 0.36 * inch, "MSLP to day 7 · marine desk briefing · 16 Nov 2026 · " + label)
    canvas.restoreState()


def styles():
    s = {}
    s["title"] = ParagraphStyle("title", fontName="Times-Bold", fontSize=17.5, leading=20, textColor=HexColor(NAVY), spaceAfter=3)
    s["sub"] = ParagraphStyle("sub", fontName="Helvetica", fontSize=7.8, leading=9.8, textColor=HexColor(MID), spaceAfter=6)
    s["h"] = ParagraphStyle("h", fontName="Times-Bold", fontSize=11.5, leading=13, textColor=HexColor(OX), spaceBefore=4, spaceAfter=2)
    s["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=8.6, leading=10.8, textColor=HexColor(NAVY), alignment=TA_LEFT)
    s["bl"] = ParagraphStyle("bl", parent=s["body"], fontSize=9.0, leading=11.2, spaceAfter=2)
    s["kp"] = ParagraphStyle("kp", parent=s["body"], fontName="Helvetica-Bold", fontSize=8.9, leading=10.6)
    s["so"] = ParagraphStyle("so", parent=s["body"], fontSize=8.1, leading=9.8)
    s["tag"] = ParagraphStyle("tag", parent=s["body"], fontSize=7.2, leading=8.8, textColor=HexColor(OX))
    s["bul"] = ParagraphStyle("bul", parent=s["body"], leftIndent=9, bulletIndent=0, fontSize=8.4, leading=10.4, spaceAfter=1.2)
    s["cap"] = ParagraphStyle("cap", parent=s["body"], fontSize=7.6, leading=9.3)
    s["capb"] = ParagraphStyle("capb", parent=s["cap"], fontName="Helvetica-Bold")
    s["cell"] = ParagraphStyle("cell", parent=s["body"], fontSize=7.4, leading=8.8)
    s["cellb"] = ParagraphStyle("cellb", parent=s["cell"], fontName="Helvetica-Bold", textColor=HexColor(CREAM))
    s["small"] = ParagraphStyle("small", parent=s["body"], fontSize=7.2, leading=8.8, textColor=HexColor(MID))
    return s


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tbl(rows, widths, S, head=True, first_left=True, fs=7.4):
    data = [[Paragraph(esc(str(c)), S["cellb"] if (head and i == 0) else S["cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("LINEBELOW", (0, 0), (-1, -1), 0.25, HexColor(SAND))]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), HexColor(NAVY))]
    t.setStyle(TableStyle(st))
    return t


def case_block(cid, S, width, note=True):
    from PIL import Image as PI
    pw, ph = PI.open(FIGS / "brief" / f"{cid}.png").size
    img = Image(str(FIGS / "brief" / f"{cid}.png"), width=width, height=width * ph / pw)
    parts = [Paragraph(esc(case_title(cid)), S["capb"]), Spacer(1, 2), img, Paragraph(esc(case_text(cid)), S["cap"])]
    if note and cid in CASE_NOTES:
        parts.append(Paragraph("<font color='%s'>%s</font>" % (OX, esc(CASE_NOTES[cid])), S["cap"]))
    parts.append(Spacer(1, 4))
    return KeepTogether(parts)


def build_pdf(path):
    S = styles()
    W = PW - 2 * M
    doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=M, rightMargin=M, topMargin=0.42 * inch, bottomMargin=0.5 * inch,
                          title=TITLE, author="Marine desk research")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(M, 0.5 * inch, W, PH - 0.92 * inch, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=bg)])
    E = []
    # ---- page 1
    E += [Paragraph(esc(TITLE), S["title"]), Paragraph(esc(SUB), S["sub"])]
    box = Table([[[Paragraph("<b>Bottom line</b>", ParagraphStyle("x", parent=S["bl"], textColor=HexColor(OX), fontName="Helvetica-Bold"))] +
                  [Paragraph(esc(t), S["bl"]) for t in BOTTOM]]], colWidths=[W])
    box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HexColor("#EFE6CF")), ("LINEBEFORE", (0, 0), (0, -1), 3, HexColor(OX)),
                             ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    awx = [Paragraph("<b>What works on AWIPS today</b>", ParagraphStyle("y", parent=S["so"], textColor=HexColor(OX), fontName="Helvetica-Bold"))] + \
          [Paragraph(esc(t), S["bul"], bulletText="\u2022") for t in AWIPS]
    ab = Table([[Image(str(FIGS / "brief_position.png"), width=4.3 * inch, height=4.3 * inch * 1.55 / 4.4), awx]], colWidths=[4.4 * inch, W - 4.4 * inch])
    ab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("BOX", (1, 0), (1, 0), 0.8, HexColor(NAVY)), ("LEFTPADDING", (1, 0), (1, 0), 6), ("TOPPADDING", (1, 0), (1, 0), 3)]))
    E += [box, Spacer(1, 4), ab, Spacer(1, 1)]
    E += [Paragraph("Both basins, all winter weeks, mean analysis as truth. Open diamonds: ECMWF on the 12Z cases the vote was scored on. Depth table: last page.", S["small"]), Spacer(1, 3)]
    E += [Paragraph("Five key points", S["h"])]
    for i, (head, so, tag) in enumerate(KPS, 1):
        row = Table([[Paragraph("<font color='%s' size=15><b>%d</b></font>" % (OX, i), S["body"]),
                      [Paragraph(esc(head), S["kp"]), Paragraph(esc(so), S["so"])]]],
                    colWidths=[0.28 * inch, W - 0.28 * inch])
        row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                                 ("LINEBELOW", (0, 0), (-1, -1), 0.25, HexColor(SAND))]))
        E.append(row)
    E += [Paragraph("What probability says at day 5-7", S["h"])]
    pt = tbl([PROB_HEAD] + PROB_ROWS, [3.5 * inch, 1.2 * inch, 1.2 * inch, W - 5.9 * inch], S)
    E += [pt, Spacer(1, 2)]
    for n in PROB_NOTES:
        E.append(Paragraph(esc(n), S["bul"], bulletText="\u2022"))
    E += [Paragraph(esc(SAMPLE + " " + CASE_SUMMARY), S["so"])]
    E.append(PageBreak())
    # ---- page 2
    E += [Paragraph("How to show it (proposal)", S["h"])]
    for n in DISPLAY:
        E.append(Paragraph(esc(n), S["bul"], bulletText="•"))
    E += [Paragraph("Three worked cases (day 5, 12Z run)", S["h"]),
          Paragraph("Left: ECMWF ensemble mean, member lows as dots. Middle: the proposed display. Right: the analysis, vote lows as rings. Three maps show how it reads; they settle nothing.", S["small"]), Spacer(1, 2)]
    for cid in BRIEF_CASES:
        E.append(case_block(cid, S, W))
    E += [Paragraph("What this sample cannot settle", S["h"])]
    for n in LIMITS:
        E.append(Paragraph(esc(n), S["bul"], bulletText="•"))
    E.append(PageBreak())
    # ---- appendix
    E += [Paragraph("Appendix: the proposed display at full width, and all worked cases", S["h"]),
          Paragraph("11 Dec 2025 case (page 2, first case): the GFS+ECMWF mean with the vote low, its 50% and 80% circles, G and E marks, and the analysed low (star).", S["small"]),
          Image(str(FIGS / "brief" / "natl-deep-2025-12-11_display.png"), width=W * 0.92, height=W * 0.92 * 3.7 / 7.3), Spacer(1, 3),
          Paragraph("Chosen by the study’s rule before scoring: the deepest analysed low per month (November to March) per basin, and the largest GFS-ECMWF split at day 5 per basin "
                    "(both runs deeper than 985 hPa at the low, within 1500 km of each other). Cases from 00Z runs have no stored members.", S["small"]), Spacer(1, 3)]
    rows = [["Case", "Valid", "Analysis", "GFS", "ECMWF", "GFS+ECMWF mean", "ECMWF ens mean", "Vote low (range) chance, km off"]]
    for _, r in CASES.iterrows():
        nm = ("N Atlantic" if r.basin == "natl" else "N Pacific") + (" deep" if r.kind == "deep" else " split")
        v = "no members (00Z)" if not r.members else ("L %d (%d-%d) %d%%, %d km" % (round(r.vote_hpa), round(r.vote_q10), round(r.vote_q90), round(100 * r.vote_chance), round(r.vote_dist_km)) if not pd.isna(r.get("vote_hpa")) else "none within 1000 km")
        g = lambda x: "" if pd.isna(x) else "%d" % round(x)
        rows.append([nm, r.valid, g(r.an_hpa), g(r.gfs_hpa), g(r.ifs_hpa), g(r.gi_hpa), g(r.ens_hpa), v])
    E += [tbl(rows, [0.95 * inch, 1.0 * inch, 0.55 * inch, 0.45 * inch, 0.55 * inch, 0.85 * inch, 0.8 * inch, W - 5.15 * inch], S),
          Paragraph("Pressures in hPa: the lowest value within 500 km of the analysed low, so a blend that smooths a low shows up as a higher number. "
                    "One Atlantic case (5 Nov 2025) has no day 5 fields before the study’s start and is left out of the maps.", S["small"]), Spacer(1, 4)]
    for cid in APPX_CASES:
        E.append(case_block(cid, S, W, note=False))
    E.append(PageBreak())
    # ---- backup tables
    E += [Paragraph("Backup: the tables behind the key points", S["h"]),
          Paragraph("Truth: mean of the GFS and IFS analyses; every sign was also checked against each analysis alone. Both basins, all winter weeks, %d cases at day 1 "
                    "(fewer at day 6-7 for GFS: 585). Position error: analysed lows under 1000 hPa; a miss counts 1000 km. “Aligned blend” and “outlier-drop blend” "
                    "include the ensemble means." % int(b("ifs", 24, "n_cases")), S["small"]), Spacer(1, 3)]
    hdr = ["", "Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"]
    cw = [2.5 * inch] + [(W - 2.5 * inch) / 7] * 7

    def line(label, entry, col, fmt="%.0f"):
        return [label] + [fmt % b(entry, l, col) for l in LEADS]
    E += [Paragraph("Mean low position error, km", S["h"])]
    T1 = [hdr, line("ECMWF", "ifs", "pos_km"), line("GFS", "gfs", "pos_km"), line("GFS+ECMWF mean", "m_gi", "pos_km"), line("AIFS (not on AWIPS)", "aifs", "pos_km"),
          line("ECMWF ensemble mean", "ens", "pos_km"), line("GEFS mean", "gefs", "pos_km"), line("Aligned blend, all runs", "al", "pos_km"), line("Outlier-drop blend", "od", "pos_km"),
          ["Member vote (12Z cases only)", "", "", "", "", "%d" % round(VOTE.loc[120, "pos_c"]), "%d" % round(VOTE.loc[144, "pos_c"]), "%d" % round(VOTE.loc[168, "pos_c"])],
          ["ECMWF on those same cases", "", "", "", "", "%d" % round(VOTE.loc[120, "pos_ref"]), "%d" % round(VOTE.loc[144, "pos_ref"]), "%d" % round(VOTE.loc[168, "pos_ref"])],
          line("Median: ECMWF", "ifs", "pos_median_km"), line("Median: GFS+ECMWF mean", "m_gi", "pos_median_km")]
    E += [tbl(T1, cw, S)]
    E += [Paragraph("Whole-field pressure error (RMSE over open water), hPa", S["h"])]
    T2 = [hdr, line("ECMWF", "ifs", "rmse", "%.2f"), line("GFS", "gfs", "rmse", "%.2f"), line("GFS+ECMWF mean", "m_gi", "rmse", "%.2f"), line("GFS+ECMWF+AIFS mean", "m_gif", "rmse", "%.2f"),
          line("AIFS (not on AWIPS)", "aifs", "rmse", "%.2f"), line("ECMWF ensemble mean", "ens", "rmse", "%.2f"), line("Aligned blend, all runs", "al", "rmse", "%.2f")]
    E += [tbl(T2, cw, S)]
    E += [Paragraph("Strong lows (analysed deeper than 980 hPa): forecast minus analysed pressure, hPa (positive = too shallow)", S["h"])]
    T3 = [hdr, line("ECMWF", "ifs", "strong_bias", "%.1f"), line("GFS", "gfs", "strong_bias", "%.1f"), line("GFS+ECMWF mean", "m_gi", "strong_bias", "%.1f"),
          line("Aligned blend, all runs", "al", "strong_bias", "%.1f"), line("ECMWF ensemble mean", "ens", "strong_bias", "%.1f"),
          ["Member vote (12Z cases only)", "", "", "", "", "%.1f" % SD.loc[("vote", 120), "strong_bias"], "%.1f" % SD.loc[("vote", 144), "strong_bias"], "%.1f" % SD.loc[("vote", 168), "strong_bias"]]]
    E += [tbl(T3, cw, S)]
    E += [Paragraph("False lows per map (forecast low under 1000 hPa with no analysed low under 1005 hPa within 500 km)", S["h"])]
    T4 = [hdr, line("ECMWF", "ifs", "false_per_map", "%.2f"), line("GFS", "gfs", "false_per_map", "%.2f"), line("GFS+ECMWF mean", "m_gi", "false_per_map", "%.2f"),
          line("Aligned blend, all runs", "al", "false_per_map", "%.2f")]
    E += [tbl(T4, cw, S)]
    E += [Paragraph("Outlier drop: how often the dropped run was the closest to the analysed low (cut-off 300 km, all runs and basins)", S["h"])]
    o3 = OR[(OR.cand == "od") & (OR.setting == "X=300") & (OR.basin == "all") & (OR.model == "all")].set_index("lead")
    T5 = [hdr, ["Share of drops where the dropped run was closest"] + ["%d%%" % round(100 * o3.loc[l, "share_closest"]) for l in LEADS],
          ["Drops counted"] + ["%d" % o3.loc[l, "n_dropped"] for l in LEADS]]
    E += [tbl(T5, cw, S)]
    E += [Paragraph("Day 5-7 probability products by lead (winter, both basins, mean analysis)", S["h"])]
    T6 = [["", "Day 5", "Day 6", "Day 7"],
          ["Chance it exists: better than always forecasting the average rate by (0 = no better); winter / held-out weeks", "0.21 / 0.22", "0.17 / 0.19", "0.10 / 0.13"],
          ["10-90% depth range holds (aim 72-88%)"] + ["%d%%" % round(100 * rg.loc[l, "cov80"]) for l in (120, 144, 168)],
          ["Analysis deeper than the vote median, hPa: winter / whole year"] + ["%.1f / %.1f" % (r1(-rg.loc[l, "bias_hpa"]), r1(-PP[l]["e_med"])) for l in (120, 144, 168)],
          ["Existence chance too low by, points (winter)"] + ["%.0f" % x for x in EX_LOW],
          ["50% circle: radius, verified"] + ["%d km, %d%%" % (round(PP[l]["r50"]), round(100 * ci.loc[l, "cov50"])) for l in (120, 144, 168)],
          ["80% circle: radius, verified"] + ["%d km, %d%%" % (round(PP[l]["r80"]), round(100 * ci.loc[l, "cov80"])) for l in (120, 144, 168)],
          ["50% circle, lows most members carry / few carry"] + ["%d / %d km" % (round(PP[l]["rt"][2][0]), round(PP[l]["rt"][0][0])) for l in (120, 144, 168)],
          ["Alternative low (different position): shown / right / by chance"] + ["%.0f%% / %.0f%% / %.0f%%" % (100 * a_pos.loc[l, "alt_per_low"], 100 * a_pos.loc[l, "verified"], 100 * a_pos.loc[l, "placebo"]) for l in (120, 144, 168)]]
    E += [tbl(T6, [3.5 * inch, 1.2 * inch, 1.2 * inch, W - 5.9 * inch], S)]
    E += [Spacer(1, 3), Paragraph("Circle radii and the chance and range calibration were fitted on the earlier weeks; the shares that verified are from this winter.", S["small"])]
    doc.build(E)


# ------------------------------------------------------------------ report.md
def report_md(path):
    L = ["# %s" % TITLE, "", "*%s*" % SUB, "", "## Bottom line", ""]
    L += [t + "\n" for t in BOTTOM]
    L += ["## What works on AWIPS today", ""] + ["- " + t for t in AWIPS] + [""]
    L += ["![Position error and depth by lead](figs/brief_charts.png)", "", "## Five key points", ""]
    for i, (h, so, tag) in enumerate(KPS, 1):
        L += ["%d. **%s** %s" % (i, h, so)]
    L += ["", SAMPLE, "", CASE_SUMMARY, "", "## What probability says at day 5-7", "", "| " + " | ".join(PROB_HEAD) + " |", "|---|---|---|---|"]
    L += ["| " + " | ".join(r) + " |" for r in PROB_ROWS]
    L += [""] + ["- " + n for n in PROB_NOTES]
    L += ["", "## How to show it (proposal)", ""] + ["- " + n for n in DISPLAY]
    L += ["", "## Three worked cases (day 5, 12Z run)", "", "Left: ECMWF ensemble mean with each member's low (dots). Middle: the proposed display on the GFS+ECMWF mean. Right: the analysis, with the vote lows as open rings. Three maps show how the display reads; they settle nothing.", ""]
    for cid in BRIEF_CASES:
        L += ["**%s**" % case_title(cid), "", "![%s](figs/%s.png)" % (cid, cid), "", case_text(cid) + (" " + CASE_NOTES[cid] if cid in CASE_NOTES else ""), ""]
    L += ["## What this sample cannot settle", ""] + ["- " + n for n in LIMITS]
    L += ["", "## Appendix: worked cases", "", "Chosen by the study's rule before scoring: the deepest analysed low per month (November to March) per basin, and the largest GFS-ECMWF split at day 5 per basin. "
          "Pressures are the lowest value within 500 km of the analysed low (hPa).", "",
          "| Case | Valid | Analysis | GFS | ECMWF | GFS+ECMWF mean | ECMWF ens mean | Vote low (range) chance, km off | Map |", "|---|---|---|---|---|---|---|---|---|"]
    for _, r in CASES.iterrows():
        nm = ("N Atlantic" if r.basin == "natl" else "N Pacific") + (" deep" if r.kind == "deep" else " split")
        v = "no members (00Z)" if not r.members else ("L %d (%d-%d) %d%%, %d km" % (round(r.vote_hpa), round(r.vote_q10), round(r.vote_q90), round(100 * r.vote_chance), round(r.vote_dist_km)) if not pd.isna(r.get("vote_hpa")) else "none within 1000 km")
        g = lambda x: "" if pd.isna(x) else "%d" % round(x)
        L += ["| %s | %s | %s | %s | %s | %s | %s | %s | [png](figs/%s.png) |" % (nm, r.valid, g(r.an_hpa), g(r.gfs_hpa), g(r.ifs_hpa), g(r.gi_hpa), g(r.ens_hpa), v, r.case)]
    L += [""]
    for cid in APPX_CASES:
        L += ["**%s**" % case_title(cid), "", "![%s](figs/%s.png)" % (cid, cid), "", case_text(cid), ""]
    L += ["## Backup", "", "The tables behind the key points are on the last page of the PDF.", ""]
    Path(path).write_text("\n".join(L))


def main():
    pdf = DEFAULT_PDF
    if "--pdf" in sys.argv:
        pdf = sys.argv[sys.argv.index("--pdf") + 1]
    FIGS.mkdir(exist_ok=True)
    charts(FIGS / "brief_charts.png")
    chart_pos(FIGS / "brief_position.png")
    tmp = HERE / "_brief_tmp.pdf"
    build_pdf(tmp)
    report_md(HERE / "report.md")
    dst = Path(pdf)
    if dst.parent.is_dir():
        shutil.copyfile(tmp, dst)
        print("wrote", dst, dst.stat().st_size)
    tmp.unlink()


if __name__ == "__main__":
    main()
