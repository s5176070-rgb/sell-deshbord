"""The work plan makes four testable claims. This file tests them.

A plan is not evidence. Each of these is stated in the plan as a fact about the
market, each is cheap to measure against twenty years of prices, and each is
measured here without adjustment so the answer can disagree.

  1. Breaking the 50-day average is worth about a 3.7% correction.
  2. Breaking the 150-day marks a significant one, around 8% off the high.
  3. The 200-day is the strategic decision point for the long-term trend.
  4. The confluence trigger - price 8% over its 150-day, VIX under 13, and more
     than 70% of the index above its own 50-day - marks distribution.

    python plan_checks.py
"""
from __future__ import annotations

import pandas as pd

import breadth
from cvs import closes
from stress import START, TICKERS, fwd_drawdown

MAS = [50, 150, 200]
AFTER = 60  # sessions to follow a break before calling the episode over


def breaks(spx: pd.Series, window: int) -> pd.DataFrame:
    """Every first close below the average after a spell above it.

    Reported per episode, not per day: a market that chops around its 50-day
    for a month is one break, and counting each day would turn one correction
    into thirty observations of itself.
    """
    ma = spx.rolling(window).mean()
    below = spx < ma
    first = below & ~below.shift(1, fill_value=False)
    rows = []
    for date in spx.index[first.fillna(False)]:
        i = spx.index.get_loc(date)
        after = spx.iloc[i:i + AFTER]
        peak = spx.iloc[max(0, i - AFTER):i + 1].max()
        rows.append({
            "date": date,
            "from_peak": (after.min() / peak - 1) * 100,
            "from_break": (after.min() / spx.loc[date] - 1) * 100,
            "recovered": bool((after >= peak).any()),
        })
    return pd.DataFrame(rows).set_index("date")


def summary(spx: pd.Series) -> pd.DataFrame:
    """Median and mean depth after a break of each average."""
    rows = []
    for w in MAS:
        b = breaks(spx, w)
        rows.append({
            "average": f"{w}-day",
            "breaks": len(b),
            "median_from_peak": b["from_peak"].median(),
            "mean_from_peak": b["from_peak"].mean(),
            "median_from_break": b["from_break"].median(),
            "recovered_in_60d": b["recovered"].mean() * 100,
        })
    return pd.DataFrame(rows).set_index("average")


def trigger(px: pd.DataFrame, br: pd.DataFrame) -> pd.DataFrame:
    """The plan's distribution trigger, and each of its three legs alone."""
    spx, vix = px["^GSPC"], px["^VIX"]
    s5fi = br["s5fi"].reindex(px.index).ffill(limit=5)
    legs = {
        "stretched (>150MA x1.08)": spx > spx.rolling(150).mean() * 1.08,
        "calm (VIX < 13)": vix < 13,
        "broad (S5FI > 70)": s5fi > 70,
    }
    legs["all three (plan trigger)"] = legs["stretched (>150MA x1.08)"] & legs["calm (VIX < 13)"] & legs["broad (S5FI > 70)"]
    hit = fwd_drawdown(spx) <= -0.05
    base = hit[s5fi.notna()].mean()
    rows = [{"condition": "any day", "days": int(s5fi.notna().sum()),
             "event_rate": base * 100, "lift": 1.0}]
    for name, m in legs.items():
        m = m & s5fi.notna()
        rows.append({
            "condition": name, "days": int(m.sum()),
            "event_rate": hit[m].mean() * 100 if m.any() else float("nan"),
            "lift": (hit[m].mean() / base) if m.any() and base else float("nan"),
        })
    return pd.DataFrame(rows).set_index("condition")


def main() -> int:
    px, _ = closes(TICKERS, START)
    br = breadth.load()
    spx = px["^GSPC"]

    print("Claims 1-3: what a break of each average actually cost, "
          f"{spx.index[0]:%Y}-{spx.index[-1]:%Y}\n")
    print(summary(spx).round(2).to_string())
    print("\n  from_peak  = deepest close in the next 60 sessions, against the prior high")
    print("  from_break = the same, measured from the day of the break itself")

    if br.empty:
        print("\nno breadth.csv - skipping the trigger; build it with `python breadth.py`")
        return 0
    print(f"\n\nClaim 4: the distribution trigger, on days breadth data exists\n")
    print(trigger(px, br).round(2).to_string())
    print("\n  event_rate = a 5% fall within 20 sessions. lift = against the all-day rate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
