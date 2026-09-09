"""Score the score: is `chance_pct` a probability, or just a number that rises?

`stress.py --bench` already answers whether the model separates calm days from
dangerous ones. It does not answer whether "20%" means twenty percent, and the
two are different questions - a model that ranks days perfectly can still be
wrong about every level, and a model that is right on average can rank no
better than a coin. This measures both, and keeps them apart:

    discrimination  does a higher reading really come before more falls (AUC)
    calibration     when it says 20%, do 20% of those days fall (Brier, curve)

Every number here is computed only on the walk-forward days, against the same
event `stress.py` calibrated on, and always beside the same fixed-15.8%-every-
day baseline. A Brier score alone means nothing; the comparison is the finding.

    python eval.py            # the tables
    python eval.py --offline  # skip the price download, if spx.csv is cached
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from cvs import BANDS, closes
from stress import EVENT_DAYS, EVENT_DEPTH, START, fwd_drawdown

HERE = Path(__file__).parent
CACHE = HERE / "spx.csv"   # one column, so eval.py can be re-run without waiting


def hits(index: pd.Index, offline: bool) -> pd.Series:
    """Did the event follow each day - the same test stress.py calibrated on."""
    if offline or CACHE.exists():
        spx = pd.read_csv(CACHE, index_col=0, parse_dates=True).iloc[:, 0]
    else:
        spx = closes(["^GSPC"], START)[0]["^GSPC"].dropna()
        spx.to_csv(CACHE, index_label="date", header=True)
    return (fwd_drawdown(spx.reindex(index)) <= EVENT_DEPTH)


def brier(p: pd.Series, y: pd.Series) -> float:
    """Mean squared error of a probability. Lower is better; 0.25 is a coin."""
    return float(((p - y) ** 2).mean())


def auc(p: pd.Series, y: pd.Series) -> float:
    """Chance a random event day scored above a random quiet one. 0.5 is nothing.

    The rank form of the Mann-Whitney statistic, which handles ties by giving
    them half credit - and there are ties, because a flat market produces the
    same reading for days on end.
    """
    pos, neg = y.sum(), (~y).sum()
    if not pos or not neg:
        return float("nan")
    r = p.rank()
    return float((r[y].sum() - pos * (pos + 1) / 2) / (pos * neg))


def reliability(p: pd.Series, y: pd.Series, bins: int = 10) -> pd.DataFrame:
    """Predicted against observed, in equal-count buckets. The calibration test.

    `gap` is what the model owes: positive means it promised more falls than
    arrived. `ci` is the 95% half-width on the observed rate, so a gap smaller
    than the interval beside it is not evidence of anything.
    """
    g = pd.qcut(p, bins, labels=False, duplicates="drop")
    out = pd.DataFrame({"g": g, "p": p, "y": y}).groupby("g").agg(
        said=("p", "mean"), happened=("y", "mean"), days=("y", "size"))
    out[["said", "happened"]] *= 100
    out["gap"] = out["said"] - out["happened"]
    rate = out["happened"] / 100
    out["ci"] = 1.96 * np.sqrt(rate * (1 - rate) / out["days"]) * 100
    return out.round(2)


def by_regime(df: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    """Per-band hit rate and error, including the bands nobody looks at.

    A model can be honest overall and badly wrong exactly where it is used. The
    CRITICAL row is the one that matters and the one with the fewest days, so
    it carries its own interval rather than borrowing the table's credibility.
    """
    rows = []
    for name in [n for n, _, _ in BANDS] + ["NORMAL"]:
        m = df["regime"] == name
        if not m.any():
            rows.append({"regime": name, "days": 0})
            continue
        rate = float(y[m].mean())
        rows.append({
            "regime": name, "days": int(m.sum()),
            "said": round(float(df.loc[m, "chance_pct"].mean()), 2),
            "happened": round(rate * 100, 2),
            "ci": round(1.96 * float(np.sqrt(rate * (1 - rate) / m.sum())) * 100, 2),
            "brier": round(brier(df.loc[m, "chance_pct"] / 100, y[m]), 4),
        })
    return pd.DataFrame(rows).set_index("regime")


def errors(df: pd.DataFrame, y: pd.Series, flag: float) -> dict:
    """What the model gets wrong when it is read as a yes/no call at `flag`.

    Precision and recall need a threshold to exist at all, so one is named here
    rather than implied. This is a diagnostic of the score, NOT a trading rule:
    `chance_pct` crossing a line is not an instruction to sell, and the counts
    below are here to show what such a rule would have cost.
    """
    said = df["chance_pct"] >= flag
    fp, fn = int((said & ~y).sum()), int((~said & y).sum())
    quiet = df["regime"] == "NORMAL"
    return {
        "threshold_pct": flag,
        "days_flagged": int(said.sum()),
        "precision": round(float(y[said].mean()) if said.any() else float("nan"), 3),
        "recall": round(float(said[y].mean()) if y.any() else float("nan"), 3),
        "false_positives": fp,
        # A false alarm in a market that was visibly calm is the expensive kind:
        # nothing on the screen agreed with the number.
        "false_positives_in_normal": int((said & ~y & quiet).sum()),
        "false_negatives": fn,
        # And the falls that arrived while the model was reading NORMAL are the
        # ones it had no way to warn about.
        "false_negatives_in_normal": int((~said & y & quiet).sum()),
    }


def periods(p: pd.Series, y: pd.Series, every: int = 5) -> pd.DataFrame:
    """The same two numbers per sub-period. One good decade can carry a model."""
    rows = []
    for start in range(p.index[0].year // every * every, p.index[-1].year + 1, every):
        m = (p.index.year >= start) & (p.index.year < start + every)
        if m.sum() < 100:
            continue
        rows.append({"period": f"{start}-{start + every - 1}", "days": int(m.sum()),
                     "events_pct": round(float(y[m].mean()) * 100, 2),
                     "brier": round(brier(p[m], y[m]), 4),
                     # Within one period the curve barely moves, so this is much
                     # closer to the MSS line than the pooled figure above.
                     "auc": round(auc(p[m], y[m]), 3)})
    return pd.DataFrame(rows).set_index("period")


def report(offline: bool = False, flag: float = 25.0) -> str:
    df = pd.read_csv(HERE / "score.csv", index_col=0, parse_dates=True)
    meta = json.loads((HERE / "score_meta.json").read_text(encoding="utf-8"))
    # Walk-forward only. The fitted era read off a curve that had seen its own
    # outcomes, and scoring the model there is scoring it on its answer sheet.
    df = df[df["walk_forward"].astype(bool)]
    # And only the days that got a chance at all. Before the first curve with
    # MIN_CAL days behind it there is no forecast to score - see stress.py.
    df = df[df["chance_pct"].notna()]
    y = hits(df.index, offline)
    # The tail has a forward window that runs off the end of the data, exactly
    # as event_rate drops it, and for the same reason.
    df, y = df.iloc[:-EVENT_DAYS], y.iloc[:-EVENT_DAYS]
    p = df["chance_pct"] / 100
    # The bar is a fixed forecast at the rate of the days actually being scored,
    # not the all-history rate in the meta file: those cover a different, more
    # violent stretch, and a baseline handed the wrong constant is not a bar.
    rate = float(y.mean())
    base = pd.Series(rate, index=p.index)

    out = [f"calibrated walk-forward {df.index[0]:%Y-%m-%d} to {df.index[-1]:%Y-%m-%d}, "
           f"{len(df)} days, {int(y.sum())} of them followed by the event",
           f"event: {meta['event_definition']}",
           "",
           "-- calibration: does 20% mean 20% --",
           f"brier  model {brier(p, y):.4f}   "
           f"fixed {rate * 100:.1f}% every day {brier(base, y):.4f}   "
           f"lower is better",
           reliability(p, y).to_string(),
           "",
           "-- discrimination: does a higher reading come first --",
           # Two AUCs, because they answer different questions and here they
           # disagree. The MSS is one scale for the whole history. chance_pct
           # is read off a curve redrawn every January, so the same MSS maps to
           # a different percentage in 2003 and in 2026 - ranking the two
           # against each other compares readings that were never on the same
           # scale. A large gap between these lines is a property of the
           # walk-forward design, not a fault in the factors.
           f"auc on MSS        {auc(df['percentile'], y):.3f}   one scale, whole history",
           f"auc on chance_pct {auc(p, y):.3f}   pooled across curves",
           "0.5 is a coin, and neither line says anything about the levels above",
           "",
           "-- per regime --",
           by_regime(df, y).to_string(),
           "",
           "-- sub-periods --",
           periods(p, y).to_string(),
           "",
           f"-- read as a yes/no call at {flag:.0f}%, which it is not --",
           json.dumps(errors(df, y, flag), indent=2)]
    return "\n".join(out)


def selftest() -> None:
    """The metrics on series whose answers are known by construction."""
    idx = pd.bdate_range("2020-01-01", periods=200)
    y = pd.Series([True, False] * 100, index=idx)
    # A forecaster that says 50% every day on a 50% market: brier 0.25, no skill.
    assert abs(brier(pd.Series(0.5, index=idx), y) - 0.25) < 1e-9
    assert abs(auc(pd.Series(0.5, index=idx), y) - 0.5) < 1e-9
    # One that knows the answer: brier 0, auc 1.
    perfect = y.astype(float)
    assert brier(perfect, y) == 0.0 and auc(perfect, y) == 1.0
    # And one that has it exactly backwards ranks below a coin.
    assert auc(1 - perfect, y) == 0.0
    r = reliability(perfect, y, bins=2)
    assert (r["gap"].abs() < 1e-9).all(), r      # perfect knowledge is calibrated
    e = errors(pd.DataFrame({"chance_pct": perfect * 100,
                             "regime": "NORMAL"}, index=idx), y, flag=50)
    assert e["precision"] == 1.0 and e["recall"] == 1.0 and e["false_positives"] == 0
    print("eval selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help=f"read {CACHE.name}, download nothing")
    ap.add_argument("--flag", type=float, default=25.0, help="threshold for the yes/no table")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if a.selftest:
        selftest()
        return 0
    print(report(a.offline, a.flag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
