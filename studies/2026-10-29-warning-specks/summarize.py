"""Table of speck_lines.py rows: held-out and tune weeks, each basin.

caught   = ASCAT gale events (>= 2 cells at 34 kt) with a warned cell within ~60 nm / events
on       = events with a warned cell on the event itself / events
covered  = ASCAT 34 kt cells inside the warning / ASCAT 34 kt cells
false    = seen warned cells with no 34 kt within ~60 nm / seen warned cells
pieces   = mean separate warned pieces per case (what the page draws)
area, reach = mean warned area and area with the ~60 nm ring, nm2, and reach relative to the raw line

usage: python3 summarize.py ROWS.csv [OUT.md]
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))

import pandas as pd  # noqa: E402

from rk import cases  # noqa: E402


def main(src, out=None):
    d = pd.read_csv(src)
    d["split"] = pd.to_datetime(d["run"].astype(str), format="%Y%m%d%H").map(cases.split)
    lines = [__doc__.split("\n\n")[1], ""]
    for (dom, split), g in d.groupby(["dom", "split"]):
        lines += ["## %s, %s weeks (%d cases, %d events)" % (
            {"natl": "North Atlantic", "npac": "North Pacific"}[dom], split.replace("_", "-"),
            g.run.nunique() and len(g[(g.n == 0)]), g[g.n == 0].events.sum()), "",
            "| drop pieces under | fill gaps | caught | on | covered | false | pieces | area nm2 | reach nm2 | reach vs raw |",
            "|---|---|---|---|---|---|---|---|---|---|"]
        raw = g[g.n == 0].reach_nm2.mean()
        for (n, fill), h in g.groupby(["n", "fill"]):
            ev = h.events.sum()
            lines.append("| %s | %s | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.1f | %s | %s | %+.1f%% |" % (
                "raw" if n == 0 else "%d cells" % n, "yes" if fill else "", 100 * h.hits.sum() / ev,
                100 * h.hits_on.sum() / ev, 100 * h.obs_in.sum() / max(h.obs_cells.sum(), 1),
                100 * h.bad_cells.sum() / max(h.cells.sum(), 1), h.pieces.mean(),
                f"{h.area_nm2.mean():,.0f}", f"{h.reach_nm2.mean():,.0f}", 100 * (h.reach_nm2.mean() / raw - 1)))
        lines.append("")
    text = "\n".join(lines)
    print(text)
    if out:
        Path(out).write_text(text + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
