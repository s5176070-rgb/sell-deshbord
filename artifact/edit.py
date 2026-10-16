"""The prose the charts cannot carry: dates, the premarket strip, the arrows.

refresh.py redraws every curve and every number that comes straight from
score.csv. What is left is the wording around them, which changes shape and not
just value - a bucket sentence, a market row that says open or closed, and two
arrow glyphs that have to turn with the sign of what they describe.

Edit the constants at the top, run once, and read the asserts if it refuses.
"""
from pathlib import Path

PAGE = Path(__file__).parent / "page.html"

DAY = "15.10.2026"          # the session the model has scored
NEXT = "16.10"              # the session whose open gap is showing
GAP = "‎-0.08%"        # that gap
LAST = "‎+0.33%"       # how the scored session closed
TREND = "‎+5.5"        # MSS against five readings back
SPX, VIX, DVIX = "‎+0.33%", "16.46", "‎-2.4%"

UP = ('<path d="M4 18 L10 12 L14 16 L20 8"/><path d="M14 8 H20 V14"/>')
DOWN = ('<path d="M4 9 L10 15 L14 11 L20 18"/><path d="M14 18 H20 V12"/>')

art = PAGE.read_text(encoding="utf-8")


def sub(old, new):
    global art
    assert art.count(old) == 1, f"{art.count(old)} matches: {old[:70]}"
    art = art.replace(old, new)


sub(">14.10.2026</div>", f">{DAY}</div>")
sub("מודל: נתוני 14.10.2026", f"מודל: נתוני {DAY}")
sub("פתיחת המסחר · 15.10, טרם נפתח", f"פתיחת המסחר · {NEXT}, טרם נפתח")
sub('padding:4px 12px">פער פתיחה ‎+0.13%', f'padding:4px 12px">פער פתיחה {GAP}')
sub("סגירה אחרונה ‎-1.11% · 14.10", f"סגירה אחרונה {LAST} · {DAY[:5]}")

# Same bucket as yesterday, so only the Tuesday-night aside goes: the futures
# that touched -1.79% are two sessions back now, and the page should not keep
# pointing at them as if they were this morning.
sub("פתיחה שטוחה כזו (‎±0.25%, 7,826 ימים מאז 1990): ‎2.6% נסגרו "
    "‎2%- ומטה באותו יום, ‎15.0% לוו בנפילה של ‎5% תוך 20 "
    "מפגשים — כלומר בערך כמו יום רגיל. בשעות הלילה החוזים היו ב-‎1.79%-, "
    "הקטגוריה הנדירה בטבלה, והתאוששו משם. הפרימרקט לא נכנס לציון.",
    "פתיחה שטוחה כזו (‎±0.25%, 7,826 ימים מאז 1990): ‎2.6% נסגרו "
    "‎2%- ומטה באותו יום, ‎15.0% לוו בנפילה של ‎5% תוך 20 "
    "מפגשים — כלומר בערך כמו יום רגיל. הפרימרקט לא נכנס לציון.")

# The score is still climbing, so the trend arrow keeps pointing up and only
# its number moves.
sub('<span style="font-size:13px;font-weight:600">עולה 5 ימים · ‎+8.5</span>',
    f'<span style="font-size:13px;font-weight:600">עולה 5 ימים · {TREND}</span>')

# The index closed up, so the market row's arrow turns over.
sub(f'{DOWN}</svg>\n          <span style="font-size:13px;font-weight:600">'
    'המסחר ננעל: S&amp;P ‎-1.11% · VIX 16.87 (‎+10.5%)</span>',
    f'{UP}</svg>\n          <span style="font-size:13px;font-weight:600">'
    f'המסחר ננעל: S&amp;P {SPX} · VIX {VIX} ({DVIX})</span>')

PAGE.write_text(art, encoding="utf-8")
print("ok")
