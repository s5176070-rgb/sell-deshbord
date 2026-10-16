"""Redraw the shareable page in this directory from today's model output.

`page.html` is the page published to the two artifact URLs. It is tracked, not
generated: nothing in the repository can rebuild it from scratch, so losing it
means losing the design. This script only rewrites the numbers inside it.

Its predecessors were one script per chart, kept in a temporary directory. That
directory was cleared when the app quit and they were gone, which is why these
two files live in the repository instead.

Geometry is the page's own, recovered from the published SVG and kept exactly:
  history chart  viewBox 860x200, 130 points, floor y=176.4, span 152.8
  context cards  viewBox 260x70,   60 points, floor y=66.0,  span 62.0
  ring gauge     r=80, circumference 502.65, dial full scale 40%

The band bars are NOT redrawn. Their heights come from the calibration window,
which ends twenty sessions back and does not move day to day. Only the pill
saying which band today sits in could move, and that is asserted instead.

Run from the repository root, after check.py has written today's row:

    python check.py
    python artifact/refresh.py
    python artifact/edit.py      # after editing its constants

refresh.py is safe to run twice; edit.py is not, and says so.
"""
import csv
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
PROJECT = HERE.parent
PAGE = HERE / "page.html"

CHART = dict(w=860.0, n=130, floor=176.4, span=152.8)
CARD = dict(w=260.0, n=60, floor=66.0, span=62.0)
CIRC, DIAL = 502.65, 40.0
BANDS = [(0, 45, 40), (45, 70, 220), (70, 85, 400), (85, 101, 580)]


def rows(name):
    with open(PROJECT / name, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def plot(values, geom):
    """Map a series onto one of the page's two coordinate systems."""
    lo, hi = min(values), max(values)
    step = geom["w"] / (geom["n"] - 1)
    span = (hi - lo) or 1.0

    def y(v):
        return round(geom["floor"] - (v - lo) / span * geom["span"], 1)

    pts = " ".join(f"{i * step:.1f},{y(v)}" for i, v in enumerate(values))
    return pts, y, lo, hi


def one(pattern, art, flags=0):
    """The single match a rewrite expects, or a loud failure."""
    found = re.findall(pattern, art, flags)
    assert len(found) == 1, f"{len(found)} matches for {pattern[:50]}"
    return re.search(pattern, art, flags)


def swap(art, pattern, new, flags=0):
    m = one(pattern, art, flags)
    return art[:m.start()] + new + art[m.end():]


# ---------------------------------------------------------------- model output
score = rows("score.csv")
today = score[-1]
chance, mss = float(today["chance_pct"]), float(today["percentile"])
meta = json.load(open(PROJECT / "score_meta.json", encoding="utf-8"))
assert meta["data_as_of"] == today["date"], "score.csv and score_meta.json disagree"

trend = mss - float(score[-6]["percentile"])
window = [float(r["chance_pct"]) for r in score[-CHART["n"]:]]
assert len(window) == CHART["n"], f"only {len(window)} rows of history"
start = date.fromisoformat(score[-CHART["n"]]["date"])

# The dashed mean is the realised rate over the calibrated window, not a
# constant. Recompute it so a doc can never outlive the code.
sys.path.insert(0, str(PROJECT))
import pandas as pd  # noqa: E402
import eval as ev  # noqa: E402  (the project's module, shadowing nothing we use)

dates = [r["date"] for r in score if r["date"] >= meta["calibrated_from"]]
realised = ev.hits(pd.to_datetime(dates), offline=True).dropna()
base = round(realised.mean() * 100, 1)

art = PAGE.read_text(encoding="utf-8")

# ------------------------------------------------------------- history chart
pts, ypos, lo, hi = plot(window, CHART)
art = swap(art, r'<polygon fill="url\(#areaFill\)" points="[^"]+"/>',
           f'<polygon fill="url(#areaFill)" points="0,190 {pts} 860,190"/>')
art = swap(art, r'<polyline fill="none" stroke="#2a78d6" stroke-width="2\.6"[^>]*?points="[^"]+"/>',
           '<polyline fill="none" stroke="#2a78d6" stroke-width="2.6" '
           'stroke-linejoin="round" stroke-linecap="round"\n'
           f'        points="{pts}"/>', re.S)
art = swap(art, r'<circle cx="860" cy="[\d.]+" r="5" fill="#2a78d6"/>',
           f'<circle cx="860" cy="{ypos(window[-1])}" r="5" fill="#2a78d6"/>')
art = swap(art, r'<line x1="0" y1="[\d.]+" x2="860" y2="[\d.]+" stroke="#8a8578"',
           f'<line x1="0" y1="{ypos(base)}" x2="860" y2="{ypos(base)}" stroke="#8a8578"')
art = swap(art, r'(?<=<text x="6" y="20" font-family="Rubik,sans-serif" font-size="11.5" '
                r'fill="#9a9484" direction="ltr">)[\d.]+%', f"{hi}%")
art = swap(art, r'(?<=<text x="6" y="188" font-family="Rubik,sans-serif" font-size="11.5" '
                r'fill="#9a9484" direction="ltr">)[\d.]+%', f"{lo}%")
art = swap(art, r'<text x="854" y="[\d.]+" text-anchor="end" font-family="Rubik,sans-serif" '
                r'font-size="11\.5" fill="#8a8578">ממוצע [\d.]+%',
           f'<text x="854" y="{ypos(base) + 11.4:.1f}" text-anchor="end" '
           f'font-family="Rubik,sans-serif" font-size="11.5" fill="#8a8578">ממוצע {base}%')
art = swap(art, r'130 ימי מסחר אחרונים, החל ב-[\d.]+',
           f"130 ימי מסחר אחרונים, החל ב-{start:%d.%m.%Y}")

# ------------------------------------------------------------------ ring gauge
arc = round(chance / DIAL * CIRC, 1)
art = swap(art, r'stroke-dasharray="[\d.]+ 502\.65"', f'stroke-dasharray="{arc} 502.65"')
art = swap(art, r'(?<=@keyframes sweep \{ from \{ stroke-dashoffset: )[\d.]+', str(arc))
art = swap(art, r'(?<=font-size="40" font-weight="700" fill="#2a2823">)[\d.]+%', f"{chance}%")
art = swap(art, r'ציון גולמי: [\d.]+', f"ציון גולמי: {mss}")

ang = math.radians(base / DIAL * 360)          # the dial starts at twelve o'clock
tick = [(100 + r * math.sin(ang), 100 - r * math.cos(ang)) for r in (70, 91)]
art = swap(art, r'<line x1="[\d.]+" y1="[\d.]+" x2="[\d.]+" y2="[\d.]+" '
                r'stroke="#9a9484" stroke-width="2\.4"',
           f'<line x1="{tick[0][0]:.1f}" y1="{tick[0][1]:.1f}" '
           f'x2="{tick[1][0]:.1f}" y2="{tick[1][1]:.1f}" '
           'stroke="#9a9484" stroke-width="2.4"')
art = swap(art, r'הקו הדק = [\d.]+%', f"הקו הדק = {base}%")

# --------------------------------------------------------------- band bar pill
here = next(x for lo_b, hi_b, x in BANDS if lo_b <= mss < hi_b)
pill = one(r'<rect x="(\d+)" y="[\d.]+" width="90" height="20" rx="10"', art)
assert int(pill.group(1)) == here + 25, (
    f"the 'here' pill sits on the bar at x={int(pill.group(1)) - 25}, "
    f"today's MSS {mss} belongs on the bar at x={here}")

# ------------------------------------------------------------- context cards
# Sentiment, debt, breadth - in page order. Two of the three share one neutral
# stroke, so they are found by position and never by colour.
cards = [[float(r["fear_greed"]) for r in rows("fear.csv")][-CARD["n"]:],
         [float(r["total"]) / 1e12 for r in rows("debt.csv")][-CARD["n"]:],
         [float(r["s5fi"]) for r in rows("breadth.csv")][-CARD["n"]:]]
for values in cards:
    assert len(values) == CARD["n"], f"only {len(values)} readings for a context card"

pattern = re.compile(r'(<polyline fill="none" stroke="#[0-9a-f]{6}" stroke-width="2\.4"'
                     r'[^>]*?points=")[^"]+("/>\s*<circle cx="260" cy=")[\d.]+', re.S)
spots = list(pattern.finditer(art))
assert len(spots) == 3, f"{len(spots)} context cards found"
for spot, values in zip(reversed(spots), reversed(cards)):   # from the end, so
    pts_c, ypos_c, _, _ = plot(values, CARD)                 # spans stay valid
    art = (art[:spot.start()] + spot.group(1) + pts_c + spot.group(2)
           + str(ypos_c(values[-1])) + art[spot.end():])

fear, debt, s5fi = (c[-1] for c in cards)
mood = ("פחד קיצוני" if fear < 25 else "פחד" if fear < 45 else "ניטרלי"
        if fear < 55 else "תאווה" if fear < 75 else "תאווה קיצונית")
art = swap(art, r'(?<=padding:4px 12px">)[\d.]+ · (?:פחד קיצוני|פחד|ניטרלי|תאווה קיצונית|תאווה)',
           f"{fear:.0f} · {mood}")
art = swap(art, r'[\d.]+ טריליון \$', f"{debt:.2f} טריליון $")
art = swap(art, r'[\d.]+% מעל ממוצע 50', f"{s5fi:.1f}% מעל ממוצע 50")

quarter = [float(r["total"]) / 1e12 for r in rows("debt.csv")][-64:]
art = swap(art, r'עלייה של כ-[\d,]+ מיליארד \$',
           f"עלייה של כ-{round((quarter[-1] - quarter[0]) * 1000):,} מיליארד $")

PAGE.write_text(art, encoding="utf-8")
print(f"{today['date']} chance {chance} mss {mss} trend {trend:+.1f} {today['regime']}")
print(f"chart {lo}-{hi} base {base} baseline y {ypos(base)} "
      f"last y {ypos(window[-1])} from {start}")
print(f"gauge arc {arc} tick {base / DIAL * 360:.0f}deg  band x={here}")
print(f"fear {fear} {mood} · debt {debt:.3f}T · s5fi {s5fi}")
