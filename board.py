"""The dashboard's presentation layer, kept apart from anything that measures.

stress.py decides what is true; this file decides how it looks. The split
matters because the two change for different reasons - a colour is not allowed
to become a finding, and a finding must not need a redesign to be corrected.

Colour here is assigned by the job each series does, and the palette was run
through the data-viz validator against this page's own card surface rather than
picked by eye:

  subject series   #ec4899   the thing the panel is about
  reference ramp   #93c5fd -> #3b82f6   one hue, ordered: the 50-, 150- and
                   200-day averages read as a sequence because their colour does
  second peer      #d97706   validated all-pairs against the subject
  score bands      the fixed status scale, because 0-44 through 85+ *means*
                   good-to-bad, and a scale that means that wears status tokens
                   rather than a series hue - always with its label beside it

Dark only, on purpose: the reference design is dark, and a palette validated
against #232640 is not automatically valid against a light surface. Every
colour is painted explicitly rather than inherited.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

# The horizons the forward table is actually built with. Imported rather than
# retyped: the column headers here and the columns forward() produces have to be
# the same list, and two hardcoded copies drift silently.
from cvs import HORIZONS

# Only for the debt panel: the level is a display, not a factor - stress.py
# builds the pace readings that are actually scored.
import debt
import fear

SURFACE = "#232640"
SUBJECT = "#ec4899"
RAMP = ["#93c5fd", "#60a5fa", "#3b82f6"]
PEER = "#d97706"
# good -> critical. Reserved: never reused as a series colour.
STATUS = {"calm": "#0ca30c", "watch": "#fab219", "elevated": "#ec835a", "critical": "#d03b3b"}
BAND_STATUS = {"0-44": "calm", "45-69": "watch", "70-84": "elevated", "85+": "critical"}
# The page is Hebrew, and %b prints English month names whatever the locale of
# the machine that happens to build the file. Formatting them here keeps the
# output identical on any box.
RU_MONTHS = ["ינו", "פבר", "מרץ", "אפר", "מאי", "יונ",
             "יול", "אוג", "ספט", "אוק", "נוב", "דצמ"]


def ru_date(ts, year: bool = True) -> str:
    out = f"{ts.day} ב{RU_MONTHS[ts.month - 1]}"
    return f"{out} {ts.year}" if year else out
BAND_MARK = {"0-44": "&#9679;", "45-69": "&#9650;", "70-84": "&#9670;", "85+": "&#9632;"}

CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --page:#171a2e; --card:#232640; --rail:#12142a; --line:#2e3252; --base:#3a3f66;
  --ink:#ffffff; --ink2:#b9bdd4; --mut:#8189a6;
  --subject:#ec4899; --peer:#d97706;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --crit:#d03b3b;
}
html{color-scheme:dark}
body{background:var(--page);color:var(--ink);margin:0;
  font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:inherit;text-decoration:none}
.shell{display:grid;grid-template-columns:198px minmax(0,1fr);min-height:100vh}
.shell>div{min-width:0}

.rail{background:var(--rail);padding:20px 0;border-right:1px solid var(--line)}
.brand{font-size:19px;font-weight:700;letter-spacing:.06em;color:var(--subject);padding:0 20px 22px}
.rail .sec{font-size:10.5px;letter-spacing:.14em;color:var(--mut);padding:16px 20px 7px;text-transform:uppercase}
.rail a{display:block;padding:8px 20px;color:var(--ink2);font-size:13.5px;border-left:3px solid transparent}
.rail a:hover{background:#1b1e38;color:var(--ink)}
.rail a.on{background:#2a2d52;color:var(--ink);border-left-color:var(--subject);font-weight:600}

.top{display:flex;align-items:center;gap:12px;flex-wrap:wrap;
  padding:16px 24px;border-bottom:1px solid var(--line);background:var(--card)}
.top h1{font-size:16px;margin:0;font-weight:600}
.top h1 span{color:var(--subject)}
.top .spacer{flex:1}
.chip{font-size:12px;color:var(--ink2);background:var(--page);border:1px solid var(--line);
  border-radius:6px;padding:5px 10px}
.chip b{color:var(--ink);font-weight:600}
main{padding:20px 24px 40px}
h2{font-size:11.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);
  margin:26px 0 10px;font-weight:600}
h2:first-of-type{margin-top:4px}

.row{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(196px,1fr))}
/* The hero gets its own full-width band and the four evidence tiles get a clean
   row of four beneath it. Squeezing all five into one auto-fit row means picking
   a track size that is either too narrow for the gauge or too wide for six
   tracks to fit - it wrapped one tile onto a second line at every width tried.
   Two rows always work, at any width. */
.hero-band{margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
  padding:14px 16px;min-width:0}
.card .lbl{font-size:12.5px;color:var(--ink2);margin-bottom:2px}
.card .sub{font-size:11.5px;color:var(--mut)}
.val{font-size:30px;font-weight:600;line-height:1.1;margin:6px 0 2px}
.val small{font-size:14px;font-weight:500;color:var(--ink2);margin-left:3px}
.hero-wrap{display:flex;gap:18px;align-items:center}
.hero-fig{font-size:52px;font-weight:600;line-height:1}
.hero-meta{display:flex;flex-direction:column;gap:3px;font-size:12.5px;color:var(--ink2)}
.hero-meta b{color:var(--ink)}
.tag{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;
  padding:3px 9px;border-radius:20px;border:1px solid currentColor;width:fit-content}

.panels{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.panel h3{font-size:13.5px;margin:0 0 2px;font-weight:600}
.panel .cap{color:var(--mut);font-size:11.5px;margin:0 0 10px}
.plot{position:relative}
.plot svg{width:100%;height:132px;display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;color:var(--ink2);margin-top:9px}
.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:5px;border-radius:1px}

.tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .08s;
  background:var(--rail);border:1px solid var(--base);border-radius:7px;padding:7px 9px;
  font-size:11.5px;color:var(--ink);white-space:nowrap;z-index:5;
  box-shadow:0 6px 18px rgba(0,0,0,.45)}
.tip .d{color:var(--mut);margin-bottom:3px}
.tip .r{display:flex;gap:7px;align-items:center;font-variant-numeric:tabular-nums}
.tip .r i{width:9px;height:9px;border-radius:50%;flex:none}
.tip .r span{color:var(--ink2)}
.tip .r b{margin-left:auto;font-weight:600}

.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:9px 13px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
th{color:var(--mut);font-weight:500;font-size:11.5px;letter-spacing:.05em;text-transform:uppercase}
tr:last-child td{border-bottom:0}
tr.now td{background:#2a2d52}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:-1px}
.note{color:var(--mut);font-size:11.5px;margin-top:9px;max-width:78ch}
.note em{color:var(--ink2);font-style:normal}
/* Twenty-three factors is a long column. Two columns on a wide screen keeps the
   whole set on one screen, which is the only way it gets read at all. */
.factors{columns:2;column-gap:26px}
@media (max-width:900px){.factors{columns:1}}
.bar{display:grid;grid-template-columns:132px 1fr 34px;gap:10px;align-items:center;
  margin:7px 0;font-size:12.5px;color:var(--ink2);break-inside:avoid}
.bar .track{height:7px;background:var(--line);border-radius:4px;overflow:hidden}
.bar .fill{height:100%;border-radius:4px}
.bar .num{text-align:right;color:var(--ink);font-variant-numeric:tabular-nums}
/* Wide content — tables, the chart grid — scrolls inside its own box. The page
   body never does. */
.panels{min-width:0}
.panel{min-width:0}
@media (max-width:820px){
  .shell{grid-template-columns:1fr}
  .rail{display:none}
}
"""

# One delegated listener per plot: nearest index from the pointer's x fraction,
# a crosshair, and a tooltip. The dots carry a surface-coloured ring so they stay
# legible where they cross a line, and the ring is part of the hit target.
JS = """
document.querySelectorAll('.plot[data-series]').forEach(function(plot){
  var data = JSON.parse(plot.dataset.series), svg = plot.querySelector('svg');
  var tip = plot.querySelector('.tip'), cross = svg.querySelector('.crosshair');
  var dots = svg.querySelectorAll('.hoverdot');
  function hide(){ tip.style.opacity=0; cross.setAttribute('opacity',0);
    dots.forEach(function(d){ d.setAttribute('opacity',0); }); }
  plot.addEventListener('pointerleave', hide);
  plot.addEventListener('pointermove', function(e){
    var box = svg.getBoundingClientRect();
    var frac = Math.min(1, Math.max(0, (e.clientX - box.left) / box.width));
    var i = Math.round(frac * (data.dates.length - 1));
    var x = i / (data.dates.length - 1) * 1000;
    cross.setAttribute('x1', x); cross.setAttribute('x2', x); cross.setAttribute('opacity', 1);
    var rows = '';
    data.series.forEach(function(s, k){
      var v = s.values[i], dot = dots[k];
      if (v === null || v === undefined) { if (dot) dot.setAttribute('opacity', 0); return; }
      if (dot) { dot.setAttribute('cx', x); dot.setAttribute('cy', s.y[i]); dot.setAttribute('opacity', 1); }
      rows += '<div class="r"><i style="background:' + s.color + '"></i><span>' +
              s.name + '</span><b>' + s.fmt[i] + '</b></div>';
    });
    tip.innerHTML = '<div class="d">' + data.dates[i] + '</div>' + rows;
    tip.style.opacity = 1;
    var w = tip.offsetWidth, left = e.clientX - box.left + 14;
    if (left + w > box.width) left = e.clientX - box.left - w - 14;
    tip.style.left = Math.max(0, left) + 'px';
    tip.style.top = '6px';
  });
});
"""

H = 132.0  # plot height in user units; the viewBox is 1000 x H
PAD_T, PAD_B = 10.0, 12.0


def _fmt(v: float) -> str:
    a = abs(v)
    if a >= 1000:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:,.2f}"
    return f"{v:,.4g}"


def plot(series: dict[str, tuple[pd.Series, str]], days: int = 500,
         refs: list[float] | None = None, unit: str = "") -> str:
    """One panel's chart: shared axis, hairline refs, and a hover layer.

    `series` maps a name to (values, colour). Everything shares one y-axis - the
    caller is responsible for only passing series that belong on one, because a
    second axis is the fastest way to make two unrelated shapes look correlated.
    """
    cut = {k: (v.dropna().tail(days), c) for k, (v, c) in series.items()}
    cut = {k: v for k, v in cut.items() if len(v[0]) > 1}
    if not cut:
        return '<div class="plot"></div>'
    lo = min(v.min() for v, _ in cut.values())
    hi = max(v.max() for v, _ in cut.values())
    for r in refs or []:
        lo, hi = min(lo, r), max(hi, r)
    span = (hi - lo) or 1.0

    def y(v: float) -> float:
        return H - PAD_B - (v - lo) / span * (H - PAD_T - PAD_B)

    n = max(len(v) for v, _ in cut.values())
    dates = next(v for v, _ in cut.values() if len(v) == n).index
    body = ""
    for r in refs or []:
        body += (f'<line x1="0" y1="{y(r):.1f}" x2="1000" y2="{y(r):.1f}" stroke="var(--base)" '
                 f'stroke-width="1" vector-effect="non-scaling-stroke"/>'
                 f'<text x="5" y="{y(r) - 4:.1f}" font-size="9" fill="var(--mut)">{r:g}{unit}</text>')

    payload = {"dates": [ru_date(d) for d in dates], "series": []}
    for name, (v, colour) in cut.items():
        off = n - len(v)  # a shorter series starts further right, never stretched
        xs = [(off + j) / (n - 1) * 1000 for j in range(len(v))]
        ys = [y(val) for val in v]
        body += (f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, ys))}" '
                 f'fill="none" stroke="{colour}" stroke-width="2" stroke-linejoin="round" '
                 f'stroke-linecap="round" vector-effect="non-scaling-stroke"/>')
        pad = [None] * off
        payload["series"].append({
            "name": name, "color": colour,
            "values": pad + [float(x) for x in v],
            "fmt": pad + [_fmt(float(x)) + unit for x in v],
            "y": pad + [round(b, 1) for b in ys],
        })
    body += ('<line class="crosshair" x1="0" y1="0" x2="0" y2="%.0f" stroke="var(--ink2)" '
             'stroke-width="1" opacity="0" vector-effect="non-scaling-stroke"/>' % H)
    for _, (_, colour) in cut.items():
        body += (f'<circle class="hoverdot" r="4.5" fill="{colour}" stroke="{SURFACE}" '
                 f'stroke-width="2" opacity="0" vector-effect="non-scaling-stroke"/>')

    keys = "".join(f'<span><i style="background:{c}"></i>{k}</span>' for k, (_, c) in cut.items())
    legend = f'<div class="legend">{keys}</div>' if len(cut) > 1 else ""
    return (f'<div class="plot" data-series=\'{json.dumps(payload)}\'>'
            f'<svg viewBox="0 0 1000 {H:.0f}" preserveAspectRatio="none">{body}</svg>'
            f'<div class="tip"></div></div>{legend}')


def panel(title: str, caption: str, series: dict, **kw) -> str:
    return (f'<div class="card panel"><h3>{title}</h3><p class="cap">{caption}</p>'
            f"{plot(series, **kw)}</div>")


def gauge(value: float, colour: str) -> str:
    """The score as a 240-degree arc. One hero figure per view, and this is it."""
    import math
    r, cx, cy = 52.0, 62.0, 62.0
    start, sweep = 150.0, 240.0

    def point(deg: float) -> tuple[float, float]:
        a = math.radians(deg)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    x0, y0 = point(start)
    x1, y1 = point(start + sweep)
    xv, yv = point(start + sweep * max(0.0, min(100.0, value)) / 100)
    big = 1 if sweep * value / 100 > 180 else 0
    return (f'<svg viewBox="0 0 124 108" style="width:124px;height:108px;flex:none" '
            f'role="img" aria-label="ציון סיכון {value:.0f} מתוך 100">'
            f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 1 1 {x1:.1f},{y1:.1f}" fill="none" '
            f'stroke="var(--line)" stroke-width="9" stroke-linecap="round"/>'
            f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 {big} 1 {xv:.1f},{yv:.1f}" fill="none" '
            f'stroke="{colour}" stroke-width="9" stroke-linecap="round"/></svg>')


REFRESH_JS = """
(function(){
  var quick = document.getElementById('refresh');
  var full  = document.getElementById('analyze');
  var say   = document.getElementById('jobstep');
  if (!quick) return;
  var labels = {refresh: quick.textContent, analyze: full ? full.textContent : ''};

  function lock(on){ quick.disabled = on; if (full) full.disabled = on; }
  function fail(btn, err, label){
    btn.classList.remove('busy');
    btn.classList.add('failed');
    btn.textContent = 'שגיאה';
    say.textContent = String(err && err.message || err);
    setTimeout(function(){
      btn.classList.remove('failed');
      btn.textContent = label;
      say.textContent = '';
      lock(false);
    }, 8000);
  }

  quick.addEventListener('click', async function(){
    lock(true); quick.classList.add('busy'); quick.textContent = 'טוען\\u2026';
    try {
      var r = await fetch('/refresh', {method: 'POST'});
      if (!r.ok) throw new Error(await r.text());
      location.reload();
    } catch (err) {
      // The server keeps serving the last good reading, so the page in front of
      // the viewer is still true - say what broke and leave it up.
      fail(quick, err, labels.refresh);
    }
  });

  if (!full) return;
  full.addEventListener('click', async function(){
    lock(true); full.classList.add('busy'); full.textContent = 'מחשב מחדש\\u2026';
    try {
      var r = await fetch('/analyze', {method: 'POST'});
      if (!r.ok) throw new Error(await r.text());
    } catch (err) { fail(full, err, labels.analyze); return; }
    // Minutes, not seconds, so the page asks what stage it is at rather than
    // holding one request open and hoping nothing times it out.
    var poll = setInterval(async function(){
      try {
        var s = await (await fetch('/status')).json();
        if (s.step) say.textContent = s.step;
        if (!s.running) {
          clearInterval(poll);
          if (s.error) { fail(full, new Error(s.error), labels.analyze); }
          else { say.textContent = 'הושלם'; location.reload(); }
        }
      } catch (err) { clearInterval(poll); fail(full, err, labels.analyze); }
    }, 1500);
  });
})();
"""


BROADSHEET_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap');
:root{
  --color-bg:#f3f2f2; --color-surface:#eae9e9; --color-text:#201e1d;
  --color-accent:#0088b0; --color-accent-2:#d6006c;
  --color-divider:color-mix(in srgb, #201e1d 16%, transparent);
  --color-accent-2-100:#fff1f4; --color-accent-2-800:#790e3d;
  --color-neutral-100:#f8f4f4; --color-neutral-300:#d7d3d3; --color-neutral-800:#444141;
  --font-heading:"Source Serif 4",system-ui,sans-serif; --font-body:"Source Serif 4",system-ui,sans-serif;
  --space-1:5px; --space-2:10px; --space-3:15px; --space-4:20px; --space-6:30px; --space-8:40px;
  --radius-sm:1px; --radius-md:2px;
  --good:#1a7f4b; --warn:#b5820a; --serious:#b5560a; --crit:#b3261e;
  /* Aliases so plot()/panel() - built for the dark dashboard - render correctly
     here too, unchanged: they paint with these var names directly. */
  --line:var(--color-divider); --base:var(--color-divider);
  --mut:color-mix(in srgb, var(--color-text) 55%, transparent);
  --ink:var(--color-text); --ink2:color-mix(in srgb, var(--color-text) 75%, transparent);
}
html{color-scheme:light}
body{background:var(--color-bg);color:var(--color-text);margin:0;font:15px/1.55 var(--font-body)}
a{color:var(--color-accent);text-underline-offset:3px}
h1,h2,h3,h4{font-family:var(--font-heading);font-weight:600;line-height:1.12;
  letter-spacing:-0.015em;margin:0 0 var(--space-2)}
h2{font-size:26px} h3{font-size:18px}
.text-muted,.note{color:color-mix(in srgb, var(--color-text) 55%, transparent)}

.nav{display:flex;align-items:center;gap:var(--space-4);padding:var(--space-3) var(--space-4)}
.nav-brand{font-family:var(--font-heading);font-weight:600;font-size:18px}

.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;cursor:pointer;
  font-family:var(--font-heading);font-weight:600;font-size:14px;line-height:1.2;color:var(--color-text);
  background:transparent;border:1px solid transparent;padding:var(--space-2) 18px;border-radius:var(--radius-md)}
.btn-primary{background:var(--color-accent);color:#fff}
.btn-primary:hover{background:#006786}
.btn-secondary{border-color:var(--color-divider)}
.btn-secondary:hover{background:color-mix(in srgb, var(--color-text) 7%, transparent)}
.btn[disabled]{cursor:progress;opacity:.7}
.btn.busy{background:var(--color-neutral-300);color:var(--color-text)}
.btn.failed{background:var(--crit);color:#fff}
@media (prefers-reduced-motion:no-preference){
  .btn.busy{animation:pulse 1.1s ease-in-out infinite}
  @keyframes pulse{50%{opacity:.55}}
}

.card{display:flex;flex-direction:column;gap:var(--space-2);padding:var(--space-3);
  border-radius:var(--radius-md);background:var(--color-surface)}
.card-kicker{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--color-accent)}
.card-title{font-family:var(--font-heading);font-weight:600;font-size:20px;line-height:1.2}

.tag{display:inline-flex;align-items:center;font-size:11px;letter-spacing:.02em;padding:3px 10px;
  border-radius:2px}
.tag-accent-2{background:var(--color-accent-2-100);color:var(--color-accent-2-800)}
.tag-neutral{background:var(--color-neutral-100);color:var(--color-neutral-800)}

.only{max-width:1080px;margin:0 auto;padding:var(--space-8) var(--space-6)}
#jobstep{font-size:12.5px;color:var(--color-text);opacity:.7}

/* — the six-chart grid, reusing panel()/plot() from the dark dashboard as-is —
   only the colours above changed underneath them. */
.panels{display:grid;gap:var(--space-3);grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.panel h3{font-size:15px;margin:0 0 2px;font-family:var(--font-heading);font-weight:600}
.panel .cap{color:color-mix(in srgb, var(--color-text) 55%, transparent);font-size:11.5px;margin:0 0 10px}
.plot{position:relative}
.plot svg{width:100%;height:132px;display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:11.5px;
  color:color-mix(in srgb, var(--color-text) 70%, transparent);margin-top:9px}
.legend i{display:inline-block;width:14px;height:2px;vertical-align:middle;margin-right:5px;border-radius:1px}
.tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .08s;
  background:#fff;border:1px solid var(--color-divider);border-radius:7px;padding:7px 9px;
  font-size:11.5px;color:var(--color-text);white-space:nowrap;z-index:5;
  box-shadow:0 6px 18px rgba(32,30,29,.16)}
.tip .d{color:color-mix(in srgb, var(--color-text) 55%, transparent);margin-bottom:3px}
.tip .r{display:flex;gap:7px;align-items:center;font-variant-numeric:tabular-nums}
.tip .r i{width:9px;height:9px;border-radius:50%;flex:none}
.tip .r span{color:color-mix(in srgb, var(--color-text) 70%, transparent)}
.tip .r b{margin-left:auto;font-weight:600}
"""


def score_chart(history: pd.Series, sessions: int = 250) -> str:
    """The score's own history, full window, no hover - a plain read of whether
    today's marked dot sits near the quiet end of the line or the busy one.
    """
    recent = history.dropna().tail(sessions)
    if len(recent) < 2:
        return ""
    w, h, pad = 800.0, 220.0, 12.0

    def y(v: float) -> float:
        return h - pad - v / 100 * (h - 2 * pad)

    n = len(recent)
    xs = [i / (n - 1) * w for i in range(n)]
    ys = [y(float(v)) for v in recent]
    refs = "".join(
        f'<line x1="0" y1="{y(r):.1f}" x2="{w:.0f}" y2="{y(r):.1f}" '
        f'stroke="var(--color-divider)" stroke-width="1"/>'
        f'<text x="4" y="{y(r) - 4:.1f}" font-size="11" fill="var(--color-text)" opacity="0.5">{r:g}</text>'
        for r in (45, 70, 85))
    line = ('<polyline points="' + " ".join(f"{a:.1f},{b:.1f}" for a, b in zip(xs, ys)) +
            '" fill="none" stroke="var(--color-text)" stroke-width="2"/>')
    dot = f'<circle cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="4" fill="var(--color-accent-2)"/>'
    return (f'<svg viewBox="0 0 {w:.0f} {h:.0f}" style="width:100%;height:{h:.0f}px;display:block" '
            f'role="img" aria-label="היסטוריית ציון, {n} מפגשים">{refs}{line}{dot}</svg>')


def simple(score: float, chance_now: float, base: float, ceiling: float, floor: float,
           asof, px: pd.DataFrame, res: pd.DataFrame, chosen: list[str],
           br: pd.DataFrame, days: int = 63,
           live: bool = False, held_back: str | None = None,
           history: pd.Series | None = None, far: dict | None = None,
           ev: pd.DataFrame | None = None,
           span: tuple[int, int] | None = None) -> str:
    """One screen: today's score, its factors, and the track record behind them.
    Broadsheet design system (light, RTL, serif) - the handoff in
    design_handoff_market_stress_dashboard/, recreated with real values.

    `ev` is the walk-forward table `render` already gets. It is optional so an
    older caller still builds a page, and when it is passed this page stops
    being the only one of the two that shows a number without its evidence.

    The band a reading belongs to is `band_of(MSS)`, NOT `band_of(score)`.
    The two are different scales - the score is the calibrated chance stretched
    over 0-100, the bands are cut on the raw percentile - and reading the band
    off the published score puts today in the wrong row.
    """
    last = res.iloc[-1]
    regime = str(last["regime"])
    tag_class = "tag-neutral" if regime == "NORMAL" else "tag-accent-2"
    versus = ("נמוך מהנורמה" if chance_now < base * 0.9 else
              "גבוה מהנורמה" if chance_now > base * 1.1 else "קרוב לנורמה")
    times = chance_now / base if base else 1.0
    # Spelled from the walk-forward's own span. It read "fifteen years" while
    # the record ran 1999-2026, which is the kind of number that goes wrong
    # quietly every time the history moves.
    years_text = f' מאז <span dir="ltr">{span[0]}</span>' if span else ""

    nav_buttons = ('<button id="refresh" type="button" class="btn btn-primary">רענון</button>'
                   '<button id="analyze" type="button" class="btn btn-secondary">חישוב מחדש</button>'
                   '<span id="jobstep"></span>') if live else ""

    readings = sorted(((k, float(last[k])) for k in chosen if pd.notna(last[k])),
                       key=lambda kv: abs(kv[1] - 50), reverse=True)
    top_readings = readings[:8]
    extreme = top_readings[0][0] if top_readings else None
    bars = "".join(
        f'<div style="display:grid;grid-template-columns:1fr 34px;gap:var(--space-2);'
        f'align-items:center;margin-bottom:var(--space-3)">'
        f'<div><div style="font-size:13px;margin-bottom:4px">{k}</div>'
        f'<div style="height:8px;background:var(--color-bg);border-radius:var(--radius-sm);overflow:hidden">'
        f'<div style="height:100%;width:{max(0.0, min(100.0, v)):.0f}%;'
        f'background:{"var(--color-accent-2)" if k == extreme else "var(--color-text)"}"></div></div></div>'
        f'<span style="font-size:13px" dir="ltr">{v:.0f}</span></div>'
        for k, v in top_readings)

    mss5, mss10 = float(last["MSS_5d"]), float(last["MSS_10d"])

    # The track record, on the same page as the reading it justifies. Cut on the
    # raw percentile, which is what the bands are defined over.
    walkforward = ""
    if ev is not None and "all days" in ev.index:
        here = band_of(float(last["MSS"]))
        wf = ev.drop(index="all days")
        # The interval is the spell-based one, not the day-based one: adjacent
        # days share their forward window, so days overstate the sample.
        has_ci = "ci_spells" in ev.columns and "spells" in ev.columns
        cards = "".join(
            f'<div class="card">'
            f'<div class="card-kicker">ציון <span dir="ltr">{b}</span>'
            f'{" &middot; היום" if b == here else ""}</div>'
            f'<div class="card-title" style="color:{band_colour(b)}" dir="ltr">'
            f'{r.rate:.1f}%'
            + (f'<small style="font-size:14px;color:var(--mut)"> &plusmn;{r.ci_spells:.1f}</small>'
               if has_ci and pd.notna(r.ci_spells) else "")
            + f'</div>'
            f'<div class="note" style="font-size:12px;margin-top:4px">'
            f'<span dir="ltr">{r.lift:.2f}&times;</span> מהבסיס &middot; '
            f'<span dir="ltr">{r.days:,.0f}</span> ימים'
            + (f' ב-<span dir="ltr">{r.spells:,.0f}</span> התקפים' if has_ci else "")
            + '</div></div>'
            for b, r in wf.iterrows())
        # Whether the top two bands are separable is a fact about this run's
        # numbers, not a permanent one - so it is read off the intervals rather
        # than asserted in prose that goes stale the next time the table moves.
        top = wf.loc[["70-84", "85+"]] if {"70-84", "85+"} <= set(wf.index) else None
        overlap = ""
        if top is not None and has_ci and top["ci_spells"].notna().all():
            lo_hi = [(r.rate - r.ci_spells, r.rate + r.ci_spells) for _, r in top.iterrows()]
            if lo_hi[0][1] >= lo_hi[1][0] and lo_hi[1][1] >= lo_hi[0][0]:
                overlap = (" שני הפסים העליונים אינם נבדלים זה מזה: הטווחים שלהם "
                           "חופפים, ולכן אי אפשר לומר שאחד מסוכן מהשני.")
        walkforward = f"""
  <h2>המסלול מחוץ למדגם</h2>
  <p class="text-muted" style="margin:0 0 var(--space-3);font-size:14px;max-width:70ch">
    קל לבנות מודל שמנבא מצוין את העבר: מסתכלים על כל ההיסטוריה, בוחרים את מה שעבד,
    ומראים כמה טוב זה &rdquo;ניבא&ldquo;. כאן זה חסום. בכל ינואר הגורמים נבחרים מחדש
    מתוך השנים שכבר הסתיימו, ונמדדים על השנה שאחריהן &mdash; בלי לראות יום אחד קדימה.
    כך נמדדו <span dir="ltr">{int(ev.loc["all days", "days"]):,}</span> ימי מסחר, וכולם
    ללא הצצה. השאלה בכל יום אחת: האם המדד ירד 5% או יותר בעשרים ימי המסחר שאחריו.
    ביום אקראי התשובה חיובית ב-<span dir="ltr">{base:.1f}%</span> מהמקרים; מה שמופיע
    למטה הוא אותה שאלה, מחולקת לפי הציון של אותו יום.</p>
  <div style="display:grid;grid-template-columns:repeat({len(wf)},1fr);
              gap:var(--space-3);margin-bottom:var(--space-3)">{cards}</div>
  <p class="note" style="font-size:12px;margin:0 0 var(--space-8);max-width:70ch">
    הפסים נקבעים לפי הציון הגולמי, והמספר הגדול בראש הדף הוא הציון המכויל &mdash;
    שני סולמות של אותה תופעה, ולכן אין ביניהם התאמה מדויקת.
    המספר שאחרי ה-&plusmn; הוא טווח הביטחון, והוא נספר לפי התקפים ולא לפי ימים:
    חלון החיזוי הוא עשרים יום, כך ששני ימים סמוכים מצביעים על אותה נפילה ואינם שתי
    תצפיות נפרדות. פס עם הרבה ימים אבל מעט התקפים הוא מדגם קטן, גם כשהוא לא נראה
    כזה.{overlap}</p>"""

    since2000 = ""
    if far:
        word = ("רגוע יותר" if far["lift"] < 0.9 else
                "בקו עם" if far["lift"] <= 1.1 else "גרוע יותר מ")
        since2000 = (f'<p class="text-muted" style="font-size:13px;margin:0 0 var(--space-2)">'
                     f'מול 26 שנות היסטוריה: מתוך {far["days"]:,} ימים דומים מאז שנת 2000, '
                     f'<span dir="ltr">{far["near_rate"]:.0%}</span> מהם נפלו 5%+ תוך חודש '
                     f'(לעומת <span dir="ltr">{far["base"]:.0%}</span> ביום אקראי) &mdash; '
                     f'{word} מהרגיל. אחד עשר גורמים לטווח ארוך, כולל התרסקות הדוט-קום ו-2008.</p>')

    return f"""<title>סיכון לנפילת השוק</title>
<style>{BROADSHEET_CSS}</style>
<div dir="rtl" lang="he" style="background:var(--color-bg);color:var(--color-text);min-height:100vh">
<nav class="nav">
  <span class="nav-brand">MSS</span>
  <div style="flex:1"></div>
  {nav_buttons}
</nav>
<main class="only">

  <div style="display:flex;align-items:baseline;gap:var(--space-4);flex-wrap:wrap;margin-bottom:var(--space-1)">
    <h1 style="font-size:88px;margin:0;line-height:1" dir="ltr">{score:.0f}</h1>
    <span class="tag {tag_class}" dir="ltr">{regime}</span>
  </div>
  <p class="text-muted" style="margin:0 0 var(--space-1);font-size:15px">ציון פגיעות מצרפי (MSS), 0&ndash;100</p>
  <p class="text-muted" style="margin:0 0 var(--space-1);font-size:13px">{ru_date(asof)} &middot;
    {len(chosen)} גורמים &middot; שינוי 5 ימים <span dir="ltr">{mss5:+.1f}</span> &middot;
    10 ימים <span dir="ltr">{mss10:+.1f}</span></p>
  {f'<p style="color:var(--warn);font-size:13px;margin:0 0 var(--space-1)">&#9432; {held_back}</p>' if held_back else ''}
  {since2000}
  <p class="text-muted" style="margin:0 0 var(--space-2);font-size:14px;max-width:70ch">
    מה הציון אומר בפועל: מתוך מאה ימים שדומים להיום, <span dir="ltr">{chance_now:.0f}%</span>
    נפלו 5% ומעלה תוך חודש. גם המספר הזה נקרא מול שנים קודמות בלבד: העקומה שממירה
    ציון להסתברות נבנית מחדש בכל שנה, מהימים שכבר הסתיימו, ולא מהשנה שהיא מודדת.</p>
  <p class="text-muted" style="margin:0 0 var(--space-8);font-size:14px;max-width:70ch">
    היום <b style="color:var(--color-text)">{versus}</b> &mdash; פי
    <span dir="ltr">{times:.1f}</span> מההסתברות הרגילה של <span dir="ltr">{base:.0f}%</span>.
    הציון עצמו שווה 0 בערך של <span dir="ltr">{floor:.0f}%</span> ו-100 בערך של
    <span dir="ltr">{ceiling:.0f}%</span> &mdash; היום הכי רגוע והכי קשה{years_text}.</p>

  <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:var(--space-3);margin-bottom:var(--space-8)">
    <div class="card"><div class="card-kicker">ציון</div><div class="card-title" dir="ltr">{score:.0f}</div></div>
    <div class="card"><div class="card-kicker">רג׳ים</div><div class="card-title" dir="ltr">{regime}</div></div>
    <div class="card"><div class="card-kicker" dir="ltr">P(-5% ב-20d)</div><div class="card-title" dir="ltr">{chance_now:.0f}%</div></div>
    <div class="card"><div class="card-kicker">&Delta; 5 ימים</div><div class="card-title" dir="ltr">{mss5:+.1f}</div></div>
    <div class="card"><div class="card-kicker">&Delta; 10 ימים</div><div class="card-title" dir="ltr">{mss10:+.1f}</div></div>
    <div class="card"><div class="card-kicker">פיזור גורמים</div><div class="card-title" dir="ltr">{last['dispersion']:.0f}</div></div>
  </div>

  <div style="display:grid;grid-template-columns:1.6fr 1fr;gap:var(--space-8);margin-bottom:var(--space-8)">
    <div>
      <h3>ציון MSS &middot; 250 מפגשים אחרונים</h3>
      {score_chart(history) if history is not None else ''}
      <p class="note" style="font-size:12px;margin-top:var(--space-2)">הקווים מסמנים את גבולות הרג׳ים
        (45 / 70 / 85). הנקודה המסומנת היא הקריאה הנוכחית.</p>
    </div>
    <div>
      <h3>גורמים בולטים היום</h3>
      <div>{bars}</div>
      <p class="note" style="font-size:12px;margin-top:var(--space-2)">שמונת הגורמים הרחוקים ביותר
        מהאמצע, מתוך {len(chosen)} בשימוש היום.</p>
    </div>
  </div>

  {walkforward}

  <h2>אינדיקטורים נוספים</h2>
  <div style="margin-bottom:var(--space-8)">{panels(px, br, days=days)}</div>

  <p style="font-style:italic;max-width:640px;font-size:14px">הציון מנבא את עומק הנפילה, לא את הכיוון.
    תשואת 20 הימים הקדימה מהדלי העליון אינה שלילית באופן עקבי &mdash; קריאה גבוהה טוענת לנשיאת סיכון
    נמוך יותר, לא לקריאת שיא.
    הציון מבדיל בין ימים רק כשהמדד מעל הממוצע הנע 200 שלו: מתחתיו כל הפסים נופלים באותה תדירות,
    והציון אינו מוסיף מידע &mdash; הוא מזהה תיקונים בתוך עלייה, לא שוק דובי.</p>

</main>
</div>
<script>{JS}{REFRESH_JS if live else ''}</script>"""


def band_of(score: float) -> str:
    for band, (lo, hi) in zip(BAND_STATUS, [(0, 45), (45, 70), (70, 85), (85, 101)]):
        if lo <= score < hi:
            return band
    return "85+"


def band_colour(band: str) -> str:
    return {"calm": "var(--good)", "watch": "var(--warn)",
            "elevated": "var(--serious)", "critical": "var(--crit)"}[BAND_STATUS[band]]


def panels(px: pd.DataFrame, br: pd.DataFrame, days: int = 500) -> str:
    """The six charts from the work plan, in its order.

    Every panel follows one rule so the colours mean the same thing six times
    over: the subject of the panel is magenta, anything derived from it - an
    average, a trend - is the blue ramp, and a genuine second measure is amber.
    """
    spx = px["^GSPC"]
    rsp_spy = px["RSP"] / px["SPY"]
    xlp_spx = px["XLP"] / spx
    xly_xlp = px["XLY"] / px["XLP"]
    s5fi = br["s5fi"].reindex(px.index) if not br.empty else pd.Series(dtype=float)
    s5th = br["s5th"].reindex(px.index) if not br.empty else pd.Series(dtype=float)
    gov = debt.load()
    if gov.empty:
        total = public = pd.Series(dtype=float)
    else:
        # Trillions, so the two lines share one axis honestly, and reindexed
        # onto trading days so the x-axis is the same one every other panel has.
        gov = gov.reindex(px.index, method="ffill", limit=10) / 1e12
        total, public = gov["total"], gov["public"]
    # The pace, in percent - the same two readings stress.py scores. Built off
    # `total` after the reindex, so a stale patch of the feed reads flat here
    # rather than as a jump on the day it catches up.
    pace_60 = total.pct_change(60) * 100
    pace_20 = total.pct_change(20) * 100
    # CNN's index beside ours, both on the 0-100 the reader already has. Ours is
    # inverted so high means calm on both lines - printing CNN as published
    # keeps the number on the panel the same one on CNN's own page.
    # score.csv is written before this page is rendered, so the percentile here
    # is today's, not the previous run's.
    fg = fear.load().reindex(px.index)
    try:
        mine = 100 - pd.read_csv(Path(__file__).with_name("score.csv"), index_col=0,
                                 parse_dates=True)["percentile"].reindex(px.index)
    except (OSError, KeyError):
        mine = pd.Series(dtype=float)
    return '<div class="panels">' + "".join([
        panel("S&amp;P 500 והממוצעים שלו",
              "שלושה ממוצעים &mdash; סולם צבע אחד, כי זו סדרה מסודרת.",
              {"SPX": (spx, SUBJECT), "50 ימים": (spx.rolling(50).mean(), RAMP[0]),
               "150 ימים": (spx.rolling(150).mean(), RAMP[1]),
               "200 ימים": (spx.rolling(200).mean(), RAMP[2])}, days=days),
        panel("משקל שווה מול משוקלל לפי שווי שוק",
              "RSP מול SPY. ירידה פירושה שפחות ופחות חברות מובילות את המדד.",
              {"RSP/SPY": (rsp_spy, SUBJECT), "100 ימים": (rsp_spy.rolling(100).mean(), RAMP[2])},
              days=days),
        panel("תנודתיות",
              "נקרא כמשטר, לא כרמה. נמוך &mdash; רגוע, אבל זה לא אותו דבר כמו בטוח.",
              {"VIX": (px["^VIX"], SUBJECT), "20 ימים": (px["^VIX"].rolling(20).mean(), RAMP[2])},
              days=days, refs=[13, 20]),
        panel("רוטציה הגנתית",
              "מוצרי צריכה בסיסיים מול המדד: הכסף זז בשקט הצידה.",
              {"XLP/SPX": (xlp_spx, SUBJECT), "EMA 20 ימים": (xlp_spx.ewm(span=20).mean(), RAMP[2])},
              days=days),
        panel("תיאבון לסיכון",
              "צריכה מרצון מול צריכה הכרחית &mdash; מה אנשים קונים מבחירה ומה מתוך הכרח.",
              {"XLY/XLP": (xly_xlp, SUBJECT), "50 ימים": (xly_xlp.rolling(50).mean(), RAMP[2])},
              days=days),
        panel("רוחב השוק",
              "אחוז מתוך 500 החברות שמעל הממוצע הנע שלהן. מחושב לפי הרכב המדד, לא דרך פרוקסי.",
              {"מעל ממוצע 50 יום": (s5fi, SUBJECT), "מעל ממוצע 200 יום": (s5th, PEER)},
              days=days, refs=[15, 70], unit="%"),
        panel("חוב פדרלי",
              "הסכום שהממשלה חייבת, ומתוכו החלק שמוחזק בידי הציבור. "
              "הרמה רק עולה &mdash; מה שנכנס לציון הוא הקצב שבו היא עולה, לא הגובה עצמו.",
              {"סה&quot;כ חוב": (total, SUBJECT), "מוחזק בידי הציבור": (public, PEER)},
              days=days, unit="T$"),
        panel("קצב גידול החוב",
              "בכמה אחוזים גדל החוב ב-60 וב-20 ימי מסחר. "
              "זו הקריאה שנכנסת לציון &mdash; והיא יכולה לרדת, בניגוד לרמה.",
              {"60 ימים": (pace_60, SUBJECT), "20 ימים": (pace_20, RAMP[2])},
              days=days, refs=[0], unit="%"),
        panel("מדד הפחד והחמדנות של CNN",
              "לתצוגה בלבד &mdash; לא נכנס לציון ולא נבדק. CNN מפרסם שנה אחת אחורה, "
              "והבדיקה דורשת 756 ימים לפני שנת המבחן. הציון שלנו מוצג הפוך, "
              "כדי שגבוה יסמן רגוע בשני הקווים.",
              {"CNN": (fg, SUBJECT), "הציון שלנו, הפוך": (mine, PEER)},
              days=days, refs=[25, 75]),
    ]) + "</div>"


def tile(band: str, days: int, rate: float, lift: float, current: bool,
         ci: float = float("nan"), spells: int = 0) -> str:
    colour = f"var(--{ {'calm': 'good', 'watch': 'warn', 'elevated': 'serious', 'critical': 'crit'}[BAND_STATUS[band]] })"
    now = '<span class="tag" style="color:var(--ink2);font-size:10.5px">today</span>' if current else ""
    band_ci = f'<small> &plusmn;{ci:.1f}</small>' if ci == ci else ""
    runs = f" in {spells:,} spells" if spells else ""
    return f"""<div class="card">
  <div class="lbl"><span class="dot" style="background:{colour}"></span>Score {band} {now}</div>
  <div class="val" style="color:{colour}">{rate:.1f}<small>%</small>{band_ci}</div>
  <div class="sub">{lift:.2f}&times; the base rate &middot; {days:,} days{runs}</div>
</div>"""


def render(res: pd.DataFrame, chosen: list[str], ev: pd.DataFrame, ev_all: pd.DataFrame,
           fwd: pd.DataFrame, stab: pd.DataFrame, oos: pd.Series, years: int,
           missing: list[str], px: pd.DataFrame, br: pd.DataFrame,
           alpha_ctx: dict | None = None, stale_feeds: dict | None = None,
           flag: int = 85) -> str:
    last = res.iloc[-1]
    mss = float(last["MSS"])
    here = band_of(mss)
    colour = band_colour(here)
    base = float(ev.loc["all days", "rate"])

    tiles = "".join(
        tile(b, int(r.days), float(r.rate), float(r.lift), b == here,
             float(getattr(r, "ci_spells", float("nan"))), int(getattr(r, "spells", 0)))
        for b, r in ev.drop(index="all days").iterrows())

    bars = "".join(
        f'<div class="bar"><span>{k}</span><div class="track"><div class="fill" '
        f'style="width:{0 if pd.isna(last[k]) else last[k]:.0f}%;'
        f'background:{"var(--line)" if pd.isna(last[k]) else band_colour(band_of(last[k]))}">'
        f'</div></div><span class="num">{"n/a" if pd.isna(last[k]) else f"{last[k]:.0f}"}</span></div>'
        for k in chosen)

    def band_rows(t: pd.DataFrame) -> str:
        out = ""
        for b, r in t.iterrows():
            mark = ('<span class="dot" style="background:var(--mut)"></span>' if b == "all days"
                    else f'<span class="dot" style="background:{band_colour(b)}"></span>'
                         f"{BAND_MARK[b]} ")
            lift = "" if b == "all days" else f"{r.lift:.2f}&times;"
            out += (f'<tr class="{"now" if b == here else ""}"><td>{mark}{b}</td>'
                    f'<td>{r.days:,.0f}</td><td>{r.rate:.1f}%</td><td>{lift}</td></tr>')
        return out

    fwd_rows = "".join(
        f'<tr class="{"now" if b == here else ""}"><td>'
        f'<span class="dot" style="background:{band_colour(b)}"></span>{BAND_MARK[b]} {b}</td>'
        f"<td>{r.days:,.0f}</td>"
        + "".join(f"<td>{r[f'ret{h}']:+.2f}%</td>" for h in HORIZONS)
        + "".join(f"<td>{r[f'dd{h}']:.2f}%</td>" for h in HORIZONS)
        + "</tr>"
        for b, r in fwd.iterrows())

    stab_rows = "".join(
        f'<tr><td>{"&#9679; " if r.in_latest else ""}{i}</td>'
        f"<td>{r.years_picked} / {years}</td>"
        f'<td>{"in use" if r.in_latest else "&mdash;"}</td></tr>'
        for i, r in stab.iterrows())

    chips = [f'<span class="chip">as of <b>{res.index[-1]:%d %b %Y}</b></span>',
             f'<span class="chip">{len(chosen)} factors, equal weight</span>',
             f'<span class="chip">walk-forward '
             f'<b>{oos.index[0]:%Y}&ndash;{oos.index[-1]:%Y}</b></span>']
    if stale_feeds:
        names = ", ".join(f"{t} to {d:%d %b}" for t, d in stale_feeds.items())
        chips.append('<span class="chip" style="border-color:var(--warn)">'
                     f"&#9888; stale feed <b>{names}</b></span>")

    gap = (f'<div class="note">No print today for <em>{", ".join(missing)}</em>; the score is the '
           f"average of the {len(chosen) - len(missing)} factors that did report.</div>"
           if missing else "")

    alpha = ""
    if alpha_ctx:
        pc = alpha_ctx.get("put_call") or {}
        rows, need = alpha_ctx.get("rows", 0), alpha_ctx.get("need_rows", 300)
        cc = alpha_ctx.get("cross_check")
        cells = ""
        if pc.get("full_chain") is not None:
            cells += ('<div class="card"><div class="lbl">SPY put/call, full chain</div>'
                      f'<div class="val">{pc["full_chain"]}</div>'
                      f'<div class="sub">front expiry {pc["front_expiry"]}</div></div>')
        gate = "ranked with the rest" if alpha_ctx.get("in_score") else "below the gate, left out"
        cells += ('<div class="card"><div class="lbl">History gathered</div>'
                  f'<div class="val">{rows}<small>/ {need}</small></div>'
                  f'<div class="sub">{gate}</div></div>')
        if cc:
            cells += (f'<div class="card"><div class="lbl">{cc["symbol"]} close, two sources</div>'
                      f'<div class="val" style="font-size:22px">{cc["alpha_vantage"]:.2f} / '
                      f'{cc["yfinance"]:.2f}</div>'
                      f'<div class="sub">{"they agree" if cc["agree"] else "THEY DISAGREE"}</div>'
                      "</div>")
        alpha = f"""<h2 id="alpha">Options positioning</h2>
<div class="row">{cells}</div>
<div class="note">Gathered a day at a time by <code>alpha.py</code> &mdash; the endpoint serves one
date per request. It stays out of the score until there is enough history to rank it against.
<em>That gate is the point:</em> a factor earns its way in by being testable, not by sounding
right.</div>"""

    return f"""<title>Market Stress Dashboard</title>
<style>{CSS}</style>
<div class="shell">
<nav class="rail">
  <div class="brand">MSS</div>
  <div class="sec">Market Downturn DSS</div>
  <a class="on" href="#overview">Dashboard</a>
  <a href="#factors">Factors</a>
  <a href="#charts">Charts</a>
  <div class="sec">Evidence</div>
  <a href="#forward">Walk-forward</a>
  <a href="#returns">Forward returns</a>
  <a href="#stability">Factor stability</a>
  <a href="#alpha">Options</a>
</nav>
<div>
<header class="top">
  <h1>Market Stress <span>Dashboard</span></h1>
  <div class="spacer"></div>
  {''.join(chips)}
</header>
<main>

<h2 id="overview">Score, and what followed it</h2>
<div class="card hero-band">
  <div class="hero-wrap">
    {gauge(mss, colour)}
    <div>
      <div class="hero-fig" style="color:{colour}">{mss:.1f}</div>
      <div class="hero-meta" style="margin-top:8px">
        <span class="tag" style="color:{colour}">{BAND_MARK[here]} {last['regime']}</span>
      </div>
    </div>
    <div class="hero-meta" style="margin-left:auto;text-align:right">
      <span>sell flag <b>{'ON' if last['signal'] else 'off'}</b>, fires at {flag}</span>
      <span>5 days <b>{last['MSS_5d']:+.1f}</b></span>
      <span>10 days <b>{last['MSS_10d']:+.1f}</b></span>
      <span>factor spread <b>{last['dispersion']:.0f}</b></span>
    </div>
  </div>
</div>
<div class="row">{tiles}</div>
<div class="note">Each tile is how often a 5% fall arrived within 20 sessions from a day in that
band, measured walk-forward: the factors were re-picked every January using only prior years, so
no day was scored by a selection that had seen it. The base rate across all days is
<em>{base:.1f}%</em>.</div>

<h2 id="factors">Factors today</h2>
<div class="card factors">{bars}</div>
{gap}

<h2 id="charts">The six charts, last two years</h2>
{panels(px, br)}

<h2 id="forward">Walk-forward, {oos.index[0]:%Y}&ndash;{oos.index[-1]:%Y}</h2>
<div class="scroll"><table>
<tr><th>score</th><th>days</th><th>5% fall within 20d</th><th>vs base</th></tr>
{band_rows(ev)}
</table></div>
<div class="note">The table the whole dashboard rests on. Below it, the same bands with the
factors fitted on <em>all</em> history instead &mdash; shown only for the gap, which is what
selection flatters into existence.</div>
<div class="scroll" style="margin-top:10px"><table>
<tr><th>fitted on all history</th><th>days</th><th>5% fall within 20d</th><th>vs base</th></tr>
{band_rows(ev_all)}
</table></div>

<h2 id="returns">Forward return and drawdown</h2>
<div class="scroll"><table>
<tr><th>score</th><th>days</th>{''.join(f'<th>ret +{h}d</th>' for h in HORIZONS)}
{''.join(f'<th>dd +{h}d</th>' for h in HORIZONS)}</tr>
{fwd_rows}
</table></div>
<div class="note">Return and drawdown disagree, and that disagreement is the finding: a high score
precedes a rougher ride, not a lower price. It argues for carrying less risk. It never argues for
calling a top.</div>

<h2 id="stability">Which candidates survived re-selection</h2>
<div class="scroll"><table>
<tr><th>candidate</th><th>years chosen</th><th>today</th></tr>
{stab_rows}
</table></div>
<div class="note">A candidate chosen every year is describing the market. One chosen in a handful
was describing a stretch of it, and got dropped again when that stretch ended.</div>

{alpha}
</main>
</div>
</div>
<script>{JS}</script>"""
