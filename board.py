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

import pandas as pd

# The horizons the forward table is actually built with. Imported rather than
# retyped: the column headers here and the columns forward() produces have to be
# the same list, and two hardcoded copies drift silently.
from cvs import HORIZONS

SURFACE = "#232640"
SUBJECT = "#ec4899"
RAMP = ["#93c5fd", "#60a5fa", "#3b82f6"]
PEER = "#d97706"
# good -> critical. Reserved: never reused as a series colour.
STATUS = {"calm": "#0ca30c", "watch": "#fab219", "elevated": "#ec835a", "critical": "#d03b3b"}
BAND_STATUS = {"0-44": "calm", "45-69": "watch", "70-84": "elevated", "85+": "critical"}
# The page is Russian, and %b prints English month names whatever the locale of
# the machine that happens to build the file. Formatting them here keeps the
# output identical on any box.
RU_MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек"]


def ru_date(ts, year: bool = True) -> str:
    out = f"{ts.day} {RU_MONTHS[ts.month - 1]}"
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
            f'role="img" aria-label="оценка риска {value:.0f} из 100">'
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
    btn.textContent = 'Ошибка';
    say.textContent = String(err && err.message || err);
    setTimeout(function(){
      btn.classList.remove('failed');
      btn.textContent = label;
      say.textContent = '';
      lock(false);
    }, 8000);
  }

  quick.addEventListener('click', async function(){
    lock(true); quick.classList.add('busy'); quick.textContent = 'Загрузка\\u2026';
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
    lock(true); full.classList.add('busy'); full.textContent = 'Пересчёт\\u2026';
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
          else { say.textContent = 'Готово'; location.reload(); }
        }
      } catch (err) { clearInterval(poll); fail(full, err, labels.analyze); }
    }, 1500);
  });
})();
"""


def simple(score: float, chance_now: float, base: float, ceiling: float, floor: float,
           asof, px: pd.DataFrame, br: pd.DataFrame, days: int = 63,
           live: bool = False, held_back: str | None = None,
           history: pd.Series | None = None, month: int = 22,
           far: dict | None = None) -> str:
    """Three numbers and six pictures. Nothing else.

    The dial runs 0 to 100 against the model's own observed range, so it is
    worth watching day to day. On its own it would still mislead: 0 reads as
    "no risk" when it means "the calmest this has ever been", which is a 5%
    chance, not none. So the chance sits beside it at the same size, and the
    ordinary day sits beside that, because a probability without something to
    compare it against is a number nobody can act on.
    """
    frac = max(0.0, min(1.0, score / 100))
    colour = ("var(--good)" if frac < 0.34 else
              "var(--warn)" if frac < 0.67 else "var(--crit)")
    versus = ("ниже" if chance_now < base * 0.9 else
              "выше" if chance_now > base * 1.1 else "около")
    times = chance_now / base if base else 1.0
    return f"""<title>Риск падения рынка</title>
<style>{CSS}
.only{{max-width:1060px;margin:0 auto;padding:26px 22px 44px}}
.head{{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(232px,1fr));
  margin-bottom:16px}}
.big-wrap{{display:flex;gap:20px;align-items:center;
  background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 26px}}
.big-num{{font-size:74px;font-weight:600;line-height:1}}
.num2{{font-size:46px;font-weight:600;line-height:1;margin:8px 0 4px}}
.num2 sup{{font-size:20px;font-weight:500;vertical-align:super;margin-left:1px}}
.cell{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px 24px;
  display:flex;flex-direction:column;justify-content:center}}
.cell .k{{font-size:12.5px;color:var(--ink2)}}
.cell .w{{font-size:11.5px;color:var(--mut);line-height:1.5}}
.scale{{font-size:11.5px;color:var(--mut);margin-top:8px}}
.waiting{{font-size:11.5px;color:var(--warn);margin-top:8px;max-width:26ch;line-height:1.45}}
.wide{{grid-template-columns:1fr;margin-bottom:14px}}
.bar-top{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:14px}}
.bar-top .stamp{{font-size:12px;color:var(--mut);margin-left:auto;text-align:right;
  max-width:44ch;line-height:1.45}}
#jobstep{{font-size:12.5px;color:var(--ink2);font-variant-numeric:tabular-nums}}
.bar-top button{{font:inherit;font-size:12.5px;font-weight:600;border:0;border-radius:7px;
  padding:8px 16px;cursor:pointer}}
#refresh{{color:var(--ink);background:var(--subject)}}
#analyze{{color:var(--ink2);background:transparent;box-shadow:inset 0 0 0 1px var(--base)}}
.bar-top button:hover{{filter:brightness(1.15)}}
.bar-top button:focus-visible{{outline:2px solid var(--ink);outline-offset:2px}}
.bar-top button[disabled]{{cursor:progress;opacity:.7}}
.bar-top button.failed{{background:var(--crit);color:var(--ink);box-shadow:none}}
.bar-top button.busy{{background:var(--base);color:var(--ink2);box-shadow:none}}
@media (prefers-reduced-motion:no-preference){{
  .bar-top button.busy{{animation:pulse 1.1s ease-in-out infinite}}
  @keyframes pulse{{50%{{opacity:.55}}}}
}}
</style>
<div class="only">
  {'''<div class="bar-top">
    <button id="refresh" type="button">Обновить</button>
    <button id="analyze" type="button">Пересчитать</button>
    <span id="jobstep"></span>
    <span class="stamp">Обновить &mdash; заново скачивает цены и пересчитывает оценку,
      несколько секунд. Пересчитать &mdash; также заново считает широту рынка по всем
      500 компаниям и загружает историю опционов в пределах дневного лимита,
      несколько минут.</span>
  </div>''' if live else ''}
  <div class="head">
    <div class="big-wrap">
      {gauge(score, colour)}
      <div>
        <div class="big-num" style="color:{colour}">{score:.0f}</div>
        <div class="scale">оценка, 0&ndash;100<br>на {ru_date(asof)}</div>
        {f'<div class="waiting">&#9432; {held_back}</div>' if held_back else ''}
      </div>
    </div>
    <div class="cell">
      <div class="k">Вероятность падения на 5% в течение месяца</div>
      <div class="num2" style="color:{colour}">{chance_now:.0f}<sup>%</sup></div>
      <div class="w">Что оценка означает на деле: из ста дней, похожих на сегодняшний,
        столько упало.</div>
    </div>
    {far_cell(far)}
    <div class="cell">
      <div class="k">В обычный день</div>
      <div class="num2" style="color:var(--ink2)">{base:.0f}<sup>%</sup></div>
      <div class="w">Сегодня <b style="color:var(--ink)">{versus}</b> нормы
        &mdash; {times:.1f}&times; от обычной вероятности. Оценка равна 0 при значении
        {floor:.0f}% и 100 при {ceiling:.0f}% &mdash; самый спокойный и самый тяжёлый
        день за пятнадцать лет.</div>
    </div>
  </div>
  {track(history, month) if history is not None else ''}
  {panels(px, br, days=days)}
</div>
<script>{JS}{REFRESH_JS if live else ''}</script>"""


def track(history: pd.Series, month: int = 22) -> str:
    """The score itself over the last month, against the bands it moves between.

    The three hairlines are the band edges, so the line is read as a position
    rather than a number: crossing 45 is the whole event, and a move from 8 to
    26 that never leaves the calm band is not.
    """
    recent = history.dropna().tail(month)
    if len(recent) < 2:
        return ""
    # The range, not the net move: this month opened at 28 and closed at 28
    # having been to 46 and to 0 in between, and "unchanged" would be a true
    # sentence that describes none of it.
    return ('<div class="panels wide">' + panel(
        "Оценка за последний месяц",
        f"{len(recent)} сессий, {ru_date(recent.index[0], year=False)} &mdash; "
        f"{ru_date(recent.index[-1], year=False)}. "
        f"Минимум {recent.min():.0f}, максимум {recent.max():.0f}, "
        f"сейчас {recent.iloc[-1]:.0f}. Линии &mdash; границы зон.",
        {"Оценка": (recent, SUBJECT)}, days=month, refs=[45, 70, 85]) + "</div>")


def far_cell(far: dict | None) -> str:
    """Today against 26 years, in one cell. Absent silently if the run failed.

    A different ruler than the headline chance on purpose: that one is the
    walk-forward model on 2012-2026, this one is eleven long-lived factors
    against everything back to the dot-com top. Two eras, two base rates -
    which is why this prints its own base beside the analog rate instead of
    borrowing the headline's.
    """
    if not far:
        return ""
    tone = ("var(--good)" if far["lift"] < 0.9 else
            "var(--warn)" if far["lift"] <= 1.5 else "var(--crit)")
    word = ("спокойнее" if far["lift"] < 0.9 else
            "на уровне" if far["lift"] <= 1.1 else "хуже")
    return f"""<div class="cell">
      <div class="k">Против 26 лет истории</div>
      <div class="num2" style="color:{tone}">{far["lift"]:.2f}&times;</div>
      <div class="w">Из {far["days"]:,} дней с 2000 года, похожих на сегодняшний,
        {far["near_rate"]:.0%} упали на 5%+ в течение месяца, против
        {far["base"]:.0%} в произвольный день &mdash;
        <b style="color:var(--ink)">{word}</b> обычной долгосрочной вероятности.
        Одиннадцать факторов, включая крах доткомов и 2008 год.</div>
    </div>"""


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
    return '<div class="panels">' + "".join([
        panel("S&amp;P 500 и его средние",
              "Три средних &mdash; одна цветовая шкала, потому что это упорядоченный набор.",
              {"SPX": (spx, SUBJECT), "50 дней": (spx.rolling(50).mean(), RAMP[0]),
               "150 дней": (spx.rolling(150).mean(), RAMP[1]),
               "200 дней": (spx.rolling(200).mean(), RAMP[2])}, days=days),
        panel("Равный вес против взвешенного по капитализации",
              "RSP к SPY. Падение означает, что индекс тянут всё меньше компаний.",
              {"RSP/SPY": (rsp_spy, SUBJECT), "100 дней": (rsp_spy.rolling(100).mean(), RAMP[2])},
              days=days),
        panel("Волатильность",
              "Читается как режим, а не как уровень. Низкая &mdash; спокойно, но это не то же самое, что безопасно.",
              {"VIX": (px["^VIX"], SUBJECT), "20 дней": (px["^VIX"].rolling(20).mean(), RAMP[2])},
              days=days, refs=[13, 20]),
        panel("Защитная ротация",
              "Товары первой необходимости против индекса: деньги тихо отходят в сторону.",
              {"XLP/SPX": (xlp_spx, SUBJECT), "EMA 20 дней": (xlp_spx.ewm(span=20).mean(), RAMP[2])},
              days=days),
        panel("Аппетит к риску",
              "Дискреционное против необходимого &mdash; что люди покупают по выбору, а что вынужденно.",
              {"XLY/XLP": (xly_xlp, SUBJECT), "50 дней": (xly_xlp.rolling(50).mean(), RAMP[2])},
              days=days),
        panel("Широта рынка",
              "Доля из 500 компаний выше собственной средней. Посчитано по составу индекса, а не через прокси.",
              {"выше 50-дневной": (s5fi, SUBJECT), "выше 200-дневной": (s5th, PEER)},
              days=days, refs=[15, 70], unit="%"),
    ]) + "</div>"


def tile(band: str, days: int, rate: float, lift: float, current: bool) -> str:
    colour = f"var(--{ {'calm': 'good', 'watch': 'warn', 'elevated': 'serious', 'critical': 'crit'}[BAND_STATUS[band]] })"
    now = '<span class="tag" style="color:var(--ink2);font-size:10.5px">today</span>' if current else ""
    return f"""<div class="card">
  <div class="lbl"><span class="dot" style="background:{colour}"></span>Score {band} {now}</div>
  <div class="val" style="color:{colour}">{rate:.1f}<small>%</small></div>
  <div class="sub">{lift:.2f}&times; the base rate &middot; {days:,} days</div>
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
        tile(b, int(r.days), float(r.rate), float(r.lift), b == here)
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
