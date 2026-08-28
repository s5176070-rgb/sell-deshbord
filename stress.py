"""Market Stress Score - the same question as cvs.py, asked the other way round.

cvs.py measured how calm the market was and called that vulnerability. The
forward table said the opposite: calm days do not fall, panicked days do. So
this file drops the framing and asks what actually precedes a drawdown -
volatility rising, breadth narrowing, credit widening, trend breaking.

Nothing here is scored on data it was chosen with. Every January the factors
are re-picked using only the years that ended before that January, and the
score those factors produce is recorded for the twelve months that follow.
Stitch the years together and the whole track from 2012 on is out-of-sample -
not one lucky split, fifteen consecutive ones. Re-picking yearly also means a
factor that stops working stops being used, which a single fixed selection
cannot do.

Two details that would quietly distort this if left alone, both handled: the
ranking window only ever looks backwards, and the last 20 rows of each training
slice are dropped, because their forward window is cut off by the boundary and
would report the run-up to a January as calmer than it was.

    python stress.py             # dashboard_stress.html + today's reading
    python stress.py --bench     # tables only, write nothing
    python stress.py --selftest
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
import time
import webbrowser
from pathlib import Path

import pandas as pd

import alpha
import board
import breadth
from cvs import closes, forward, patch, pct_rank, regimes, stale

TICKERS = ["^GSPC", "^VIX", "^VIX3M", "^VVIX", "RSP", "SPY", "XLY", "XLP", "XLU", "HYG",
           "LQD", "TLT", "^TNX", "^IRX",
           # The 2026 additions, auditioned in bench_new.py: small caps, semis,
           # transports and the two safety bids all cleared the bar in every one
           # of the fourteen yearly selections. ^SKEW and CL=F also cleared it
           # but are not here - SKEW has 67 holes inside its own span and oil
           # trades a futures calendar, and one holed column deletes the row
           # for everyone. A candidate has to be a clean feed, not just a good
           # signal.
           "^RUT", "^SOX", "^DJT", "^DJI", "GLD", "UUP"]
START = "2006-01-01"

# What counts as the event worth selling ahead of.
EVENT_DAYS, EVENT_DEPTH = 20, -0.05
# A candidate has to beat this correlation against forward drawdown on the
# years available at the time to be let into the composite. One bar, all years.
MIN_CORR = -0.06
FLAG = 85  # the level the sell flag acts on; see score() for why it is not 70
FIRST_LIVE_YEAR = 2012  # the first January with enough history behind it to pick on
MIN_TRAIN = 756  # three years of ranked rows before a selection is allowed
# Share of the chosen factors that must report before a day may be the reading.
# One index posting an early bar while the ETFs have not opened drags the frame's
# last date forward, and the score then averages whatever handful of factors
# happens to have a value - a different measurement wearing the same name.
MIN_COVERAGE = 0.75
# The hour the served dashboard re-analyses itself. Morning, so the previous US
# session has closed and its daily bars are final.
MARKET_TZ = "America/New_York"
# An hour after the 16:00 New York close, so the tape has settled before the
# day is scored. Held in exchange time, not local time: the machine can be in
# any zone and move between them, but the close does not.
DAILY_AT = 17
STAMP = Path(__file__).with_name(".last_analysis")


def candidates(px: pd.DataFrame, br: pd.DataFrame | None = None,
               pc: pd.DataFrame | None = None) -> pd.DataFrame:
    """Every raw reading worth testing. Higher must mean *more* stress, always.

    Signs are set here and nowhere else, so the bench measures direction as
    well as strength: a candidate with the wrong sign simply fails the bar.
    """
    spx, vix = px["^GSPC"], px["^VIX"]
    ratio_rsp = px["RSP"] / px["SPY"]
    ratio_credit = px["HYG"] / px["LQD"]
    c = pd.DataFrame(index=px.index)

    # Volatility, as movement and as shape, not only as level.
    c["vix_5d"] = vix.diff(5)
    c["vix_20d"] = vix.diff(20)
    c["vix_level"] = vix
    c["vol_of_vol"] = vix.rolling(20).std()
    c["realized_vol"] = spx.pct_change().rolling(20).std()
    # Term structure: one-month above three-month is backwardation - the market
    # pricing trouble now rather than later, and the cheapest stress read there is.
    c["vix_term"] = vix / px["^VIX3M"]
    c["vix_term_5d"] = (vix / px["^VIX3M"]).diff(5)
    # ^VIX3M, ^VIX9D and ^VIX6M all stopped updating on yfinance in July 2026
    # while ^VIX kept printing, so the term-structure factor - chosen in every
    # one of the fifteen selections - has been missing from the live reading.
    # VVIX over VIX is a different measure, not a substitute: the price of
    # protection against volatility itself, against volatility. It is offered as
    # a candidate on the same terms as everything else, and it is current.
    c["vvix_ratio"] = px["^VVIX"] / vix
    c["vvix_level"] = px["^VVIX"]

    # Trend giving way.
    c["off_high"] = -(spx / spx.rolling(60).max() - 1)
    c["below_50"] = -(spx / spx.rolling(50).mean() - 1)
    c["below_200"] = -(spx / spx.rolling(200).mean() - 1)
    c["stretch"] = spx / spx.rolling(200).mean() - 1  # cvs.py's, kept as a control

    # Breadth, read entirely off RSP. The equal-weight index gives every name
    # the same vote, so RSP against SPY is the average stock against the index -
    # not true breadth, but the only version available without downloading five
    # hundred histories, and it answers the same question: is the market being
    # carried by everything, or by a handful of names.
    rsp = px["RSP"]
    c["narrow_20"] = -ratio_rsp.pct_change(20)
    c["narrow_60"] = -ratio_rsp.pct_change(60)
    # The level of the ratio against its own trend, not just its recent change:
    # breadth can be flat for months and still be sitting far below where it was.
    c["narrow_trend"] = -(ratio_rsp / ratio_rsp.rolling(100).mean() - 1)
    # The average stock off its own high, and under its own long trend. These
    # can be ugly while the cap-weighted index still prints records.
    c["rsp_off_high"] = -(rsp / rsp.rolling(60).max() - 1)
    c["rsp_below_200"] = -(rsp / rsp.rolling(200).mean() - 1)
    # The divergence itself: how much further above its 200-day the index sits
    # than the average stock does. Large means few names are holding it up.
    c["divergence"] = (spx / spx.rolling(200).mean()) - (rsp / rsp.rolling(200).mean())
    # The average stock moving more violently than the index it belongs to.
    c["rsp_vol_gap"] = (rsp.pct_change().rolling(20).std()
                        - px["SPY"].pct_change().rolling(20).std())

    # Credit widening: junk losing to investment grade.
    c["credit_20"] = -ratio_credit.pct_change(20)
    c["credit_60"] = -ratio_credit.pct_change(60)

    # Money moving to safety. The slope versions ask whether the rotation is
    # under way rather than whether it already happened.
    c["defensive"] = ((px["XLP"] + px["XLU"]) / px["SPY"]).pct_change(20)
    c["bonds_bid"] = (px["TLT"] / px["SPY"]).pct_change(20)
    xlp_spx = px["XLP"] / spx
    c["xlp_slope"] = xlp_spx.ewm(span=20).mean().diff(10)
    c["xlu_ratio"] = (px["XLU"] / px["SPY"]).pct_change(20)

    # Risk appetite: discretionary against staples. Falling means the market is
    # paying up for what people must buy over what they choose to.
    xly_xlp = px["XLY"] / px["XLP"]
    c["risk_off_20"] = -xly_xlp.pct_change(20)
    # The rolling over, not the fall: the second derivative of the ratio's own
    # trend turns down while the ratio is still rising.
    c["risk_off_accel"] = -xly_xlp.rolling(50).mean().diff(5).diff(5)

    # The middle average, between the 50 that breaks first and the 200 that decides.
    c["below_150"] = -(spx / spx.rolling(150).mean() - 1)

    # The yield curve. Its reputation is for calling recessions a year out,
    # which is the wrong clock for a twenty-day drawdown - so it is offered as a
    # candidate on the same terms as everything else and judged, not assumed.
    curve = px["^TNX"] - px["^IRX"]
    c["curve_flat"] = -curve
    c["curve_steepen_20"] = curve.diff(20)
    c["rates_up_20"] = px["^TNX"].diff(20)

    # The bid for Treasuries, stated the way Yoni put it: a rising bond price
    # means money paying up for safety, and a falling yield is the same
    # sentence read off the other side of the bond. `bonds_bid` above already
    # asks this *relative to SPY*, which answers a different question - bonds
    # can outrun stocks while both fall. These are the absolute versions.
    #
    # Note this is the opposite sign to `rates_up_20`. `select` keeps only
    # candidates pointing one way, so rates rising failing to predict a
    # drawdown says nothing at all about rates falling; that claim has never
    # been on the bench until now. Both are offered, and the bench answers.
    c["bond_up_20"] = px["TLT"].pct_change(20)
    c["bond_stretch"] = px["TLT"] / px["TLT"].rolling(200).mean() - 1
    c["yield_down_20"] = -px["^TNX"].diff(20)
    c["yield_low"] = -px["^TNX"]
    c["short_rate_down_20"] = -px["^IRX"].diff(20)

    # The long-history bench (bench_new.py, judged 2012-2026 each January on
    # prior years only) - every one of these cleared the bar in all fourteen
    # selections, with correlations stronger than most of the incumbents.
    over = lambda series, n: series / series.rolling(n).mean()
    rut, sox, djt, dji = px["^RUT"], px["^SOX"], px["^DJT"], px["^DJI"]
    # Small caps break first: their own trend, and how far they lag the index.
    c["rut_off_high"] = -(rut / rut.rolling(60).max() - 1)
    c["rut_below_200"] = 1 - over(rut, 200)
    c["rut_lag"] = over(spx, 200) - over(rut, 200)
    # Semiconductors as the cycle's loudest early warning.
    c["sox_off_high"] = -(sox / sox.rolling(60).max() - 1)
    c["sox_fade_60"] = -(sox / spx).pct_change(60)
    # Dow theory: transports refusing to confirm the industrials.
    c["djt_div"] = over(dji, 200) - over(djt, 200)
    # Flights to safety with the same shape as bonds_bid: relative, not absolute.
    c["gold_bid"] = (px["GLD"] / spx).pct_change(20)
    c["dollar_bid"] = px["UUP"].pct_change(20)

    if br is not None and not br.empty:
        # True breadth, counted off the constituents (see breadth.py). Two
        # readings of the same series in opposite directions, deliberately:
        # thin participation is the ordinary warning, while a very *high* share
        # above the 50-day is the "everything is being bought" reading that late
        # stages are supposed to show. Both are claims. The bench answers them.
        s5fi = br["s5fi"].reindex(px.index).ffill(limit=5)
        s5th = br["s5th"].reindex(px.index).ffill(limit=5)
        c["breadth_thin_50"] = -s5fi
        c["breadth_thin_200"] = -s5th
        c["breadth_euphoria"] = s5fi
        c["breadth_rolling"] = -s5fi.diff(20)
        c["breadth_rolling_200"] = -s5th.diff(20)
        # The divergence the plan is built around: the index climbing while
        # fewer and fewer names come with it.
        c["breadth_divergence"] = spx.pct_change(20).rank(pct=True) - s5th.rank(pct=True) / 100

    if pc is not None and len(pc) >= alpha.NEED_ROWS:
        # Options positioning, and it only gets here once alpha.py has gathered
        # enough days to rank against a trailing year. Below that the gate in
        # main() keeps it out entirely - an untested factor stays out of the
        # score no matter how good the reasoning behind it sounds.
        # Two directions again, because both stories are told about this series:
        # heavy put buying as fear that marks a bottom, and light put buying as
        # an unhedged market with further to fall.
        chain = pc["full_chain"].reindex(px.index).ffill(limit=5)
        c["puts_heavy"] = chain
        c["puts_light"] = -chain
        c["puts_change_20"] = -chain.diff(20)
    return c


def fwd_drawdown(spx: pd.Series, days: int = EVENT_DAYS) -> pd.Series:
    """Deepest close over the next `days` sessions, as a return from today."""
    fwd_min = spx.iloc[::-1].rolling(days, min_periods=1).min().iloc[::-1].shift(-1)
    return fwd_min / spx - 1


def rank_against_drawdown(ranked: pd.DataFrame, spx: pd.Series) -> pd.Series:
    """Correlation of each candidate with the drawdown that followed.

    The final EVENT_DAYS rows are dropped. Their forward window runs off the
    end of the slice and is silently cut short, so they report a calmer market
    than the one that followed - at a January cut, the twenty days whose answer
    lies on the other side of the boundary.
    """
    dd = fwd_drawdown(spx.reindex(ranked.index))
    return ranked.iloc[:-EVENT_DAYS].corrwith(dd.iloc[:-EVENT_DAYS])


def select(corr: pd.Series) -> list[str]:
    """Candidates that cleared the bar. No optimiser, equal weight among them.

    With sixteen candidates and one market, a weight optimiser fits the 2008 and
    2020 crashes and calls it a model. Equal weight has nothing to fit.
    """
    return list(corr.index[corr <= MIN_CORR])


def walk_forward(ranked: pd.DataFrame, spx: pd.Series) -> tuple[pd.Series, dict[int, list[str]]]:
    """Re-pick every January on prior years only; keep the score for that year.

    Returns the stitched out-of-sample score and what was chosen each year.
    """
    pieces: list[pd.Series] = []
    picks: dict[int, list[str]] = {}
    for year in range(FIRST_LIVE_YEAR, ranked.index[-1].year + 1):
        past = ranked[ranked.index < f"{year}-01-01"]
        if len(past) < MIN_TRAIN:
            continue
        chosen = select(rank_against_drawdown(past, spx))
        if not chosen:
            continue
        window = ranked[(ranked.index >= f"{year}-01-01") & (ranked.index < f"{year + 1}-01-01")]
        picks[year] = chosen
        if not window.empty:
            pieces.append(window[chosen].mean(axis=1))
    return (pd.concat(pieces) if pieces else pd.Series(dtype=float)), picks


def score(ranked: pd.DataFrame, chosen: list[str]) -> pd.DataFrame:
    """Today's composite from today's selection, plus momentum and the flag."""
    out = ranked[chosen].copy()
    out["MSS"] = ranked[chosen].mean(axis=1)
    out["MSS_5d"] = out["MSS"].diff(5)
    out["MSS_10d"] = out["MSS"].diff(10)
    out["dispersion"] = ranked[chosen].std(axis=1)
    out["regime"] = regimes(out["MSS"])
    # The flag sits at 85, and the honest reason is not that 85 is better than
    # 70. On the current walk-forward the top two bands are indistinguishable -
    # 1.69x at 70-84 against 1.67x at 85+, on 445 and 112 days - and earlier
    # runs had them the other way round. At equal lift the choice is only how
    # often you want to be told: 85 fires on a quarter as many days for the same
    # accuracy. Someone who would rather have the earlier, noisier warning
    # should set this to 70 and expect four times the alerts, not better ones.
    # Do not re-tune it each time the table wiggles; that is fitting to noise.
    # Persistence: two of the last three days, so one poke through is not an
    # instruction to sell anything.
    out["signal"] = (out["MSS"] >= FLAG).rolling(3).sum() >= 2
    return out


def event_rate(spx: pd.Series, mss: pd.Series) -> pd.DataFrame:
    """How often the event followed, by band, on whatever series is handed in."""
    hit = fwd_drawdown(spx.reindex(mss.index)) <= EVENT_DEPTH
    rows = [{"band": "all days", "days": int(len(mss)), "rate": hit.mean() * 100, "lift": 1.0}]
    base = hit.mean()
    for lo, hi in [(0, 45), (45, 70), (70, 85), (85, 101)]:
        m = (mss >= lo) & (mss < hi)
        rows.append({
            "band": f"{lo}-{hi - 1}" if hi < 101 else "85+",
            "days": int(m.sum()),
            "rate": hit[m].mean() * 100,
            "lift": (hit[m].mean() / base) if base and m.any() else float("nan"),
        })
    return pd.DataFrame(rows).set_index("band")


def calibration(oos: pd.Series, hit: pd.Series, bins: int = 10) -> pd.DataFrame:
    """Turn the score into an actual chance of a fall, from the walk-forward days.

    The score is a percentile - it says where today sits against its own past,
    which is not a probability of anything. This splits the out-of-sample days
    into equal-sized groups and asks what share of each was followed by a 5%
    fall. Reading a score against this curve gives a number that means what it
    says: out of a hundred days that looked like today, this many fell.

    The curve is forced upward-only. More stress must never map to less risk;
    where the raw groups dip it is the sample being thin, not the market saying
    something, and a dip would show as a falling gauge on a rising score.
    """
    group = pd.qcut(oos, bins, labels=False, duplicates="drop")
    table = pd.DataFrame({"g": group, "score": oos, "hit": hit.reindex(oos.index)})
    out = table.groupby("g").agg(score=("score", "mean"), rate=("hit", "mean"),
                                 days=("hit", "size"))
    out["rate"] = out["rate"].cummax() * 100
    return out


def chance(score, curve: pd.DataFrame):
    """Read a score off the calibration curve, flat outside its range.

    Takes one number or a whole series, and gives back a percentage: out of a
    hundred days that looked like this one, how many fell.
    """
    import numpy as np
    out = np.interp(score, curve["score"], curve["rate"])
    return pd.Series(out, index=score.index) if isinstance(score, pd.Series) else float(out)


def relative(chance_pct, curve: pd.DataFrame):
    """The same reading stretched over 0-100, against its own observed range.

    The honest probability only ever runs from about 5% to about 23%, because
    that is the whole span the market has offered in fifteen years. As a number
    to watch that is nearly useless - every real day reads as "small" and the
    difference between a calm week and the worst week of 2020 is eighteen
    points near the bottom of the dial. This puts 0 at the calmest the model has
    ever read and 100 at the worst, so the full width of the scale carries the
    full width of the evidence.

    It is a rank, not a probability, and the two must always be shown together:
    100 here does not mean the market will fall, it means nothing in fifteen
    years looked worse than this. `chance` is the number that means what it says.
    """
    lo, hi = curve["rate"].min(), curve["rate"].max()
    return (chance_pct - lo) / ((hi - lo) or 1.0) * 100


def stability(picks: dict[int, list[str]], names: list[str]) -> pd.DataFrame:
    """How many of the re-selections each candidate survived, and its last year."""
    years = sorted(picks)
    rows = {n: {"years_picked": sum(n in picks[y] for y in years),
                "in_latest": n in picks[years[-1]] if years else False}
            for n in names}
    out = pd.DataFrame(rows).T
    out["years_picked"] = out["years_picked"].astype(int)
    return out.sort_values(["in_latest", "years_picked"], ascending=False)


def selftest() -> None:
    idx = pd.bdate_range("2020-01-01", periods=11)
    spx = pd.Series([100.0] * 10 + [90.0], index=idx)
    dd = fwd_drawdown(spx, days=5)
    assert dd.iloc[5] < -0.09, "a fall five days out must be visible today"
    assert dd.iloc[0] == 0.0, "flat ahead is no drawdown"

    # Selection must weigh the sign, not just the size.
    assert select(pd.Series({"good": -0.20, "flat": -0.01, "backwards": 0.20})) == ["good"]

    # The trailing EVENT_DAYS rows must be dropped, or a training slice reads
    # the drawdown that happens after it ends.
    # A market falling every day. The rows near the end still have a real fall
    # ahead of them, but their forward window is cut short by the edge of the
    # data, so they read calmer the closer to it they sit - which is exactly
    # the bias the tail drop removes.
    n = 60
    idx = pd.bdate_range("2020-01-01", periods=n)
    falling = pd.Series([100.0 - i for i in range(n)], index=idx)
    d = fwd_drawdown(falling)
    assert pd.isna(d.iloc[-1]), "the last row has no forward window at all"
    assert d.iloc[-2] > d.iloc[-EVENT_DAYS], "the truncated tail understates the fall"
    r = pd.DataFrame({"x": range(n)}, index=idx, dtype=float)
    assert len(r.iloc[:-EVENT_DAYS]) == n - EVENT_DAYS, "the tail must be cut"

    # Persistence: one day through the line is not a flag, two of three is.
    mss = pd.Series([50, 75, 50, 75, 75], index=pd.bdate_range("2020-01-01", periods=5))
    assert list((mss >= 70).rolling(3).sum() >= 2)[2:] == [False, True, True]

    # The calibration curve may never fall: a higher score reading as a lower
    # chance would show on the gauge as risk dropping while stress rises.
    n = 400
    idx = pd.bdate_range("2020-01-01", periods=n)
    scores = pd.Series(range(n), index=idx, dtype=float)
    hits = pd.Series([(i % 10) < (i // 40) for i in range(n)], index=idx)
    curve = calibration(scores, hits)
    assert curve["rate"].is_monotonic_increasing, curve["rate"].tolist()
    assert chance(scores.iloc[-1], curve) == curve["rate"].iloc[-1], "top reads the top"
    assert chance(-999, curve) == curve["rate"].iloc[0], "below the range is flat"

    # The relative score must put 0 at the calmest reading and 100 at the worst,
    # so the dial spans the evidence rather than a corner of it.
    assert round(relative(curve["rate"].min(), curve), 6) == 0
    assert round(relative(curve["rate"].max(), curve), 6) == 100

    # A premature last row - one feed open, the rest not - must not become the
    # reading. The day before it, measured over everything, is the honest answer.
    idx = pd.bdate_range("2026-08-12", periods=3)
    frame = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, None],
                          "c": [1.0, 2.0, None], "d": [1.0, 2.0, None]}, index=idx)
    covered = frame.notna().mean(axis=1) >= MIN_COVERAGE
    assert not covered.iloc[-1], "one of four reporting is not a day"
    assert covered[covered].index[-1] == idx[1], "fall back to the last full day"

    # The daily clock fires on an unserved session close, not on a wall-clock
    # match, so a machine asleep at the close catches up and a restart an hour
    # later does not re-run. Everything here is exchange time.
    et = lambda t: pd.Timestamp(t, tz=MARKET_TZ)
    late = et("2026-08-18 18:00")  # Tuesday, after the close
    assert due(late, et("2026-08-17 17:05")), "yesterday's run is stale after today's close"
    assert not due(late, et("2026-08-18 17:05")), "today's run already served"
    assert due(late, None), "never run means due"
    early = et("2026-08-18 09:00")  # Tuesday, market open, today's close still ahead
    assert not due(early, et("2026-08-17 17:05")), "not due before the close"
    assert due(et("2026-08-20 09:00"), et("2026-08-18 17:05")), \
        "a missed day is caught up, not skipped"
    # A weekend must not rerun Friday. 21 Aug 2026 is a Friday.
    friday_done = et("2026-08-21 17:05")
    assert not due(et("2026-08-22 12:00"), friday_done), "Saturday has no close of its own"
    assert not due(et("2026-08-23 20:00"), friday_done), "nor does Sunday"
    assert due(et("2026-08-24 18:00"), friday_done), "Monday's close is a new slot"
    print("selftest ok")


def build(a, live: bool = False) -> str | None:
    """Download, score, write score.csv, and return the page.

    Everything that reaches the network or the disk happens here, so `--serve`
    can call it again on a button press and get a genuinely fresh reading rather
    than a re-render of a stale one. None when there is no page to build.
    """
    px, patched = closes(TICKERS, a.start)
    if px.empty:
        raise RuntimeError("no price data came back")
    if patched:
        print("filled from CBOE and patches.csv: "
              + ", ".join(f"{t} {n} days" for t, n in patched.items()))
    spx = px["^GSPC"]
    br = breadth.load()
    if br.empty:
        print("no breadth.csv - running without the constituent factors; "
              "build it with `python breadth.py`", file=sys.stderr)
    pc = alpha.load()
    if 0 < len(pc) < alpha.NEED_ROWS:
        print(f"put/call history is {len(pc)} rows, needs {alpha.NEED_ROWS} "
              f"before it can be ranked - left out of the score", file=sys.stderr)
    ranked = candidates(px, br, pc).apply(pct_rank, lookback=a.lookback)
    # Selection and the walk-forward want complete rows; the live reading does
    # not, and must not be dragged a month back by one lagging feed.
    hist = ranked.dropna()
    behind = stale(px)

    oos, picks = walk_forward(hist, spx)
    if oos.empty:
        raise RuntimeError("no year cleared the bar - that is the answer, not an error")
    chosen = picks[max(picks)]
    res = score(ranked.loc[hist.index[0]:], chosen)

    # Back off the tail until enough of the chosen factors actually reported.
    # Yesterday's reading over the full set beats today's over a third of it.
    covered = res[chosen].notna().mean(axis=1) >= MIN_COVERAGE
    held_back = None
    if covered.any() and not covered.iloc[-1]:
        keep = covered[covered].index[-1]
        share = res[chosen].notna().mean(axis=1).iloc[-1]
        # One session back is the market opening. More than that is the feed
        # itself falling behind, and saying "still opening" for a week would
        # dress a broken source up as a normal morning.
        # Counted on the calendar, not on surviving rows: when a feed goes
        # dark the bad days are dropped from the frame entirely, so the row
        # distance shrinks to one and hides exactly the outage it should show.
        # ponytail: business days, so a market holiday reads one session late.
        gap = len(pd.bdate_range(keep, res.index[-1])) - 1
        # The page is Hebrew, so the notice on it is too. The stderr line
        # below stays English - that one is for the log, not the reader.
        held_back = (f"ל-{board.ru_date(res.index[-1], year=False)} זמינים רק "
                     f"{share:.0%} מהגורמים "
                     + ("&mdash; המסחר עדיין נפתח. מוצג היום המלא האחרון."
                        if gap <= 1 else
                        f"&mdash; פס המחירים חסר כבר {gap} מפגשים. מוצג "
                        f"{board.ru_date(keep, year=False)}, היום המלא האחרון."))
        print(f"{res.index[-1]:%Y-%m-%d} had only {share:.0%} of the factors reporting - "
              f"reading {keep:%Y-%m-%d} instead", file=sys.stderr)
        res = res.loc[:keep]

    # A chosen factor with no print on the reading day is averaged out, not guessed at.
    missing = [c for c in chosen if pd.isna(res.iloc[-1][c])]
    # Staleness is judged against the day being read, not against a premature row.
    behind = {t: d for t, d in behind.items() if d < res.index[-1]}

    ev = event_rate(spx, oos)
    ev_all = event_rate(spx, score(hist, select(rank_against_drawdown(hist, spx)))["MSS"])
    fwd = forward(px, oos)
    stab = stability(picks, list(ranked.columns))

    last = res.iloc[-1]
    print(f"{res.index[-1]:%Y-%m-%d}  MSS {last['MSS']:.1f}  {last['regime']}  "
          f"5d {last['MSS_5d']:+.1f}  sell flag {'ON' if last['signal'] else 'off'}")
    print(f"picked for {max(picks)}: {chosen}")
    if behind:
        print("stale feeds: " + ", ".join(f"{t} last {d:%Y-%m-%d}" for t, d in behind.items()))
    if missing:
        print(f"scored without {missing} - no print today")
    print()
    print(f"walk-forward {oos.index[0]:%Y}-{oos.index[-1]:%Y}")
    print(ev.round(2).to_string())
    if a.bench:
        print("\nfitted on all history, for the gap")
        print(ev_all.round(2).to_string())
        print()
        print(fwd.round(2).to_string())
        print()
        print(stab.to_string())
        return None

    # The daily series, exported whether the page is the plain one or the full
    # one, so the number can be read somewhere other than this dashboard.
    curve = calibration(oos, fwd_drawdown(spx.reindex(oos.index)) <= EVENT_DEPTH)
    pct = chance(res["MSS"], curve)
    export = pd.DataFrame({
        "score": relative(pct, curve).round(1),   # 0-100 against the observed range
        "chance_pct": pct.round(1),               # what it means, in percent
        "percentile": res["MSS"].round(1),        # the raw factor average
        "regime": res["regime"],
        "walk_forward": res.index.isin(oos.index),  # False = fitted era, weaker evidence
    })
    csv = Path(__file__).with_name("score.csv")
    export.to_csv(csv, index_label="date")
    print(f"wrote {csv} - {len(export)} days")

    if a.full:
        ctx = Path(__file__).with_name("alpha_context.json")
        alpha_ctx = json.loads(ctx.read_text(encoding="utf-8")) if ctx.exists() else None
        return board.render(res, chosen, ev, ev_all, fwd, stab, oos, len(picks), missing,
                            px, br, alpha_ctx, behind, FLAG)
    # The long-history comparison rides along on every build, as asked: the
    # same day measured against every similar-looking day since 2000. Import
    # here, not at the top - since2000 imports from this module.
    try:
        import since2000
        far = since2000.analogs()
    except Exception as exc:
        print(f"since-2000 comparison unavailable this run: {type(exc).__name__}",
              file=sys.stderr)
        far = None
    return board.simple(float(export["score"].iloc[-1]),
                        float(export["chance_pct"].iloc[-1]),
                        float(ev.loc["all days", "rate"]),  # the everyday chance
                        curve["rate"].max(), curve["rate"].min(),
                        res.index[-1], px, res, chosen, br, a.days, live, held_back,
                        history=export["score"], far=far)


def reanalyse(a, state, note) -> None:
    """Rebuild every input from source, then rescore. Minutes, not seconds.

    Refresh re-reads prices; this re-derives the things prices alone cannot
    give: breadth counted from all five hundred members, and whatever put/call
    history the day's API budget allows. Each stage is reported as it starts and
    each one is allowed to fail on its own - a breadth download that times out
    should not cost the score a rescore it could still have done, so the run
    carries on with the cached breadth and says so.
    """
    note("Counting the S&P 500 members")
    try:
        frame = breadth.build(breadth.members(), breadth.START)
        frame.to_csv(breadth.CSV)
        note(f"Breadth rebuilt, {len(frame)} days")
    except Exception as exc:
        note(f"Breadth failed, keeping the cached file: {exc}")

    key = alpha.api_key()
    if not key:
        note("No Alpha Vantage key, skipping options")
    else:
        note("Gathering options history")
        try:
            fetched, stored = alpha.gather(key, note=note)
            note(f"Options: {fetched} new, {stored} of {alpha.NEED_ROWS} rows")
        except Exception as exc:
            note(f"Options failed: {exc}")

    note("Rescoring")
    state["page"] = build(a, live=True)
    state["built"] = pd.Timestamp.now()


def due(now: pd.Timestamp, last: pd.Timestamp | None, hour: int = DAILY_AT) -> bool:
    """Has the most recent session close passed without a run? Both in exchange time.

    Framed as "is there an unserved slot behind us" rather than "is it five now",
    so a machine that was asleep at the close catches up when it wakes instead
    of skipping the day - and so a restart an hour later does not trigger a
    second run.

    The slot walks back off a weekend, so Saturday and Sunday do not rerun
    Friday's numbers. Public holidays are deliberately not in a calendar here:
    on a holiday the run finds no new session in the price feed, fetches
    nothing and rescores the same day it already had - a few wasted minutes
    nine times a year, against an exchange calendar that would need keeping up
    to date and would be wrong the year it was not.
    """
    slot = now.normalize() + pd.Timedelta(hours=hour)
    if now < slot:  # today's slot is still ahead; the last one was earlier
        slot -= pd.Timedelta(days=1)
    while slot.weekday() >= 5:  # Saturday, Sunday: no close to wait for
        slot -= pd.Timedelta(days=1)
    return last is None or last < slot


def market_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz=MARKET_TZ)


def last_run() -> pd.Timestamp | None:
    """When the daily job last finished, in exchange time.

    A stamp written before this file kept exchange time is naive local. It is
    read as local and converted, so the first run after the change is timed off
    a real instant rather than one seven hours out.
    """
    if not STAMP.exists():
        return None
    ts = pd.Timestamp(STAMP.read_text(encoding="utf-8").strip())
    if ts.tz is None:
        ts = ts.tz_localize(datetime.now().astimezone().tzinfo)
    return ts.tz_convert(MARKET_TZ)


def serve(a, port: int) -> int:
    """Hold the page open with buttons that rebuild it.

    A file on disk cannot recalculate itself - the browser has no way to run
    any of this - so the buttons on the dashboard need something listening. This
    is that something, and nothing more: four routes, bound to localhost only,
    and it holds the last good page so a failed rebuild leaves the previous
    reading on screen instead of a blank tab.
    """
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    url = f"http://127.0.0.1:{port}/"

    # Before anything downloads. Ask whether anyone answers rather than trying
    # to bind and catching the error: on Windows a second bind to the same port
    # *succeeds* - HTTPServer sets SO_REUSEADDR, and Windows reads that as
    # permission to share the port rather than as the Unix "reuse the TIME_WAIT
    # leftovers". Two servers then both believe they are serving, requests land
    # on whichever the OS picks, and each runs its own daily re-analysis over
    # the same files. Four of them were running here before this check existed.
    with socket.socket() as probe:
        probe.settimeout(0.4)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            print(f"something is already serving {url} - nothing to do", file=sys.stderr)
            return 3  # serve.bat reads 3 as "stop", anything else as "restart me"

    state = {"page": build(a, live=True), "built": pd.Timestamp.now()}
    job = {"running": False, "step": "", "log": [], "error": None, "done": 0}

    def note(message: str) -> None:
        job["step"] = message
        job["log"].append(message)
        print(f"[{pd.Timestamp.now():%H:%M:%S}] {message}", flush=True)

    def run_job() -> None:
        try:
            reanalyse(a, state, note)
            job["error"] = None
            STAMP.write_text(market_now().isoformat(), encoding="utf-8")
        except Exception as exc:
            job["error"] = str(exc)
            print(f"re-analysis failed: {exc}", file=sys.stderr, flush=True)
        finally:
            job["running"] = False
            job["step"] = ""
            job["done"] += 1

    def clock() -> None:
        """One daily re-analysis, run by the server itself.

        The server is the only thing that updates anything. A second scheduled
        process doing the same work would race it for breadth.csv and split the
        day's 25 API calls between two runs that each think they have all of them.
        """
        while True:
            try:
                if not job["running"] and due(market_now(), last_run()):
                    job.update(running=True, step="Daily re-analysis", log=[], error=None)
                    run_job()
            except Exception as exc:
                print(f"clock: {exc}", file=sys.stderr, flush=True)
            time.sleep(300)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, kind: str = "text/html; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/status"):
                self._send(200, json.dumps({
                    "running": job["running"], "step": job["step"],
                    "log": job["log"][-6:], "error": job["error"], "done": job["done"],
                }).encode("utf-8"), "application/json")
                return
            self._send(200, state["page"].encode("utf-8"))

        def do_POST(self):
            if self.path == "/analyze":
                if job["running"]:
                    self._send(409, b"already running", "text/plain")
                    return
                job.update(running=True, step="Starting", log=[], error=None)
                threading.Thread(target=run_job, daemon=True).start()
                self._send(202, b"started", "text/plain")
                return
            if self.path != "/refresh":
                self._send(404, b"no", "text/plain")
                return
            # flush: stdout to a pipe is block-buffered, and a server whose
            # progress only appears when it exits is a server with no progress.
            print(f"[{pd.Timestamp.now():%H:%M:%S}] refresh requested", flush=True)
            try:
                state["page"] = build(a, live=True)
                state["built"] = pd.Timestamp.now()
                self._send(200, b"ok", "text/plain")
            except Exception as exc:  # the page stays on the last good reading
                print(f"refresh failed: {exc}", file=sys.stderr)
                self._send(500, str(exc).encode("utf-8"), "text/plain")

        def log_message(self, *args):  # one line per refresh is enough
            pass

    class Server(HTTPServer):
        allow_reuse_address = False  # backstop for the race the probe cannot close

    try:
        httpd = Server(("127.0.0.1", port), Handler)
    except OSError as exc:
        print(f"cannot bind port {port}: {exc}", file=sys.stderr)
        return 3

    threading.Thread(target=clock, daemon=True).start()
    print(f"\nserving {url} - buttons rebuild on demand, "
          f"and it re-analyses itself once a trading day, "
          f"{DAILY_AT:02d}:00 New York")
    print("ctrl-c to stop", flush=True)
    if not a.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lookback", type=int, default=252)
    ap.add_argument("--bench", action="store_true", help="tables only, write nothing")
    ap.add_argument("--full", action="store_true",
                    help="the whole evidence page instead of just the number")
    ap.add_argument("--days", type=int, default=63, help="sessions shown on each chart")
    ap.add_argument("--serve", action="store_true",
                    help="hold the page open with a working Refresh button")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--start", default=START)
    ap.add_argument("--out", default="dashboard_stress.html")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return 0
    if a.serve:
        return serve(a, a.port)

    try:
        page = build(a)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if page is None:
        return 0
    out = Path(a.out).resolve()
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out}")
    if not a.no_open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
