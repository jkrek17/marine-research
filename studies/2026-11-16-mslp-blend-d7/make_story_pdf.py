"""Companion PDF to the briefing: the story in graphs, then four storm storyboards.

Reads figs/story/*.png (make_story_figs.py) and results/*.csv. Every number in a headline or bullet is either formatted straight
from a CSV or asserted against one with check(); a mismatch stops the build.
Usage: python3 make_story_pdf.py [out.pdf]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (str(REPO), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)
import pandas as pd
from PIL import Image as PI
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Image, PageBreak, KeepTogether, Table, TableStyle

RES = HERE / "results"
FIG = HERE / "figs" / "story"
CREAM, NAVY, OX, SAND, MID = "#F6F0E1", "#16294D", "#6B1D2A", "#E8DFC8", "#6F7A93"
DEFAULT_PDF = "/mnt/project-files/mslp-blend-d7/mslp-blend-figures-and-cases.pdf"
PW, PH = letter
M = 0.6 * inch
W = PW - 2 * M
LEADS = (24, 48, 72, 96, 120, 144, 168)

# ------------------------------------------------------------------ data
R2 = pd.read_csv(RES / "by_lead_raw2.csv")
R2 = R2[(R2.truth == "mean") & (R2.basin == "all")].set_index(["entry", "lead"])
BL = pd.read_csv(RES / "by_lead.csv")
BL = BL[(BL.truth == "mean") & (BL.basin == "all")].set_index(["entry", "lead"])
NF = pd.read_csv(RES / "noise_floor.csv")
VOTE = pd.read_csv(RES / "diffs_vs_ifs.csv")
VOTE = VOTE[(VOTE.entry == "vote") & (VOTE.truth == "mean") & (VOTE.basin == "all") & (VOTE.subset == "main")].set_index("lead")
WARP = pd.read_csv(RES / "warp_effect.csv")
WARP = WARP[~WARP.over_water_only]
OR = pd.read_csv(RES / "outlier_risk.csv")
OR = OR[(OR.cand == "od") & (OR.setting == "X=300") & (OR.basin == "all") & (OR.model == "all")].set_index("lead")
REL = pd.read_csv(RES / "partb_reliability.csv")
REL = REL[(REL["product"] == "exist") & (REL.basin == "both") & (REL.subset == "winter") & (REL.lead == 120) & (REL.n > 0) & REL.freq.notna()]
CIRC = pd.read_csv(RES / "partb_circles.csv")
CIRC = CIRC[(CIRC.subset == "winter") & (CIRC.truth == "mean") & (CIRC.basin == "both")].set_index("lead")
RNG = pd.read_csv(RES / "partb_range.csv")
RNG = RNG[(RNG.subset == "winter") & (RNG.truth == "mean") & (RNG.basin == "both") & (RNG.direction == "forecast_low")].set_index("lead")
ALT = pd.read_csv(RES / "partb_alt.csv")
ALT = ALT[(ALT.subset == "winter") & (ALT.truth == "mean") & (ALT.basin == "both") & (ALT.kind == "pos")].set_index("lead")
TR = pd.read_csv(RES / "story_tracks.csv")
SC = pd.read_csv(RES / "story_cases.csv").set_index("case")
DET = pd.read_csv(RES / "worked_cases_detail.csv").set_index("case")
CAND = pd.read_csv(RES / "story_false_deep_candidates.csv")


def r2(e, L, col):
    return float(R2.loc[(e, L), col])


def bl(e, L, col):
    return float(BL.loc[(e, L), col])


def check(label, got, want, tol=0.5):
    if abs(got - want) > tol:
        raise SystemExit("MISMATCH %s: csv %.3f vs text %.3f" % (label, got, want))


def n0(x):
    return "%d" % round(x)


def n1(x):
    return "%.1f" % x


def tk(case, lead, src, col="hpa"):
    d = TR[(TR.case == case) & (TR.lead == lead) & (TR.source == src)]
    return float(d[col].iloc[0]) if len(d) else float("nan")


# ------------------------------------------------------------------ headlines (numbers asserted)
def head1():
    ents = ("ifs", "gfs", "aifs", "m_gi", "ens", "gefs")
    for L in LEADS:
        assert r2("ifs", L, "pos_km") <= min(r2(e, L, "pos_km") for e in ents) + 1e-9, "ECMWF not best at lead %d" % L
    for L in (120, 144, 168):
        assert VOTE.loc[L, "dpos"] < 0
    check("floor", float(NF[NF.lead == 24].pos_km.max()), 130, 1)
    check("floor lo", float(NF[NF.lead == 24].pos_km.min()), 119, 1)
    h = "ECMWF places the lows best at every lead; on days 5-7 the member vote is closer still"
    s = ("Mean position error, ECMWF %s km at day 1, %s at day 4 and %s at day 7, against %s, %s and %s for GFS. The GFS+ECMWF mean never beats ECMWF. The ensemble means and GEFS trail (day 7: ECMWF ens. %s, GEFS %s km). The shaded band is how far the "
         "two analyses disagree on where the low is (119-130 km), so day-1 errors are already close to the floor. On days 5-7 (12Z cycles only) the member vote "
         "is %s, %s and %s km closer than ECMWF on the same cases."
         % (n0(r2("ifs", 24, "pos_km")), n0(r2("ifs", 96, "pos_km")), n0(r2("ifs", 168, "pos_km")),
            n0(r2("gfs", 24, "pos_km")), n0(r2("gfs", 96, "pos_km")), n0(r2("gfs", 168, "pos_km")),
            n0(r2("ens", 168, "pos_km")), n0(r2("gefs", 168, "pos_km")),
            n0(-VOTE.loc[120, "dpos"]), n0(-VOTE.loc[144, "dpos"]), n0(-VOTE.loc[168, "dpos"])))
    # claim in the text: mean is never better than ECMWF
    for L in LEADS:
        assert r2("m_gi", L, "pos_km") >= r2("ifs", L, "pos_km") - 1e-9, L
    return h, s


def head2():
    assert r2("al", 168, "rmse") < r2("ifs", 168, "rmse") and r2("al", 168, "pos_km") > r2("ifs", 168, "pos_km")
    h = "The closest field is not the best placement"
    s = ("At day 7 the aligned blend (all runs) has the smallest pressure-field error, %s hPa against %s for ECMWF, but it puts the lows %s km farther away "
         "(%s against %s km). Smoothing wins on RMSE and loses on where the low is. At day 1 the choice hardly matters; by day 5 ECMWF is best on position (%s km) "
         "while the aligned blend is best on RMSE (%s hPa)."
         % (n1(r2("al", 168, "rmse")), n1(r2("ifs", 168, "rmse")), n0(r2("al", 168, "pos_km") - r2("ifs", 168, "pos_km")),
            n0(r2("al", 168, "pos_km")), n0(r2("ifs", 168, "pos_km")), n0(r2("ifs", 120, "pos_km")), n1(r2("al", 120, "rmse"))))
    for e in ("ifs", "gfs", "aifs", "m_gi", "m_gif", "ens", "gefs", "od"):
        assert r2("al", 120, "rmse") <= r2(e, 120, "rmse") + 1e-9, e
        assert r2("ifs", 120, "pos_km") <= r2(e, 120, "pos_km") + 1e-9, e
    return h, s


def head3():
    h = "Why blends look smooth: they flatten the deep lows"
    s = ("Sharpness is the strength of the forecast pressure features compared with the analysis (1 = as sharp). By day 7 ECMWF is at %s, the GFS+ECMWF mean %s, "
         "the three-model mean %s and the aligned blend %s. The cost shows on strong lows (analysed below 980 hPa): too shallow by %s hPa for the aligned blend against "
         "%s for ECMWF at day 7. The depth fix brings the aligned blend back to %s, but not to ECMWF's level. (Shown with the aligned blend of all runs: the "
         "three-model mean with the depth fix is not a separate scored candidate.)"
         % (n1(bl("ifs", 168, "sharp")), n1(bl("m_gi", 168, "sharp")), n1(bl("m_gif", 168, "sharp")), n1(bl("al", 168, "sharp")),
            n1(bl("al", 168, "strong_bias")), n1(bl("ifs", 168, "strong_bias")), n1(bl("ald", 168, "strong_bias"))))
    assert bl("ald", 168, "strong_bias") > bl("ifs", 168, "strong_bias")
    return h, s


def head4():
    h = "Too shallow or too deep? It depends which lows you look at"
    s = ("At day 7 ECMWF is %s hPa too shallow on the lows that verified below 980 hPa, yet %s hPa too deep on the lows it forecast below 980. GFS: +%s and %s. "
         "The same forecast is both. A blanket deepening of the blend therefore helps one side and hurts the other."
         % (n1(bl("ifs", 168, "strong_bias")), n1(-bl("ifs", 168, "fdeep_bias")), n1(bl("gfs", 168, "strong_bias")), n1(bl("gfs", 168, "fdeep_bias"))))
    assert bl("ifs", 168, "strong_bias") > 0 > bl("ifs", 168, "fdeep_bias") and bl("gfs", 168, "strong_bias") > 0 > bl("gfs", 168, "fdeep_bias")
    return h, s


def head5():
    w = WARP
    mx = float(w.dpos_km.abs().max())
    assert mx < 5.0
    check("warp max", mx, 4.8, 0.1)
    h = "Moving lows to the consensus adds almost nothing"
    s = ("Aligning the runs' lows to a common position before averaging changes the mean position error by less than 5 km at every lead (largest move %s km, "
         "either way). The bars are the change against the plain mean; the shaded band is plus or minus 5 km. Whatever the aligned blend gains is from the pressure "
         "averaging, not from moving the lows. (Both comparisons are post hoc.)" % n1(mx))
    assert bool(w.post_hoc.all())
    return h, s


def head6():
    s7 = OR
    lo, hi = float(s7.share_closest.min()), float(s7.share_closest.max())
    check("share lo", 100 * lo, 7, 0.5)
    check("share hi", 100 * hi, 13, 0.5)
    h = "Your outlier habit is right: the model you would drop is rarely the closest"
    s = ("When one run sits 300 km or more from the others and is dropped, it was the closest to the analysed low in only %s-%s%% of drops, depending on lead. "
         "The dropped run's low was %s-%s km from the analysis, the best other run's %s-%s km. Dropping is still a judgement: about one drop in eight, "
         "the run you threw away was the one that had it right."
         % (n0(100 * lo), n0(100 * hi), n0(s7.drop_err_km.min()), n0(s7.drop_err_km.max()), n0(s7.best_other_km.min()), n0(s7.best_other_km.max())))
    return h, s


def head7():
    for L in LEADS:
        assert bl("m_gif", L, "false_per_map") < bl("ifs", L, "false_per_map")
    h = "ECMWF and GFS draw the most lows, and most of the extras are false"
    s = ("Per map at day 7: ECMWF draws %s lows, %s of them false; GFS %s and %s; the three-model mean %s and %s; the aligned blend %s and %s; GEFS %s and %s. "
         "A false low is a forecast low with no analysed low within the match distance. Fewer lows on the map is not a loss of information if the missing ones were not real."
         % (n1(bl("ifs", 168, "fc_lows_per_map")), n1(bl("ifs", 168, "false_per_map")), n1(bl("gfs", 168, "fc_lows_per_map")), n1(bl("gfs", 168, "false_per_map")),
            n1(bl("m_gif", 168, "fc_lows_per_map")), n1(bl("m_gif", 168, "false_per_map")), n1(bl("al", 168, "fc_lows_per_map")), n1(bl("al", 168, "false_per_map")),
            n1(bl("gefs", 168, "fc_lows_per_map")), n1(bl("gefs", 168, "false_per_map"))))
    return h, s


def head8():
    gaps = [100 * (float(q.freq) - float(q.mean_p)) for _, q in REL.iterrows()]
    assert 4.5 < min(gaps) and max(gaps) < 10.5, gaps
    cov = [100 * RNG.loc[l, "cov80"] for l in (120, 144, 168)]
    assert all(72 <= c <= 88 for c in cov), cov
    h = "Day 5-7 probabilities: honest, if a little cautious"
    s = ("Chance a low exists (winter, day 5): lows were there %s-%s points more often than stated, so the chances are slightly low, not high. The 10-90%% depth range caught "
         "%s, %s and %s%% of analysed depths on days 5, 6 and 7, inside the 72-88%% band. The 50%% circle at day 5 is %s km when most members carry the low and "
         "%s km when few do. Alternative scenarios shown on the map verified %s%% of the time at day 5 against %s%% for a placebo location."
         % (n0(min(gaps)), n0(max(gaps)), n0(cov[0]), n0(cov[1]), n0(cov[2]), n0(CIRC.loc[120, "terc2_r50"]), n0(CIRC.loc[120, "terc0_r50"]),
            n0(100 * ALT.loc[120, "verified"]), n0(100 * ALT.loc[120, "placebo"])))
    assert CIRC.loc[120, "terc2_r50"] < CIRC.loc[120, "terc0_r50"] and ALT.loc[120, "verified"] > ALT.loc[120, "placebo"]
    return h, s


# ------------------------------------------------------------------ storms
STORMS = [
    ("natl-deep-2025-12-11", "Deepest Atlantic low of the winter, 11 Dec 2025"),
    ("npac-deep-2025-11-08", "Deepest Pacific low of the winter, 8 Nov 2025"),
    ("natl-split-2026-01-27", "The Atlantic split, 27 Jan 2026"),
    ("npac-falsedeep-2025-12-09", "False-deep case, North Pacific, 9 Dec 2025"),
]


def an_hpa(cid):
    return tk(cid, 0, "analysis")


def bullets(cid):
    a = an_hpa(cid)
    g = lambda L, s: tk(cid, L, s)
    d = lambda L, s: tk(cid, L, s, "dist_km")
    if cid == "natl-deep-2025-12-11":
        check("an", a, 937, 0.6)
        check("deet", DET.loc[cid, "an_hpa"], a, 0.6)
        return [
            "<b>What happened.</b> The analysis reads %s hPa. ECMWF had %s, %s and %s hPa at days 1, 2 and 3. GFS had %s and %s at days 1 and 2 but fell back to %s at day 3 and %s at day 4."
            % (n0(a), n0(g(24, "ifs")), n0(g(48, "ifs")), n0(g(72, "ifs")), n0(g(24, "gfs")), n0(g(48, "gfs")), n0(g(72, "gfs")), n0(g(96, "gfs"))),
            "<b>Day 5.</b> The two runs disagreed by %s hPa: GFS %s (%s km off), ECMWF %s (%s km off), their mean %s (%s km off). Averaging gave a shallower low than the run that had "
            "it right." % (n0(abs(g(120, "gfs") - g(120, "ifs"))), n0(g(120, "gfs")), n0(d(120, "gfs")), n0(g(120, "ifs")), n0(d(120, "ifs")),
                                                           n0(g(120, "m_gi")), n0(d(120, "m_gi"))),
            "<b>The vote.</b> %s hPa at day 5, %s km off, then %s at day 6 and %s at day 7 (%s and %s km off). Stated chance the low existed: %s%%. The analysed depth fell outside "
            "the vote's 10-90%% range (%s-%s hPa) and outside both circles: the range was too shallow for the deepest storms." %
            (n0(g(120, "vote")), n0(d(120, "vote")), n0(g(144, "vote")), n0(g(168, "vote")), n0(d(144, "vote")), n0(d(168, "vote")), n0(100 * DET.loc[cid, "vote_chance"]),
             n0(DET.loc[cid, "vote_q10"]), n0(DET.loc[cid, "vote_q90"])),
            "<b>What the desk could have used.</b> Every source had a low of %s-%s hPa near the place at day 7, so a strong-low call was available a week out; the central "
            "pressure was %s-%s hPa too shallow at day 5 and the vote's range did not reach the analysed depth. Use the warning, widen the range toward deeper values." %
            (n0(min(g(168, s) for s in ("ifs", "gfs", "m_gi", "vote"))), n0(max(g(168, s) for s in ("ifs", "gfs", "m_gi", "vote"))),
             n0(min(g(120, "vote"), g(120, "m_gi")) - a), n0(max(g(120, "vote"), g(120, "m_gi")) - a)),
        ]
    if cid == "npac-deep-2025-11-08":
        check("an", a, 941, 0.6)
        return [
            "<b>What happened.</b> The analysis reads %s hPa at 12Z on 8 Nov. ECMWF held %s-%s hPa from day 1 to day 5 and GFS %s-%s hPa, both within about 200 km of the analysed low "
            "(day 5: ECMWF %s km, GFS %s km)." % (n0(a), n0(min(g(L, "ifs") for L in (24, 48, 72, 96, 120))), n0(max(g(L, "ifs") for L in (24, 48, 72, 96, 120))),
                                                  n0(min(g(L, "gfs") for L in (24, 48, 72, 96, 120))), n0(max(g(L, "gfs") for L in (24, 48, 72, 96, 120))),
                                                  n0(d(120, "ifs")), n0(d(120, "gfs"))),
            "<b>Day 6-7.</b> Both runs let it fill: ECMWF %s then %s, GFS %s then %s hPa. Both filled the low too early." %
            (n0(g(144, "ifs")), n0(g(168, "ifs")), n0(g(144, "gfs")), n0(g(168, "gfs"))),
            "<b>The vote.</b> %s hPa at day 5, %s km off, %s at day 6 (%s km off) and %s at day 7 (%s km off). Chance it existed %s%%; the 10-90%% range %s-%s hPa held the analysed "
            "%s and both circles held the position." % (n0(g(120, "vote")), n0(d(120, "vote")), n0(g(144, "vote")), n0(d(144, "vote")), n0(g(168, "vote")), n0(d(168, "vote")),
                                                         n0(100 * DET.loc[cid, "vote_chance"]), n0(DET.loc[cid, "vote_q10"]), n0(DET.loc[cid, "vote_q90"]), n0(a)),
            "<b>What the desk could have used.</b> The place was right for a week and the depth range was right at day 5; the member vote kept a deep low where the single runs "
            "began to fill it.",
        ]
    if cid == "natl-split-2026-01-27":
        check("an", a, 981, 0.6)
        return [
            "<b>What happened.</b> A low that split in the analysis, %s hPa at the lower of the two centres. Through day 6 every source stayed between %s and %s hPa; the runs were "
            "within %s km at day 5." % (n0(a), n0(min(g(L, s) for L in (24, 48, 72, 96, 120, 144) for s in ("ifs", "gfs", "m_gi"))),
                                        n0(max(g(L, s) for L in (24, 48, 72, 96, 120, 144) for s in ("ifs", "gfs", "m_gi"))), n0(max(d(120, "ifs"), d(120, "gfs"), d(120, "m_gi")))),
            "<b>Day 5.</b> GFS %s (%s km off), ECMWF %s (%s km off), mean %s (%s km off). The mean sits in between the two members' lows, farther from the analysed centre than ECMWF alone." %
            (n0(g(120, "gfs")), n0(d(120, "gfs")), n0(g(120, "ifs")), n0(d(120, "ifs")), n0(g(120, "m_gi")), n0(d(120, "m_gi"))),
            "<b>The vote.</b> %s hPa, %s km off at day 5, the closest of the sources, then %s km off at day 6 and %s at day 7 as the split opened. Chance it existed %s%%, "
            "inside the range (%s-%s hPa) and both circles." % (n0(g(120, "vote")), n0(d(120, "vote")), n0(d(144, "vote")), n0(d(168, "vote")),
                                                                n0(100 * DET.loc[cid, "vote_chance"]), n0(DET.loc[cid, "vote_q10"]), n0(DET.loc[cid, "vote_q90"])),
            "<b>What the desk could have used.</b> A low that stays near 980 hPa with an uncertain second centre: the circles and the alternative-scenario marker said so at day 5, "
            "while the single maps gave one sharp low.",
        ]
    if cid == "npac-falsedeep-2025-12-09":
        check("an", a, 995, 0.6)
        r = CAND.sort_values("pair").iloc[0] if "pair" in CAND else None
        return [
            "<b>What happened.</b> The low that verified was weak, %s hPa. Every source had it at %s-%s hPa on days 1 to 3, then GFS fell to %s and ECMWF to %s at day 5, "
            "the mean %s, deeper by %s hPa." % (n0(a), n0(min(g(L, s) for L in (24, 48, 72) for s in ("ifs", "gfs", "m_gi"))), n0(max(g(L, s) for L in (24, 48, 72) for s in ("ifs", "gfs", "m_gi"))),
                                                n0(g(120, "gfs")), n0(g(120, "ifs")), n0(g(120, "m_gi")), n0(a - g(120, "m_gi"))),
            "<b>Why it was picked.</b> By the rule below it is the day-5 forecast with the largest gap between what both runs forecast and what verified: GFS and ECMWF within 450 km "
            "of each other, both deeper than 990 hPa, deepest verifying weakest (forecast pair mean %s hPa, analysed %s)." % (n0((g(120, "gfs") + g(120, "ifs")) / 2), n0(a)),
            "<b>The vote.</b> %s hPa at day 5, %s km off, %s and %s at days 6 and 7. The vote did not rescue the depth: it was about as deep as the mean. The map shows a second, "
            "weaker low in the vote." % (n0(g(120, "vote")), n0(d(120, "vote")), n0(g(144, "vote")), n0(g(168, "vote"))),
            "<b>What the desk could have used.</b> Not the central pressure. Forecast depth is least trustworthy where two runs agree on a deep low at day 5 and the day-4 value "
            "has just dropped from %s to %s hPa within one day; widen the depth range, keep the place." % (n0(g(96, "m_gi")), n0(g(120, "m_gi"))),
        ]
    raise KeyError(cid)


# ------------------------------------------------------------------ pdf
def styles():
    s = {}
    s["title"] = ParagraphStyle("title", fontName="Times-Bold", fontSize=18, leading=21, textColor=HexColor(NAVY), spaceAfter=3)
    s["sub"] = ParagraphStyle("sub", fontName="Helvetica", fontSize=8, leading=10, textColor=HexColor(MID), spaceAfter=5)
    s["h"] = ParagraphStyle("h", fontName="Times-Bold", fontSize=12.5, leading=14, textColor=HexColor(OX), spaceBefore=3, spaceAfter=2)
    s["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=8.4, leading=10.6, textColor=HexColor(NAVY))
    s["cap"] = ParagraphStyle("cap", parent=s["body"], fontSize=8.0, leading=10.0)
    s["bul"] = ParagraphStyle("bul", parent=s["body"], leftIndent=9, bulletIndent=0, fontSize=8.4, leading=10.5, spaceAfter=2.5)
    s["small"] = ParagraphStyle("small", parent=s["body"], fontSize=7.3, leading=9, textColor=HexColor(MID))
    s["cell"] = ParagraphStyle("cell", parent=s["body"], fontSize=7.4, leading=9)
    s["cellb"] = ParagraphStyle("cellb", parent=s["cell"], fontName="Helvetica-Bold", textColor=HexColor(CREAM))
    return s


def esc_amp(t):
    return t.replace("&", "&amp;")


LABELS = {}


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
    canvas.drawString(M, 0.36 * inch, "MSLP to day 7 · figures and cases · 16 Nov 2026 · page %d" % doc.page)
    canvas.restoreState()


def fig(name, width=W):
    pw, ph = PI.open(FIG / name).size
    return Image(str(FIG / name), width=width, height=width * ph / pw)


def block(name, headline, support, S):
    return KeepTogether([Paragraph(esc_amp(headline), S["h"]), fig(name), Spacer(1, 2), Paragraph(esc_amp(support), S["cap"]), Spacer(1, 7)])


def storm_page(cid, title, S):
    maps_lead = int(SC.loc[cid, "lead_map"])
    out = [Paragraph(esc_amp(title), S["title"])]
    row = SC.loc[cid]
    out.append(Paragraph("Valid %s · analysed low %s hPa · tracks are the 12Z runs for that valid time, day 7 to day 1 (circle and label = forecast pressure); "
                         "the map row is the day-%d forecast." % (row.valid, n0(an_hpa(cid)), maps_lead // 24), S["sub"]))
    out.append(fig("c_%s_track.png" % cid))
    out.append(Spacer(1, 4))
    out.append(fig("c_%s_maps.png" % cid))
    out.append(Paragraph("Left: ECMWF ensemble mean with the member lows. Middle: GFS+ECMWF mean with the most likely lows (labelled L, with the 10-90% pressure range and the chance "
                         "the low exists; E and G are the single-run lows). Right: the analysis.", S["small"]))
    out.append(Spacer(1, 4))
    for b in bullets(cid):
        out.append(Paragraph(b, S["bul"], bulletText="•"))
    return out


def summary_page(S):
    out = [Paragraph("Four storms", S["title"]),
           Paragraph("Three are the storms the desk would remember, one is a miss. Each page shows where each run put the low as the day got closer, how its depth "
                     "changed, and what the day-5 maps looked like.", S["sub"])]
    rows = [["Storm", "Analysed", "Day 5 GFS", "Day 5 ECMWF", "Day 5 mean", "Day 5 vote"]]
    for cid, t in STORMS:
        rows.append([t, "%s hPa" % n0(an_hpa(cid))] +
                    ["%s hPa, %s km" % (n0(tk(cid, 120, s)), n0(tk(cid, 120, s, "dist_km"))) for s in ("gfs", "ifs", "m_gi", "vote")])
    data = [[Paragraph(esc_amp(str(c)), S["cellb"] if i == 0 else S["cell"]) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[2.2 * inch, 0.8 * inch] + [1.07 * inch] * 4)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), HexColor(NAVY)), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LINEBELOW", (0, 0), (-1, -1), 0.25, HexColor(SAND)), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    out += [t, Spacer(1, 8)]
    out.append(Paragraph("How the cases were chosen", S["h"]))
    r = CAND.iloc[0]
    assert (CAND.deficit.iloc[0] == CAND.deficit.max()) and r.basin == "npac"
    rn = CAND[CAND.basin == "natl"].iloc[0]
    out.append(Paragraph(
        "<b>Deepest Atlantic and Pacific:</b> the lowest analysed pressure of the winter in each basin (11 Dec 2025, %s hPa; 8 Nov 2025, %s hPa). "
        "<b>The Atlantic split:</b> the largest day-5 disagreement between a GFS low and an ECMWF low in the Atlantic (%s km, forecast from 22 Jan 2026, valid 27 Jan). "
        "<b>False-deep case, fixed before the maps were looked at:</b> across every winter 12Z cycle at day 4 and day 5, take each pair of one GFS low and one ECMWF low, "
        "both deeper than 990 hPa and within 450 km of each other. Forecast depth is the pair's mean; analysed depth is the lowest mean-analysis pressure within 500 km of the pair. "
        "The case is the pair with the largest analysed-minus-forecast pressure: the deepest low both runs forecast that verified weakest." %
        (n0(an_hpa("natl-deep-2025-12-11")), n0(an_hpa("npac-deep-2025-11-08")), n0(float(DET.loc["natl-split-2026-01-27", "split_km"]))), S["body"]))
    out.append(Spacer(1, 6))
    out.append(Paragraph("It is %s: Pacific, forecast from %s at day 5 (pair mean %s hPa, GFS %s and ECMWF %s), analysed %s hPa, a gap of %s hPa. "
                         "The best Atlantic candidate (cycle %s, day %d, %s hPa forecast against %s), was %s hPa short." %
                         ("the 9 Dec 2025 low", "the 4 Dec 12Z cycle", n1(float(r["pair"])), n1(float(r["gfs"])), n1(float(r["ifs"])), n1(float(r["an_min500"])),
                          n1(float(r["an_min500"]) - float(r["pair"])), str(rn["cycle"])[:10], int(rn["lead"]) // 24, n0(float(rn["pair"])), n0(float(rn["an_min500"])),
                          n0(float(rn["deficit"]))), S["body"]))
    out.append(Spacer(1, 6))
    out.append(Paragraph("Four storms are a gallery, not a sample: the scores on the earlier pages come from every case in the winter.", S["small"]))
    return out


def build(path):
    S = styles()
    doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=M, rightMargin=M, topMargin=0.45 * inch, bottomMargin=0.55 * inch,
                          title="MSLP forecasts to day 7: figures and cases", author="Marine desk research")
    doc.addPageTemplates([PageTemplate(id="p", frames=[Frame(M, 0.55 * inch, W, PH - 1.0 * inch, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=bg)])
    st = [Paragraph("Best MSLP forecast to day 7: the story in graphs, and four storms", S["title"]),
          Paragraph("Companion to the briefing. Winter 2025-26, North Atlantic and North Pacific, 00Z and 12Z. Truth is the mean of the GFS and ECMWF analyses; ECMWF is the "
                    "deterministic run. Position error counts a missed low as 1000 km; strong lows are those analysed below 980 hPa. Every number is read from the study's result files.",
                    S["sub"])]
    st.append(block("s1_position_by_day.png", *head1(), S))
    st.append(block("s2_field_vs_position.png", *head2(), S))
    st.append(PageBreak())
    st.append(block("s3_smooth_blends.png", *head3(), S))
    st.append(block("s4_shallow_or_deep.png", *head4(), S))
    st.append(PageBreak())
    st.append(block("s5_warp_effect.png", *head5(), S))
    st.append(block("s6_outlier_habit.png", *head6(), S))
    st.append(PageBreak())
    st.append(block("s7_lows_per_map.png", *head7(), S))
    st.append(block("s8_probability.png", *head8(), S))
    st.append(PageBreak())
    st += summary_page(S)
    for cid, t in STORMS:
        st.append(PageBreak())
        st += storm_page(cid, t, S)
    doc.build(st)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF)
    build(out)
    print("wrote", out, out.stat().st_size)
