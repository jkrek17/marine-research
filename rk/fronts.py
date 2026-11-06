"""WPC coded surface bulletin (CODSUS, the Unified Surface Analysis as lat/lon points) from the IEM archive.

Fetches one UTC day of bulletins per request (cached as raw text under
`rk.paths.data("extra", "fronts", "codsus", "YYYYMMDD.txt")`), parses the ASUS02 blocks (tenths of a
degree) and returns lows, highs and fronts. Interface in rk/CONTRACT.md. Times are naive UTC, lon 0-360.
"""
import datetime as dt
import re

import numpy as np

from . import paths

URL = ("https://mesonet.agron.iastate.edu/cgi-bin/afos/retrieve.py"
       "?pil=CODSUS&sdate=%s&edate=%s&limit=200&fmt=text")
R_NM = 3440.065  # earth radius in nautical miles
TYPES = {"COLD": "cold", "WARM": "warm", "OCFNT": "occluded", "STNRY": "stationary", "TROF": "trough"}
_KEYWORDS = set(TYPES) | {"HIGHS", "LOWS"}
_HDR = re.compile(r"^(ASUS0\d) KWBC (\d{6})\s*$", re.M)
_ISSUE = re.compile(r"\b\d{3,4} [AP]M [A-Z]{2,4} [A-Z]{3} ([A-Z]{3}) (\d{1,2}) (\d{4})\b")
_VALID = re.compile(r"\bVALID (\d{2})(\d{2})(\d{2})Z")
_MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


# ---------------------------------------------------------------- geometry
def distance_nm(lat1, lon1, lat2, lon2):
    """Great-circle distance in nautical miles (vectorised, degrees in, any lon convention)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2, float) - np.asarray(lon1, float))
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_NM * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def _xyz(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def densify(lat, lon, step_nm=25):
    """Fill a polyline with points at most step_nm apart along the great circles between its vertices.
    Original vertices are kept. Returns (lat, lon) arrays, lon 0-360."""
    lat = np.asarray(lat, float)
    lon = np.asarray(lon, float)
    if len(lat) < 2:
        return lat.copy(), lon.copy() % 360
    la, lo = [lat[0]], [lon[0]]
    for i in range(1, len(lat)):
        d = float(distance_nm(lat[i - 1], lon[i - 1], lat[i], lon[i]))
        n = int(np.ceil(d / step_nm))
        if n > 1:
            a, b = _xyz(lat[i - 1], lon[i - 1]), _xyz(lat[i], lon[i])
            om = d / R_NM
            f = np.arange(1, n) / n
            pts = (np.sin((1 - f) * om)[None] * a[:, None] + np.sin(f * om)[None] * b[:, None]) / np.sin(om)
            la.extend(np.degrees(np.arcsin(np.clip(pts[2], -1, 1))))
            lo.extend(np.degrees(np.arctan2(pts[1], pts[0])))
        la.append(lat[i])
        lo.append(lon[i])
    return np.array(la), np.array(lo) % 360


def merge_segments(fronts, join_nm=30):
    """Join same-type fronts whose ends lie within join_nm of each other (reversing a segment when
    needed). Other keys are dropped from joined results; order of first appearance is kept."""
    out = []
    for typ in dict.fromkeys(f["type"] for f in fronts):
        segs = [(np.asarray(f["lat"], float), np.asarray(f["lon"], float)) for f in fronts if f["type"] == typ]
        merged = True
        while merged and len(segs) > 1:
            merged = False
            for i in range(len(segs)):
                for j in range(i + 1, len(segs)):
                    r = _join(segs[i], segs[j], join_nm)
                    if r is not None:
                        segs[i] = r
                        del segs[j]
                        merged = True
                        break
                if merged:
                    break
        out.extend({"type": typ, "lat": a, "lon": b} for a, b in segs)
    return out


def _join(a, b, join_nm):
    best = None
    for ra in (False, True):
        for rb in (False, True):
            x = (a[0][::-1], a[1][::-1]) if ra else a
            y = (b[0][::-1], b[1][::-1]) if rb else b
            d = float(distance_nm(x[0][-1], x[1][-1], y[0][0], y[1][0]))
            if d <= join_nm and (best is None or d < best[0]):
                best = (d, x, y)
    if best is None:
        return None
    _, x, y = best
    skip = 1 if best[0] < 1e-6 else 0
    return np.concatenate([x[0], y[0][skip:]]), np.concatenate([x[1], y[1][skip:]])


# ---------------------------------------------------------------- parser
def _pos(tok):
    """7-digit LLLLOOO (tenths of a degree, N and W) -> (lat, lon 0-360); None if not that shape."""
    if len(tok) != 7 or not tok.isdigit():
        return None
    return int(tok[:3]) / 10.0, (360.0 - int(tok[3:]) / 10.0) % 360


def _resolve(issue_year, issue_month, vm, vd, vh):
    """Valid datetime from MMDDHH and the issue year/month (December/January rollover)."""
    y = issue_year
    if vm == 12 and issue_month == 1:
        y -= 1
    elif vm == 1 and issue_month == 12:
        y += 1
    return dt.datetime(y, vm, vd, vh)


def _issued(valid, dd, hh, mm):
    """Issue time (UTC) from the DDHHMM header, taken as the month nearest the valid time."""
    best = None
    for k in (-1, 0, 1):
        y, m = valid.year, valid.month + k
        y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
        try:
            c = dt.datetime(y, m, dd, hh, mm)
        except ValueError:
            continue
        if best is None or abs(c - valid) < abs(best - valid):
            best = c
    return best


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or p != out[-1]:
            out.append(p)
    return out


def _block(text, issued_key):
    """One ASUS02 bulletin body -> analysis dict (with "issued"), or None."""
    m_i, m_v = _ISSUE.search(text), _VALID.search(text)
    if not m_i or not m_v:
        return None
    mon = _MONTHS.index(m_i.group(1)) + 1
    try:
        valid = _resolve(int(m_i.group(3)), mon, int(m_v.group(1)), int(m_v.group(2)), int(m_v.group(3)))
    except ValueError:
        return None
    feats, cur = [], None
    for line in text[m_v.end():].splitlines():
        toks = line.split()
        if not toks:
            continue
        if toks[0] in _KEYWORDS:
            cur = [toks[0], []]
            feats.append(cur)
            toks = toks[1:]
        elif cur is None:
            continue
        cur[1].extend(t for t in toks if t.isdigit())
    res = {"valid": valid, "lows": [], "highs": [], "fronts": [], "issued": issued_key(valid)}
    for key, toks in feats:
        if key in ("HIGHS", "LOWS"):
            for i in range(0, len(toks) - 1, 2):
                p = _pos(toks[i + 1])
                if p is not None:
                    res[key.lower()].append((float(toks[i]), p[0], p[1]))
            continue
        pts = _dedupe([p for p in map(_pos, toks) if p is not None])
        if len(pts) >= 2:
            res["fronts"].append({"type": TYPES[key], "lat": np.array([p[0] for p in pts]),
                                  "lon": np.array([p[1] for p in pts])})
    return res


def parse(text):
    """Text of one or more concatenated CODSUS bulletins -> list of analyses, one per valid time
    (the last issued wins), sorted by valid time. Only ASUS02 blocks are read. Pure; no network."""
    text = re.sub(r"\n[ \t]*\d{1,4}[ \t]*\n(?=\s*ASUS0\d KWBC)", "\n", "\n" + text.replace("\r", ""))
    heads = list(_HDR.finditer(text))
    best = {}
    for k, h in enumerate(heads):
        if h.group(1) != "ASUS02":
            continue
        body = text[h.end(): heads[k + 1].start() if k + 1 < len(heads) else len(text)]
        body = body.split("$$")[0]
        d, hh, mm = int(h.group(2)[:2]), int(h.group(2)[2:4]), int(h.group(2)[4:])
        a = _block(body, lambda v: _issued(v, d, hh, mm))
        if a is None:
            continue
        old = best.get(a["valid"])
        if old is None or (a["issued"] or dt.datetime.min) >= (old["issued"] or dt.datetime.min):
            best[a["valid"]] = a
    return [best[v] for v in sorted(best)]


# ---------------------------------------------------------------- fetch and cache
def _file(date):
    return paths.data("extra", "fronts", "codsus", date.strftime("%Y%m%d") + ".txt")


def _raw(date):
    """Raw bulletin text for a UTC day: cache first (never refetched), else one IEM request.
    None if the server gave nothing. Today and yesterday are not stored."""
    f = _file(date)
    if f.exists():
        return f.read_text()
    today = dt.datetime.utcnow().date()
    if date > today:
        return None
    from . import fetch  # lazy: needs the nwp package, parsing does not
    url = URL % (date.isoformat(), (date + dt.timedelta(days=1)).isoformat())
    blob = fetch.get(url)
    if blob is None:
        return None
    text = blob.content.decode("utf-8", "replace")  # nwp.get returns a requests Response
    if date < today - dt.timedelta(days=1) and "ASUS0" in text:
        tmp = f.with_suffix(".tmp")
        tmp.write_text(text)
        tmp.replace(f)
    return text


def _as_date(d):
    return d.date() if isinstance(d, dt.datetime) else d


def day(date):
    """All analyses valid on a UTC day (date or datetime), sorted. Reads that day's bulletins and the
    next day's (late corrections); [] when none."""
    date = _as_date(date)
    text = "\n".join(t for t in (_raw(date), _raw(date + dt.timedelta(days=1))) if t)
    return [a for a in parse(text) if a["valid"].date() == date]


def analysis(valid):
    """The analysis valid at `valid` (naive UTC datetime), or None."""
    for a in day(valid):
        if a["valid"] == valid:
            return a
    return None


def synoptic(valid):
    """True at 00, 06, 12 and 18 UTC."""
    return valid.hour in (0, 6, 12, 18)
