"""Redraw the shareable page in this directory from today's model output.

`page.html` is the page published to the two artifact URLs. It is tracked, not
generated: nothing in the repository can rebuild it from scratch, so losing it
means losing the design. This script only rewrites what is inside it.

Its predecessors were one script per chart, kept in a temporary directory. That
directory was cleared when the app quit and they were gone, which is why these
files live in the repository instead.

Geometry is the page's own, recovered from the published SVG and kept exactly:
  history chart  viewBox 860x200, 130 points, floor y=176.4, span 152.8
  context cards  viewBox 260x70,   60 points, floor y=66.0,  span 62.0
  ring gauge     r=80, circumference 502.65, dial full scale 40%

The band bars are NOT redrawn. Their heights come from the calibration window,
which ends twenty sessions back and does not move day to day. The pill saying
which band today sits in does move, and that is handled.

Everything here is a function of the data, including the wording that has a
sign or a date in it - the trend arrow, the market row, the premarket strip.
What is left for edit.py is prose that takes a judgement: how to describe the
week, and what the sentiment reading means. That split is the whole point: a
refresh nobody reviews must not be able to leave an arrow pointing the wrong
way.

Run from the repository root, after check.py has written today's row:

    python check.py
    python artifact/refresh.py

Safe to run twice. serve.py runs both for the button on the page.
"""
import csv
import json
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).parent
PROJECT = HERE.parent
PAGE = HERE / "page.html"

CHART = dict(w=860.0, n=130, floor=176.4, span=152.8)
CARD = dict(w=260.0, n=60, floor=66.0, span=62.0)
CIRC, DIAL = 502.65, 40.0
BANDS = [(0, 45, 40), (45, 70, 220), (70, 85, 400), (85, 101, 580)]
REGIME_WORD = {"NORMAL": "רגוע", "WATCH": "ערנות",
               "ELEVATED": "מתוח", "CRITICAL": "קריטי"}
UP = '<path d="M4 18 L10 12 L14 16 L20 8"/><path d="M14 8 H20 V14"/>'
DOWN = '<path d="M4 9 L10 15 L14 11 L20 18"/><path d="M14 18 H20 V12"/>'

sys.path.insert(0, str(PROJECT))
import pandas as pd  # noqa: E402
import cvs  # noqa: E402
import eval as ev  # noqa: E402  (the project's module, shadowing nothing we use)
import premarket as pm  # noqa: E402


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
    assert len(found) == 1, f"{len(found)} matches for {pattern[:60]}"
    return re.search(pattern, art, flags)


def swap(art, pattern, new, flags=0):
    m = one(pattern, art, flags)
    return art[:m.start()] + new + art[m.end():]


def pct(x, places=2):
    """A signed percentage with the mark that keeps it readable inside RTL."""
    return f"‎{x:+.{places}f}%"


# ---------------------------------------------------------------- model output
score = rows("score.csv")
today = score[-1]
chance, mss = float(today["chance_pct"]), float(today["percentile"])
regime = today["regime"]
day = date.fromisoformat(today["date"])
meta = json.load(open(PROJECT / "score_meta.json", encoding="utf-8"))
assert meta["data_as_of"] == today["date"], "score.csv and score_meta.json disagree"
assert regime in REGIME_WORD, f"no Hebrew word for regime {regime}"

trend = mss - float(score[-6]["percentile"])
window = [float(r["chance_pct"]) for r in score[-CHART["n"]:]]
assert len(window) == CHART["n"], f"only {len(window)} rows of history"
start = date.fromisoformat(score[-CHART["n"]]["date"])

# The dashed mean is the realised rate over the calibrated window, not a
# constant. Recompute it so a doc can never outlive the code.
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
# The bars are left alone, but the pill that says "today is here" moves between
# them whenever the score crosses a band edge.
here = next(x for lo_b, hi_b, x in BANDS if lo_b <= mss < hi_b)
top = float(one(rf'<rect x="{here}" y="([\d.]+)" width="140"', art).group(1))
art = swap(art, r'<rect x="\d+" y="[\d.]+" width="90" height="20" rx="10"',
           f'<rect x="{here + 25}" y="{top - 20.6:.1f}" width="90" height="20" rx="10"')
art = swap(art, r'<text x="\d+" y="[\d.]+" text-anchor="middle" '
                r'font-family="Rubik,sans-serif" font-size="11\.5" '
                r'font-weight="700" fill="#fff">היום כאן',
           f'<text x="{here + 70}" y="{top - 6.1:.1f}" text-anchor="middle" '
           'font-family="Rubik,sans-serif" font-size="11.5" '
           'font-weight="700" fill="#fff">היום כאן')

# The bar the pill now sits on also supplies the band's own range and rate,
# which the sentence under the chart quotes. Reading them back off the chart
# keeps the two from ever disagreeing.
band_rate = float(one(rf'<text x="{here + 70}" y="98"[^>]*>([\d.]+)%', art).group(1))
band_range = one(rf'<text x="{here + 70}" y="168"[^>]*>([^<]+)</text>',
                 art).group(1).split(" · ")[0]

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

# ---------------------------------------------------- dates, regime, the trend
art = swap(art, r'(?<=border:1px solid #e4e0d4;padding:7px 16px">)[\d.]+(?=</div>)',
           f"{day:%d.%m.%Y}")
art = swap(art, r'מודל: נתוני [\d.]+', f"מודל: נתוני {day:%d.%m.%Y}")
art = swap(art, r'(?:NORMAL|WATCH|ELEVATED|CRITICAL) · \S+(?=</div>)',
           f"{regime} · {REGIME_WORD[regime]}")
art = swap(art, r'<path d="M4 (?:18|9)[^/]*/><path d="M14 (?:8|18)[^/]*/></svg>\n'
                r'          <span style="font-size:13px;font-weight:600">'
                r'(?:עולה|יורד) 5 ימים · [^<]*</span>',
           f'{UP if trend >= 0 else DOWN}</svg>\n'
           '          <span style="font-size:13px;font-weight:600">'
           f'{"עולה" if trend >= 0 else "יורד"} 5 ימים · ‎{trend:+.1f}</span>')

# The band sentence and the plain-language line both name the regime, and both
# have to name the exit threshold that is keeping it: a score of 67 reading
# ELEVATED is only explicable if the page says 65 is where it would let go.
exit_at = meta["bands"].get(regime, {}).get("exit")
held = f" מצב {regime} נשמר עד ירידה מתחת ל-{exit_at}." if exit_at else ""
art = swap(art, r'היום הציון ב-[^<]*',
           f"היום הציון ב-{band_range}: ברמה הזו שיעור הנפילות ההיסטורי הוא "
           f"{band_rate}%.{held}")
because = (f" מצב {regime} נשמר בגלל סף היציאה {exit_at}."
           if exit_at and mss < meta["bands"][regime]["enter"] else "")
art = swap(art, r'הציון [\d.]+, והמגמה מול חמש תצפיות אחורה [^<]*',
           f"הציון {mss}, והמגמה מול חמש תצפיות אחורה "
           f"{'עולה' if trend >= 0 else 'יורדת'}.{because} "
           f"ההסתברות שמפרסם המודל היא {chance}%.")

# --------------------------------------------------- the market, as it stands
# cvs.closes is the model's own price source, so the row can never disagree
# with the score about what the index did.
px = cvs.closes(["^GSPC", "^VIX"], "2026-01-01")[0].dropna()
spx_chg = (px["^GSPC"].iloc[-1] / px["^GSPC"].iloc[-2] - 1) * 100
vix, vix_chg = px["^VIX"].iloc[-1], (px["^VIX"].iloc[-1] / px["^VIX"].iloc[-2] - 1) * 100
session = pm.market_session(pd.Timestamp.now(tz="Asia/Jerusalem"))
open_now = session == "מסחר רגיל"
art = swap(art, r'<path d="M4 (?:18|9)[^/]*/><path d="M14 (?:8|18)[^/]*/></svg>\n'
                r'          <span style="font-size:13px;font-weight:600">'
                r'(?:שוק פתוח|המסחר ננעל): S&amp;P [^<]*</span>',
           f'{UP if spx_chg >= 0 else DOWN}</svg>\n'
           '          <span style="font-size:13px;font-weight:600">'
           f'{"שוק פתוח" if open_now else "המסחר ננעל"}: S&amp;P {pct(spx_chg)} · '
           f'VIX {vix:.2f} ({pct(vix_chg, 1)})</span>')

# ------------------------------------------------------------ premarket strip
# The futures quote, its bucket and what that bucket preceded, all from the
# table premarket.py prints, so the strip can never drift from the module.
# The futures are not the open gap and the page says so: the buckets were cut
# on realised open gaps, and this is the closest live proxy for one.
quote = pm.live()
fut = float(quote["ES=F"]) * 100
at = pd.Timestamp(quote["ES=F_at"]).tz_convert("Asia/Jerusalem")
last = px.index[-1].date()   # the same series the market row quotes, so the
                             # two chips can never report different moves

# Which session the strip is about is a question about the clock, not about
# the quote: on a Saturday morning the newest futures print is still Friday's,
# so dating the strip from the quote would announce a session that has already
# closed as one that has not opened.
now = pd.Timestamp.now(tz="Asia/Jerusalem")
if open_now:
    head, second = f"פתיחת המסחר · {now:%d.%m}, המסחר פתוח", f"כרגע {pct(spx_chg)}"
else:
    second = f"סגירה אחרונה {pct(spx_chg)} · {last:%d.%m}"
    if now.weekday() >= 5:
        monday = now.date() + timedelta(days=7 - now.weekday())
        head = f"פתיחת המסחר · {monday:%d.%m}, סוף שבוע"
    elif last == now.date():
        head = f"פתיחת המסחר · {last:%d.%m}, המסחר ננעל"
    else:
        head = f"פתיחת המסחר · {now:%d.%m}, טרם נפתח"

art = swap(art, r'(?<=font-size:14px;font-weight:700">)פתיחת המסחר · [^<]*', head)
art = swap(art, r'(?<=padding:4px 12px">)(?:כרגע|סגירה אחרונה) [^<]*', second)

# A futures print only indicates the next open if it was made after the last
# session ended. On a Saturday the newest print is Friday's, minutes before
# that close - quoting it as a gap, with a bucket's hit rate beside it, would
# read as a claim about Monday that nobody has made. So the strip says there is
# no reading yet rather than dressing up a close as a premarket.
if at.date() > last:
    label, _ = pm.bucket_of(fut)
    name, _, span_text = label.partition(", ")
    row = pm.table(offline=True).set_index("מה קרה לפני הפתיחה").loc[label]
    chip = f"חוזי S&P {pct(fut)} · {at:%H:%M}"
    told = (f"חוזי S&P בשעה {at:%H:%M} ב-{at:%d.%m}: {pct(fut)}, בקטגוריית "
            f"{name} ({span_text}). במדגם {int(row['ימים']):,} ימים: "
            f"‎{row['ירד 2%+ באותו יום']}% נסגרו בירידה של 2% ומעלה, "
            f"ו-{row['נפילה של 5% ב-20 יום']}% לוו בנפילה של 5% בתוך 20 מפגשים. "
            "זו השוואה לפערי פתיחה היסטוריים; החוזים עדיין אינם פער הפתיחה "
            "בפועל. הפרימרקט לא נכנס לציון.")
else:
    chip = "חוזי S&P · אין עדיין קריאה"
    told = (f"הציטוט האחרון של החוזים הוא מ-{at:%d.%m} בשעה {at:%H:%M}, כלומר "
            f"מתוך מפגש {last:%d.%m} עצמו ולא לפניו — הוא אומר איפה אותו מפגש "
            "ננעל, לא איפה המפגש הבא ייפתח. פער פתיחה למפגש הבא עדיין אין, "
            "ולכן גם אין קטגוריה היסטורית להציג. הפרימרקט לא נכנס לציון.")
art = swap(art, r'(?<=padding:4px 12px">)חוזי S&P [^<]*', chip)
art = swap(art, r'(?<=font-size:12px;margin-top:8px">)(?:חוזי S&P בשעה|הציטוט האחרון)[^<]*',
           told)

# ------------------------------------------------- what the sentiment card says
prev_fear = cards[0][-2]
moved = ("עלה" if fear > prev_fear else "ירד" if fear < prev_fear else "לא זז")
art = swap(art, r'(?<=font-size:12px;margin-top:6px">)הסנטימנט [^<]*',
           f"הסנטימנט {moved} ל-{fear:.1f}: {mood}. נתון "
           f"{date.fromisoformat(rows('fear.csv')[-1]['date']):%d.%m}; "
           "לא נכנס לציון — רק להקשר.")

PAGE.write_text(art, encoding="utf-8")
print(f"{today['date']} chance {chance} mss {mss} trend {trend:+.1f} {regime}")
print(f"chart {lo}-{hi} base {base} baseline y {ypos(base)} "
      f"last y {ypos(window[-1])} from {start}")
print(f"gauge arc {arc}  band {band_range} ({band_rate}%, 1 in {round(100 / band_rate)})")
print(f"market {session}: S&P {spx_chg:+.2f}% VIX {vix:.2f} ({vix_chg:+.1f}%)")
print(f"futures {fut:+.2f}% at {at:%H:%M}"
      + (f" -> {label}" if at.date() > last else " (last session, no premarket yet)"))
print(f"fear {fear:.1f} {mood} · debt {debt:.3f}T · s5fi {s5fi}")
