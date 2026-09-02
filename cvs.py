"""Composite Vulnerability Score, and the evidence for whether it is worth anything.

The score itself is the easy part: five factors, each ranked against its own
past year, weighted into 0-100. The hard part - the part that decides whether
this file deserves to exist - is what the same history says happened *next*.
So the dashboard prints the forward table beside the gauge. If the >85 bucket
does not lead to worse forward drawdowns than the <45 bucket, the number on
the gauge is decoration and should be read as decoration.

THE TEST WAS RUN AND THE SCORE FAILED IT. The >85 bucket did not separate
from the <45 bucket by enough to trade on, and `stress.py` replaced this
score with the Market Stress Score, which holds 1.9x the base rate above 85
walk-forward and reads drawdown risk rather than direction. The gauge here is
decoration; that is now measured, not hypothetical.

This module is NOT dead, and it is not kept for the score. Six files import
its data layer - `closes`, `pct_rank`, `forward`, `patch`, `regimes`, `stale`
and `HORIZONS` - and those are sound and well tested. Import from here freely.
Build nothing new on the score itself.

Deliberately not here yet: a data-quality layer, a second price source, a
config file, a regime state machine, real breadth. Those are worth building
for a signal that works, and worth nothing for one that does not. Run
--validate first.

    python cvs.py              # dashboard.html + today's reading
    python cvs.py --validate   # forward-return table only
    python cvs.py --lookback 126
    python cvs.py --selftest
"""
from __future__ import annotations

import argparse
import io
import sys
import webbrowser
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

TICKERS = ["^GSPC", "^VIX", "RSP", "SPY", "XLP", "XLU", "HYG", "LQD"]
START = "2006-01-01"  # HYG lists mid-2007; earlier rows carry NaN and drop out.

WEIGHTS = {
    "stretch": 0.20,
    "breadth": 0.25,
    "volatility": 0.25,
    "defensive": 0.15,
    "risk_appetite": 0.15,
}

# Hysteresis: enter high, leave low, so 69.8/70.2/69.7 is one regime and not four.
BANDS = [("CRITICAL", 85, 80), ("ELEVATED", 70, 65), ("WATCH", 45, 40)]
HORIZONS = [5, 10, 20, 40]
# CBOE publishes its own indices as a plain CSV, no key and no account. Only
# ^VIX3M is listed: its closes match yfinance to a millionth over the 283 days
# the two overlap, so splicing them is joining one series, not two. ^VIX is not
# here on purpose - the same comparison puts it 2.61 apart at worst, so whatever
# CBOE's VIX file holds, it is not the series yfinance serves. VVIX has no CLOSE
# column at all. Verify before adding one.
# The exchange that computes these indices publishes them itself, daily, with
# no key and no cap - and unlike yfinance it does not stop for a month. Every
# VIX-family ticker is listed, not only the one that has broken so far: the
# whole point is that the next outage should heal itself without a patch row.
_CBOE_INDEX = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv"
CBOE = {t: _CBOE_INDEX.format(name) for t, name in
        [("^VIX", "VIX"), ("^VIX3M", "VIX3M"), ("^VVIX", "VVIX")]}
BUCKETS = [(0, 45), (45, 70), (70, 85), (85, 101)]


def closes(tickers: list[str], start: str) -> tuple[pd.DataFrame, dict[str, int]]:
    """Adjusted daily closes, one column per ticker.

    Rows survive if *any* ticker printed, not if all did. One feed running a
    month behind the rest - yfinance does this to ^VIX3M - would otherwise cut
    a month off the end of a dashboard whose whole job is to be current. The
    gaps are left as NaN for the caller to notice rather than filled in.
    """
    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False)
    frame = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    frame = frame.dropna(how="all")

    # Patches go in *before* the hole filter, and the order is not cosmetic.
    # ^VIX3M stopped publishing on 17 July and resumed on 17 August. The moment
    # it resumed, its last_valid_index jumped to today and the month in between
    # became a gap inside its own span - so the filter below deleted a month of
    # every other ticker's prices along with it. Patching first fills the gap,
    # and the rows survive.
    frame, applied = cboe(frame)
    frame, from_file = patch(frame)
    applied |= from_file

    # A gap *inside* a column's own span is a hole in the feed, and a rolling
    # window that swallows one returns nothing for the next sixty rows - which
    # is how one missing print silently blanks half a dashboard. A column that
    # has simply stopped is stale, not holed: the row stands and the NaN is
    # left where `stale` can report it.
    ok = pd.DataFrame(
        {t: frame[t].notna()
            | (frame.index < frame[t].first_valid_index())
            | (frame.index > frame[t].last_valid_index())
         for t in frame.columns if frame[t].first_valid_index() is not None}
    )
    # Measured 20 Aug 2026: relaxing this to tolerate one holed column, so that
    # ^VIX3M's intermittent prints stop deleting sessions, admits enough NaN
    # into the rolling windows to move the factor selection and shorten the
    # walk-forward by 974 days, with the top band inverting to 0.33x. The row
    # is the cheaper thing to lose. Fix a flaky feed in `patches.csv` instead.
    return frame[ok.all(axis=1)], applied


def cboe(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fill VIX-family holes from the exchange that computes them.

    yfinance drops ^VIX3M for weeks at a time and then prints a day in the
    middle of the outage, which is worse than a clean stop: the resumed print
    turns the whole gap into a hole inside the column's own span and the filter
    in `closes` deletes those sessions from every other ticker too. Reading
    CBOE's own daily file removes the outage instead of working around it, and
    it is the primary source rather than a screenshot of one.

    Like `patch`, this only ever fills a NaN, so a recovered feed silently wins
    and there is nothing to remember to switch off. A download that fails is
    not an error - the frame comes back as it went in and `patches.csv` still
    gets its turn.
    """
    applied: dict[str, int] = {}
    for ticker, url in CBOE.items():
        if ticker not in frame.columns or frame[ticker].notna().all():
            continue
        try:
            reply = requests.get(url, timeout=20, headers={"User-Agent": "market-stress"})
            reply.raise_for_status()
            hist = pd.read_csv(io.StringIO(reply.text), parse_dates=["DATE"])
            # Two layouts on the same host: the VIX files carry OHLC, the VVIX
            # file is DATE,VVIX. The close is the last column either way.
            close = "CLOSE" if "CLOSE" in hist.columns else hist.columns[-1]
            values = hist.set_index("DATE")[close].reindex(frame.index)
        except Exception as exc:  # network, layout change, anything
            print(f"cboe {ticker} unavailable, falling back to patches.csv: "
                  f"{type(exc).__name__}", file=sys.stderr)
            continue
        holes = frame[ticker].isna() & values.notna()
        if holes.any():
            frame.loc[holes, ticker] = values[holes]
            applied[ticker] = int(holes.sum())
    return frame, applied


def patch(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fill holes a feed left behind, from values collected somewhere else.

    yfinance stopped publishing ^VIX3M, ^VIX9D and ^VIX6M in July 2026 while
    ^VIX kept printing, which knocked out a factor chosen in all fifteen
    selections. `patches.csv` carries the missing closes and where they came
    from, one row each, and this splices them in.

    Two rules make that safe rather than convenient. A patch only ever fills a
    NaN - a real print always wins, so the file becomes inert by itself the day
    the feed recovers, with nothing to remember to undo. And a patch is only
    legitimate when it is the *same series*: these values were checked against
    the 25 days where yfinance and TradingView overlap and agreed to seven
    decimal places. Splicing two series that merely look alike would put a step
    in the history exactly where the model is being asked to read a change.
    """
    path = Path(__file__).with_name("patches.csv")
    if not path.exists():
        return frame, {}
    rows = pd.read_csv(path, parse_dates=["date"])
    applied: dict[str, int] = {}
    for ticker, group in rows.groupby("ticker"):
        if ticker not in frame.columns:
            continue
        values = group.set_index("date")["close"].reindex(frame.index)
        holes = frame[ticker].isna() & values.notna()
        if holes.any():
            frame.loc[holes, ticker] = values[holes]
            applied[ticker] = int(holes.sum())
    return frame, applied


def stale(px: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Tickers whose last print is behind the frame's, and how far behind."""
    last = px.apply(lambda c: c.last_valid_index())
    return {t: d for t, d in last.items() if d is not None and d < px.index[-1]}


def pct_rank(series: pd.Series, lookback: int) -> pd.Series:
    """Where today sits inside its own trailing window, 0-100.

    Trailing only - the window ends today - so nothing here can see forward.
    """
    return series.rolling(lookback, min_periods=lookback).rank(pct=True) * 100


def factors(px: pd.DataFrame) -> pd.DataFrame:
    """The five raw readings, before any ranking. Higher = more vulnerable."""
    spx, vix = px["^GSPC"], px["^VIX"]
    f = pd.DataFrame(index=px.index)
    # Stretch: how far above its own 200-day mean the index has run.
    f["stretch"] = spx / spx.rolling(200).mean() - 1
    # Breadth divergence: cap-weight outrunning equal-weight means fewer names carrying it.
    f["breadth"] = spx.pct_change(20) - px["RSP"].pct_change(20)
    # Volatility: LOW VIX is the vulnerability here - complacency, not fear.
    f["volatility"] = -vix
    # Defensive rotation: staples and utilities bid relative to the index.
    f["defensive"] = ((px["XLP"] + px["XLU"]) / px["SPY"]).pct_change(20)
    # Risk appetite: junk credit losing to investment grade, inverted.
    f["risk_appetite"] = -(px["HYG"] / px["LQD"]).pct_change(20)
    return f


def score(px: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Ranked factors, the weighted CVS, its momentum, and factor agreement."""
    ranked = factors(px).apply(pct_rank, lookback=lookback).dropna()
    out = ranked.copy()
    out["CVS"] = sum(ranked[k] * w for k, w in WEIGHTS.items())
    out["CVS_5d"] = out["CVS"].diff(5)
    out["CVS_10d"] = out["CVS"].diff(10)
    # Agreement: five factors pointing the same way is a different message than
    # one factor dragging the average. Low dispersion = high confidence.
    out["dispersion"] = ranked.std(axis=1)
    out["regime"] = regimes(out["CVS"])
    return out


def regimes(cvs: pd.Series) -> pd.Series:
    """Band per day, with hysteresis: a band is left only below its exit level."""
    state = "NORMAL"
    entry = {name: (hi, lo) for name, hi, lo in BANDS}
    order = [name for name, _, _ in BANDS] + ["NORMAL"]
    out = []
    for v in cvs:
        if state != "NORMAL" and v < entry[state][1]:
            state = "NORMAL"
        for name, hi, _ in BANDS:  # highest band first
            if v >= hi and order.index(name) <= order.index(state):
                state = name
                break
        out.append(state)
    return pd.Series(out, index=cvs.index)


def forward(px: pd.DataFrame, cvs: pd.Series) -> pd.DataFrame:
    """What actually happened next, bucketed by the score on the day.

    The only table that decides whether the gauge means anything.
    """
    spx = px["^GSPC"].reindex(cvs.index)
    rows = []
    for lo, hi in BUCKETS:
        mask = (cvs >= lo) & (cvs < hi)
        row = {"bucket": f"{lo}-{hi - 1}" if hi < 101 else "85+", "days": int(mask.sum())}
        for h in HORIZONS:
            ret = spx.shift(-h) / spx - 1
            # min of close[t+1 .. t+h], reversed so the window still ends at t.
            fwd_min = spx.iloc[::-1].rolling(h, min_periods=1).min().iloc[::-1].shift(-1)
            dd = fwd_min / spx - 1
            row[f"ret{h}"] = ret[mask].mean() * 100
            row[f"dd{h}"] = dd[mask].mean() * 100
        # A 5% drawdown inside 20 sessions is the event a sell signal is for.
        fwd_min20 = spx.iloc[::-1].rolling(20, min_periods=1).min().iloc[::-1].shift(-1)
        row["p_dd5"] = ((fwd_min20 / spx - 1) <= -0.05)[mask].mean() * 100
        rows.append(row)
    return pd.DataFrame(rows).set_index("bucket")


def lead_lag(px: pd.DataFrame, ranked: pd.DataFrame) -> pd.DataFrame:
    """Each factor against forward SPX return - which of the five carry information."""
    spx = px["^GSPC"].reindex(ranked.index)
    cols = list(WEIGHTS) + ["CVS"]
    return pd.DataFrame(
        {f"+{h}d": {c: ranked[c].corr(spx.shift(-h) / spx - 1) for c in cols} for h in HORIZONS}
    )


# ---------- rendering ----------

CSS = """
:root{--bg:#fff;--fg:#14171a;--mut:#6b7480;--line:#e3e6ea;--ok:#1a7f4b;--warn:#b5820a;--bad:#b3261e;--card:#fafbfc}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0e1116;--fg:#e6e9ee;--mut:#8b95a3;--line:#252b33;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--card:#151a21}}
:root[data-theme=dark]{--bg:#0e1116;--fg:#e6e9ee;--mut:#8b95a3;--line:#252b33;--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;--card:#151a21}
body{background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,Segoe UI,sans-serif;margin:0;padding:24px}
.wrap{max-width:1000px;margin:0 auto}
h1{font-size:19px;margin:0 0 2px}.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.hero{display:flex;gap:24px;align-items:baseline;border:1px solid var(--line);background:var(--card);border-radius:10px;padding:18px 20px;margin-bottom:18px;flex-wrap:wrap}
.big{font-size:46px;font-weight:600;line-height:1}
.tag{font-size:13px;font-weight:600;padding:3px 10px;border-radius:20px;border:1px solid currentColor}
.kv{color:var(--mut);font-size:13px}.kv b{color:var(--fg);font-weight:600}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);margin:24px 0 8px}
.bar{display:grid;grid-template-columns:150px 1fr 52px;gap:10px;align-items:center;margin:6px 0;font-size:13px}
.track{height:9px;background:var(--line);border-radius:5px;overflow:hidden}
.fill{height:100%;border-radius:5px}
table{border-collapse:collapse;width:100%;font-size:13px}
.scroll{overflow-x:auto}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{color:var(--mut);font-weight:500}
tr.hit td{font-weight:600}
.note{color:var(--mut);font-size:12px;margin-top:8px}
svg{width:100%;height:110px;display:block}
"""

def spark(cvs: pd.Series, days: int = 250) -> str:
    """The score's own recent line, with the band edges drawn behind it."""
    s = cvs.tail(days)
    n = len(s)
    pts = " ".join(f"{i / (n - 1) * 1000:.1f},{100 - v:.1f}" for i, v in enumerate(s))
    guides = "".join(
        f'<line x1="0" y1="{100 - y}" x2="1000" y2="{100 - y}" stroke="var(--line)"/>'
        f'<text x="4" y="{104 - y}" font-size="9" fill="var(--mut)">{y}</text>'
        for y in (45, 70, 85)
    )
    return (
        f'<svg viewBox="0 0 1000 110" preserveAspectRatio="none" role="img" '
        f'aria-label="CVS last {n} sessions">{guides}'
        f'<polyline points="{pts}" fill="none" stroke="var(--fg)" stroke-width="1.6"/></svg>'
    )


def color(v: float) -> str:
    """A score's band colour on this page. The live dashboard's palette is in
    board.py; this one keeps the plain look the null result was written up in."""
    if v >= 85:
        return "var(--bad)"
    if v >= 70:
        return "var(--warn)"
    return "var(--ok)" if v < 45 else "var(--fg)"


def render(res: pd.DataFrame, fwd: pd.DataFrame, ll: pd.DataFrame, lookback: int) -> str:
    last = res.iloc[-1]
    cvs = last["CVS"]
    bars = "".join(
        f'<div class="bar"><span>{k}</span><div class="track">'
        f'<div class="fill" style="width:{last[k]:.0f}%;background:{color(last[k])}"></div></div>'
        f'<span>{last[k]:.0f}</span></div>'
        for k in WEIGHTS
    )
    hit = fwd.index[-1]
    cur_bucket = next(b for (lo, hi), b in zip(BUCKETS, fwd.index) if lo <= cvs < hi)
    fwd_rows = "".join(
        f'<tr class="{"hit" if b == cur_bucket else ""}"><td>{b}</td><td>{r.days}</td>'
        + "".join(f"<td>{r[f'ret{h}']:+.2f}%</td>" for h in HORIZONS)
        + "".join(f"<td>{r[f'dd{h}']:.2f}%</td>" for h in HORIZONS)
        + f"<td>{r.p_dd5:.0f}%</td></tr>"
        for b, r in fwd.iterrows()
    )
    ll_rows = "".join(
        f"<tr><td>{i}</td>" + "".join(f"<td>{v:+.3f}</td>" for v in row) + "</tr>"
        for i, row in ll.iterrows()
    )
    return f"""<title>CVS Sell Signal</title><style>{CSS}</style>
<div class="wrap">
<h1>Composite Vulnerability Score</h1>
<div class="sub">{res.index[-1]:%d %b %Y} &middot; lookback {lookback} sessions &middot; SPX, VIX, RSP, XLP/XLU, HYG/LQD</div>

<div class="hero">
  <div class="big" style="color:{color(cvs)}">{cvs:.1f}</div>
  <span class="tag" style="color:{color(cvs)}">{last['regime']}</span>
  <span class="kv">5d <b>{last['CVS_5d']:+.1f}</b></span>
  <span class="kv">10d <b>{last['CVS_10d']:+.1f}</b></span>
  <span class="kv">factor spread <b>{last['dispersion']:.0f}</b></span>
</div>

<h2>CVS, last {min(250, len(res))} sessions</h2>
{spark(res['CVS'])}

<h2>Factors today</h2>
{bars}

<h2>What happened next, {fwd['days'].sum():,} sessions since {res.index[0]:%Y}</h2>
<div class="scroll"><table>
<tr><th>CVS</th><th>days</th>{''.join(f'<th>ret +{h}d</th>' for h in HORIZONS)}
{''.join(f'<th>dd +{h}d</th>' for h in HORIZONS)}<th>P(-5% in 20d)</th></tr>
{fwd_rows}
</table></div>
<div class="note">Averages of forward SPX return and forward maximum drawdown from that day.
Today's bucket is bold. If the bottom row is not worse than the top row, the score above is decoration.</div>

<h2>Correlation of each factor with forward return</h2>
<div class="scroll"><table>
<tr><th>factor</th>{''.join(f'<th>{c}</th>' for c in ll.columns)}</tr>
{ll_rows}
</table></div>
<div class="note">Negative is the useful direction: a high reading followed by a weak market.
A factor near zero everywhere is carrying no information and its weight is being wasted.</div>
</div>"""


# ---------- entry ----------


def selftest() -> None:
    # Both CBOE layouts must read: OHLC for the VIX files, DATE,VVIX for VVIX.
    for text, want in (("DATE,OPEN,HIGH,LOW,CLOSE\n01/02/2020,1,2,0,1.5\n", 1.5),
                       ("DATE,VVIX\n01/02/2020,88.5\n", 88.5)):
        hist = pd.read_csv(io.StringIO(text), parse_dates=["DATE"])
        close = "CLOSE" if "CLOSE" in hist.columns else hist.columns[-1]
        assert hist.set_index("DATE")[close].iloc[0] == want, text

    idx = pd.bdate_range("2020-01-01", periods=300)
    up = pd.Series(range(300), index=idx, dtype=float)
    r = pct_rank(up, 252)
    assert r.iloc[:251].isna().all(), "warm-up must stay empty"
    assert r.iloc[-1] == 100.0, "a rising series ends at its own top"

    # Forward drawdown: a cliff on the last day must be seen 5 days earlier.
    px = pd.DataFrame({"^GSPC": [100.0] * 10 + [90.0]}, index=pd.bdate_range("2020-01-01", periods=11))
    cvs = pd.Series(90.0, index=px.index)
    f = forward(px, cvs)
    assert round(f.loc["85+", "dd5"], 4) < 0, "the drop ahead must show as a forward drawdown"

    # A patch fills a hole and never overwrites a print, so it goes inert on its
    # own the day the feed recovers.
    idx = pd.bdate_range("2026-07-16", periods=3)
    frame = pd.DataFrame({"^VIX3M": [20.54, float("nan"), float("nan")]}, index=idx)
    rows = pd.DataFrame({"date": idx, "ticker": "^VIX3M", "close": [99.0, 20.40, 19.59]})
    values = rows.set_index("date")["close"].reindex(frame.index)
    holes = frame["^VIX3M"].isna() & values.notna()
    frame.loc[holes, "^VIX3M"] = values[holes]
    assert frame["^VIX3M"].tolist() == [20.54, 20.40, 19.59], frame["^VIX3M"].tolist()

    # The hole filter must run on the patched frame, not the raw one. A feed
    # that stops and later resumes turns the gap between into a hole inside its
    # own span, and an unpatched filter deletes those rows from every ticker.
    idx = pd.bdate_range("2026-07-16", periods=4)
    raw = pd.DataFrame({"^VIX": [1.0, 2.0, 3.0, 4.0],
                        "^VIX3M": [20.5, None, None, 18.9]}, index=idx)
    def survives(f):
        ok = pd.DataFrame({t: f[t].notna()
                              | (f.index < f[t].first_valid_index())
                              | (f.index > f[t].last_valid_index()) for t in f.columns})
        return len(f[ok.all(axis=1)])
    assert survives(raw) == 2, "unpatched, the resumed feed eats the gap"
    filled = raw.copy()
    filled.loc[idx[1:3], "^VIX3M"] = [20.4, 19.6]
    assert survives(filled) == 4, "patched first, every row survives"

    # Hysteresis: 71 enters ELEVATED, 66 does not leave it, 64 drops back to WATCH.
    r = regimes(pd.Series([30, 71, 66, 64], index=pd.bdate_range("2020-01-01", periods=4)))
    assert list(r) == ["NORMAL", "ELEVATED", "ELEVATED", "WATCH"], list(r)
    print("selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookback", type=int, default=252, help="ranking window, sessions")
    ap.add_argument("--validate", action="store_true", help="print the forward table, write nothing")
    ap.add_argument("--start", default=START)
    ap.add_argument("--out", default="dashboard.html")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return 0

    px, _ = closes(TICKERS, a.start)
    if px.empty:
        print("no price data came back", file=sys.stderr)
        return 1
    res = score(px, a.lookback)
    if res.empty:
        print(f"not enough history for a {a.lookback}-session window", file=sys.stderr)
        return 1
    fwd = forward(px, res["CVS"])
    ll = lead_lag(px, res)

    last = res.iloc[-1]
    print(f"{res.index[-1]:%Y-%m-%d}  CVS {last['CVS']:.1f}  {last['regime']}  "
          f"5d {last['CVS_5d']:+.1f}  spread {last['dispersion']:.0f}")
    print(fwd.round(2).to_string())

    if a.validate:
        print()
        print(ll.round(3).to_string())
        return 0

    out = Path(a.out).resolve()
    out.write_text(render(res, fwd, ll, a.lookback), encoding="utf-8")
    print(f"wrote {out}")
    if not a.no_open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
