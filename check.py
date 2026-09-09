"""One command that answers "what is the chance of a fall right now", in Hebrew.

`stress.py` already does the work; this refreshes it and prints the few numbers
worth reading, so the daily check is one line instead of four commands.

A refresh that fails is a failure of this command too: a saved reading is only
printed when `--offline` asked for one, because a stale number presented as
today's is worse than no number. The wording of the event, the everyday
baseline and the model version come from `score_meta.json`, which `stress.py`
writes beside `score.csv` - nothing about the model is spelled out twice.

    python check.py            # refresh prices, rescore, print the summary
    python check.py --offline  # print the last saved reading, download nothing
    python check.py --selftest
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
CSV = HERE / "score.csv"
META = HERE / "score_meta.json"
NEEDED = ["score", "chance_pct", "percentile", "regime"]
TREND_BACK = 5  # observations back, not calendar days: rows are trading sessions
# A long weekend plus a holiday is four calendar days with no session. Past
# that, silence is a broken feed rather than a closed market.
MAX_STALE_DAYS = 5
TIMEOUT = 900  # seconds per script; stress.py downloads twenty-odd tickers


def run(cmd: list[str]) -> None:
    """One script, or an exception carrying what it said before it died."""
    try:
        r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True,
                           timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{cmd[1]} timed out after {TIMEOUT}s")
    if r.returncode:
        said = "\n".join(x for x in (r.stdout.strip(), r.stderr.strip()) if x)
        raise RuntimeError(f"{cmd[1]} failed (exit {r.returncode}):\n{said}")


def refresh() -> None:
    """Rescore off fresh prices, or raise. The HTML page goes to a temp file.

    Fail-fast on purpose: if `fear.py` cannot reach CNN, `stress.py` does not
    run either, and nothing downstream gets to read a file that was never
    rewritten. The file must also actually move - `stress.py` exiting 0 while
    writing the same day again is not a refresh.
    """
    before = (CSV.stat().st_mtime, last_date(CSV)) if CSV.exists() else None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "stress_check.html"
        run([sys.executable, "fear.py"])
        run([sys.executable, "stress.py", "--out", str(out), "--no-open"])
    if not CSV.exists():
        raise RuntimeError(f"stress.py exited 0 but wrote no {CSV.name}")
    if before and (CSV.stat().st_mtime, last_date(CSV)) == before:
        raise RuntimeError(f"{CSV.name} did not change - the rescore did nothing")


def last_date(path: Path) -> pd.Timestamp | None:
    try:
        return pd.read_csv(path, index_col=0, parse_dates=True).index[-1]
    except Exception:
        return None


def load(path: Path) -> pd.DataFrame:
    """The saved series, or an exception naming what is wrong with it."""
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
    except FileNotFoundError:
        raise RuntimeError(f"no {path.name} - run without --offline once")
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise RuntimeError(f"{path.name} is not readable: {exc}")
    return validate(df, path.name)


def validate(df: pd.DataFrame, name: str = "score.csv") -> pd.DataFrame:
    """Sorted, de-duplicated, and in range - or an exception saying which."""
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        raise RuntimeError(f"{name} is missing {', '.join(missing)}")
    if df.empty:
        raise RuntimeError(f"{name} has no rows")
    if not isinstance(df.index, pd.DatetimeIndex) or df.index.isna().any():
        raise RuntimeError(f"{name} has dates that are not dates")
    # A duplicated day is one run written over another; the later row wins.
    df = df[~df.index.duplicated(keep="last")].sort_index()
    last = df.iloc[-1]
    for col in ("chance_pct", "percentile"):
        if not 0 <= float(last[col]) <= 100:
            raise RuntimeError(f"{name}: {col} is {last[col]}, not a percentage")
    if not pd.notna(last["score"]) or abs(float(last["score"])) == float("inf"):
        raise RuntimeError(f"{name}: score is {last['score']}")
    return df


def meta() -> dict:
    try:
        return json.loads(META.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"no {META.name} - run without --offline once")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{META.name} is not readable: {exc}")


def reading(df: pd.DataFrame, m: dict, today: pd.Timestamp) -> dict:
    """The numbers, without a word of Hebrew. Formatting is the next function."""
    last = df.iloc[-1]
    if last["regime"] not in m["regimes"]:
        raise RuntimeError(f"regime {last['regime']!r} is not one this model has")
    stale = (today.normalize() - df.index[-1].normalize()).days
    return {
        "date": df.index[-1],
        "stale_days": stale,
        "chance_pct": float(last["chance_pct"]),
        "percentile": float(last["percentile"]),
        "regime": str(last["regime"]),
        # None, not 0.0: fewer rows than the window means no trend, and a
        # printed +0.0 reads like a flat market rather than a missing answer.
        "trend": (float(last["score"] - df["score"].iloc[-1 - TREND_BACK])
                  if len(df) > TREND_BACK else None),
        "drop_pct": abs(float(m["event_depth"])) * 100,
        "days": int(m["event_days"]),
        "baseline": float(m["baseline_rate"]),
        "version": str(m["model_version"]),
    }


def lines(r: dict, live: bool) -> list[str]:
    out = [
        f"תאריך הנתון: {r['date']:%d.%m.%Y}",
        f"סיכוי לנפילה של {r['drop_pct']:.0f}% ב-{r['days']} מפגשים: {r['chance_pct']:.1f}%",
        f"ציון גולמי (MSS): {r['percentile']:.1f}   מצב: {r['regime']}",
        f"מגמה מול {TREND_BACK} תצפיות אחורה: "
        + (f"{r['trend']:+.1f}" if r["trend"] is not None else "לא מספיק נתונים"),
        f"בסיס היסטורי לכל יום: {r['baseline']:.1f}%",
        "מקור: נתונים שרועננו כעת" if live else "מקור: קריאה שמורה (--offline)",
        f"גרסת מודל: {r['version']}",
    ]
    if r["stale_days"] > MAX_STALE_DAYS:
        out.append(f"אזהרה: הנתון בן {r['stale_days']} ימים — לא 'המצב עכשיו'")
    return out


def fear_line(risk_date: pd.Timestamp) -> str | None:
    """CNN beside the score, never inside it - and only if it is the same week."""
    try:
        f = pd.read_csv(HERE / "fear.csv", index_col=0, parse_dates=True)["fear_greed"]
    except Exception:
        return None
    gap = (risk_date.normalize() - f.index[-1].normalize()).days
    note = f" (פער {gap} ימים מהנתון)" if abs(gap) > MAX_STALE_DAYS else ""
    return (f"סנטימנט CNN: {f.iloc[-1]:.1f} ({f.index[-1]:%d.%m}){note}"
            " — להקשר בלבד, לא בציון")


def summary(live: bool) -> tuple[str, bool]:
    """The printable block, and whether the reading is fresh enough to trust."""
    r = reading(load(CSV), meta(), pd.Timestamp(datetime.now()))
    out = lines(r, live)
    fear = fear_line(r["date"])
    if fear:
        out.append(fear)
    return "\n".join(out), r["stale_days"] <= MAX_STALE_DAYS


def selftest() -> None:
    idx = pd.to_datetime([f"2026-09-{d:02d}" for d in range(1, 8)])
    good = pd.DataFrame({"score": range(7), "chance_pct": 20.0, "percentile": 50.0,
                         "regime": "WATCH", "walk_forward": True}, index=idx)
    m = {"regimes": ["WATCH", "NORMAL"], "event_depth": -0.05, "event_days": 20,
         "baseline_rate": 15.8, "model_version": "test"}
    r = reading(good, m, pd.Timestamp("2026-09-08"))
    assert r["trend"] == 5.0, r          # row 7 minus row 2, five observations back
    assert r["stale_days"] == 1, r
    # Under the window there is no trend to report, and 0.0 would be a lie.
    assert reading(good.iloc[:3], m, pd.Timestamp("2026-09-08"))["trend"] is None
    for bad, why in [
        (good.drop(columns=["chance_pct"]), "missing column"),
        (good.iloc[:0], "empty"),
        (good.assign(chance_pct=140.0), "out of range"),
        (good.assign(score=float("nan")), "not finite"),
    ]:
        try:
            validate(bad)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{why} was accepted")
    # A day written twice keeps the later row rather than doubling the series.
    twice = pd.concat([good, good.iloc[[-1]].assign(percentile=61.0)])
    assert len(validate(twice)) == 7
    assert validate(twice)["percentile"].iloc[-1] == 61.0
    # An unlisted regime is a file this model did not write.
    try:
        reading(good.assign(regime="PANIC"), m, pd.Timestamp("2026-09-08"))
    except RuntimeError:
        pass
    else:
        raise AssertionError("unknown regime was accepted")
    print("selftest ok")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="read score.csv, download nothing")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return 0
    try:
        if not a.offline:
            refresh()
        text, fresh = summary(live=not a.offline)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    return 0 if fresh else 1


if __name__ == "__main__":
    raise SystemExit(main())
