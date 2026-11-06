"""Build the blind case folders the agent plays from: panels, the given L and stationary fronts, two worked examples,
and the case's fields as an .npz for the look-up tools. No analysed cold/warm/occluded front of the case goes in.
  python3 blind.py <outdir> [ids...]     (default: the 50 test cases)
"""
import json
import sys
from pathlib import Path

import numpy as np

import deck
import panels

HERE = Path(__file__).resolve().parent
COLORS = {"cold": "#1565c0", "warm": "#d32f2f", "occluded": "#7b1fa2", "stationary": "#555555", "trough": "#e08a00"}


def similar(case, man, vt, tune, k=2):
    """k worked examples: same basin, nearest in low pressure and latitude, never the same storm (within 48 h and 1000 nm)."""
    t0 = vt[case["id"]]
    c0 = case["low"]
    cand = []
    for c in man["cases"]:
        if c["id"] not in tune or c["basin"] != case["basin"]:
            continue
        if abs((vt[c["id"]] - t0).total_seconds()) < 48 * 3600 and deck._nm(c["low"]["lat"], c["low"]["lon"], c0["lat"], c0["lon"]) < 1000:
            continue
        if not deck.system_fronts(c):
            continue
        cand.append((abs(c["low"]["hpa"] - c0["hpa"]) / 5 + abs(c["low"]["lat"] - c0["lat"]) / 5, c["id"]))
    cand.sort()
    byid = {c["id"]: c for c in man["cases"]}
    return [byid[i] for _, i in cand[:k]]


def fmt_pts(pts, every=4):
    p = pts[::every] + ([pts[-1]] if (len(pts) - 1) % every else [])
    return "; ".join(f"{a:.1f}N {((b + 180) % 360) - 180:+.1f}" for a, b in p)


def example_png(case, man, view):
    """A panel with the analysed system fronts drawn on it (worked example only)."""
    import io
    import matplotlib.pyplot as plt
    png = panels.draw(case, view, man=man)
    img = plt.imread(io.BytesIO(png))
    F = deck.fields(case, man)
    fig = plt.figure(figsize=(10.0, 6.6), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img)
    ax.axis("off")
    # same placement as panels.draw: axes [0.06, 0.07, 0.92, 0.86] of a 1000 x 660 px figure
    W, H = img.shape[1], img.shape[0]
    x0, x1 = F["lon"][0] - 0.25, F["lon"][-1] + 0.25
    y0, y1 = F["lat"][-1] - 0.25, F["lat"][0] + 0.25
    for f in deck.system_fronts(case, ("cold", "warm", "occluded")):
        p = np.array(f["pts"])
        px = (0.06 + 0.92 * (p[:, 1] - x0) / (x1 - x0)) * W
        py = (1 - (0.07 + 0.86 * (p[:, 0] - y0) / (y1 - y0))) * H
        ax.plot(px, py, color=COLORS[f["type"]], lw=3.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()


def build(out, ids):
    man = deck.manifest()
    vt = deck.valid_times()
    tune = set(deck.tune_ids())
    byid = {c["id"]: c for c in man["cases"]}
    for cid in ids:
        case = byid[cid]
        d = Path(out) / cid
        (d / "examples").mkdir(parents=True, exist_ok=True)
        F = deck.fields(case, man)
        for v in panels.available(case):
            (d / f"panel_{v}.png").write_bytes(panels.draw(case, v, F, man))
        np.savez_compressed(d / "fields.npz", **{k: F[k] for k in ("lat", "lon", "msl", "thk", "u10", "v10", "te850", "te700", "dp3", "ws10_kt", "land")})
        st, lows = deck.given(case)
        info = [f"Case {cid}, {'North Atlantic' if case['basin'] == 'natl' else 'North Pacific'}, analysis valid {vt[cid]:%Y-%m-%d %HZ}.",
                f"Analysed low of the system (given): {case['low']['lat']:.1f}N {((case['low']['lon'] + 180) % 360) - 180:+.1f} (lon, + east / - west), {case['low']['hpa']:.0f} hPa.",
                f"Other analysed lows inside the ring (given): " + ("; ".join(f"{l['lat']:.1f}N {((l['lon'] + 180) % 360) - 180:+.1f} {l['hpa']:.0f} hPa" for l in lows if (l['lat'], l['lon']) != (case['low']['lat'], case['low']['lon'])) or "none"),
                f"Ring radius around the low: {case.get('sys_r_nm', 0):.0f} nm (only fronts of this system are scored; fronts mostly outside the ring cost nothing).",
                "Stationary fronts of the system (given, already drawn red/blue dashed, not scored): " + (" | ".join(fmt_pts(f["pts"]) for f in st) or "none"),
                "Panels: " + ", ".join(f"panel_{v}.png" for v in panels.available(case))]
        (d / "case.txt").write_text("\n".join(info) + "\n")
        ex_txt = []
        for k, ex in enumerate(similar(case, man, vt, tune), 1):
            for v in ("msl", "te850"):
                (d / "examples" / f"ex{k}_{v}.png").write_bytes(example_png(ex, man, v))
            fr = deck.system_fronts(ex, ("cold", "warm", "occluded"))
            ex_txt.append(f"Example {k}: {'N Atlantic' if ex['basin'] == 'natl' else 'N Pacific'} {vt[ex['id']]:%Y-%m-%d %HZ}, low {ex['low']['lat']:.1f}N {((ex['low']['lon'] + 180) % 360) - 180:+.1f} {ex['low']['hpa']:.0f} hPa."
                          f" Analysed fronts (drawn on ex{k}_msl.png and ex{k}_te850.png; blue cold, red warm, purple occluded):\n"
                          + "\n".join(f"  {f['type']}: {fmt_pts(f['pts'])}" for f in fr))
        (d / "examples" / "answers.txt").write_text("\n\n".join(ex_txt) + "\n")
    print("built", len(ids), "case folders in", out)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2:] or deck.test_ids())
