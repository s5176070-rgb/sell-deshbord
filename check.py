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
# Below this many days behind the reading, the calibration bucket is a story
# about a handful of episodes rather than a rate worth a decimal point.
LOW_N = 100
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


def margin(rate_pct: float, n: int) -> float:
    """Half-width of the 95% interval around a rate, in percentage points."""
    p = rate_pct / 100
    return 1.96 * ((p * (1 - p) / n) ** 0.5) * 100 if n else float("inf")


def reading(df: pd.DataFrame, m: dict, today: pd.Timestamp) -> dict:
    """The numbers, without a word of Hebrew. Formatting is the next function."""
    last = df.iloc[-1]
    if last["regime"] not in m["regimes"]:
        raise RuntimeError(f"regime {last['regime']!r} is not one this model has")
    cal = m.get("calibration", {})
    n = int(cal.get("bucket_days", 0))
    chance = float(last["chance_pct"])
    base = float(m["baseline_rate"])
    err = margin(chance, n)
    return {
        "date": df.index[-1],
        "stale_days": (today.normalize() - df.index[-1].normalize()).days,
        "chance_pct": chance,
        "margin_pp": err,
        "bucket_days": n,
        # A bucket this thin is a handful of past episodes, not a rate. Say so
        # rather than printing a decimal that implies a measurement.
        "low_confidence": n < LOW_N,
        # Three different numbers, and the column names in score.csv are not a
        # reliable guide to which is which. `percentile` is the raw MSS, the
        # average of the factor percentiles, and the number the regime bands are
        # cut on. `score` is only where that day's chance sits inside the range
        # its own calibration curve spanned - a display scale, not a reading.
        # `chance_pct` is the calibrated rate and the only one in probability.
        "mss": float(last["percentile"]),
        "curve_pos": float(last["score"]),
        "regime": str(last["regime"]),
        # Movement in the number the block prints, not in a column nobody sees.
        # None, not 0.0: fewer rows than the window means no trend, and a
        # printed +0.0 reads like a flat market rather than a missing answer.
        "trend": (float(last["percentile"] - df["percentile"].iloc[-1 - TREND_BACK])
                  if len(df) > TREND_BACK else None),
        "drop_pct": abs(float(m["event_depth"])) * 100,
        "days": int(m["event_days"]),
        "baseline": base,
        "lift": chance / base if base else float("nan"),   # a ratio, unitless
        "excess_pp": chance - base,                        # percentage points
        "version": str(m["model_version"]),
        "computed_at": str(m.get("computed_at", "")),
        "walk_forward": bool(last.get("walk_forward", True)),
    }


def lines(r: dict, live: bool, verbose: bool = False) -> list[str]:
    """The Hebrew block. Estimate first, caveats after, never an instruction."""
    err = r["margin_pp"]
    out = [
        "— הערכת סיכון —",
        f"תאריך הנתון: {r['date']:%d.%m.%Y}",
        # Whole percents: the interval below is wider than a tenth of a point,
        # so a decimal here would be precision the sample cannot carry.
        f"סיכוי לנפילה של {r['drop_pct']:.0f}% ב-{r['days']} מפגשים: ~{r['chance_pct']:.0f}%"
        + (f" (טווח {r['chance_pct'] - err:.0f}–{r['chance_pct'] + err:.0f}%,"
           f" מדגם {r['bucket_days']} ימים)" if r["bucket_days"] else ""),
        f"בסיס היסטורי לכל יום: {r['baseline']:.0f}%  —  "
        f"פי {r['lift']:.2f} מהבסיס, {r['excess_pp']:+.0f} נקודות אחוז",
        f"ציון גולמי (MSS): {r['mss']:.0f} מתוך 100 — ממוצע אחוזוני הגורמים, "
        "לא הסתברות",
        f"מצב: {r['regime']} (סיווג לפי סף על ה-MSS, לא הסתברות)",
        f"מגמה מול {TREND_BACK} תצפיות אחורה: "
        + (f"{r['trend']:+.0f}" if r["trend"] is not None else "לא מספיק נתונים"),
    ]
    if r["low_confidence"]:
        out.append(f"LOW CONFIDENCE — הקריאה נשענת על {r['bucket_days']} ימים בלבד")
    if not r["walk_forward"]:
        out.append("שים לב: היום הזה בתקופה המותאמת (לא walk-forward) — ראיה חלשה יותר")
    if r["stale_days"] > MAX_STALE_DAYS:
        out.append(f"אזהרה: הנתון בן {r['stale_days']} ימים — לא 'המצב עכשיו'")
    old = age_days(r["computed_at"])
    if old > MAX_STALE_DAYS:
        out.append(f"אזהרה: החישוב עצמו בן {old:.0f} ימים")
    out += [
        "מקור: נתונים שרועננו כעת" if live else "מקור: קריאה שמורה (--offline)",
        f"גרסת מודל: {r['version']}   חושב: {r['computed_at'] or 'לא ידוע'}",
        "— זו הערכת סיכון בלבד, לא הוראת פעולה —",
    ]
    if verbose:
        out.append(json.dumps(r, indent=2, ensure_ascii=False, default=str))
    return out


def age_days(stamp: str) -> float:
    """Days since an ISO timestamp, comparing aware to aware."""
    if not stamp:
        return 0.0
    when = pd.Timestamp(stamp)
    now = pd.Timestamp(datetime.now(when.tz) if when.tz else datetime.now())
    return (now - when).total_seconds() / 86400


def fear_line(risk_date: pd.Timestamp, today: pd.Timestamp) -> str | None:
    """CNN beside the score, never inside it, and never without its date.

    Two different distances matter and neither is the other: how old the CNN
    reading is, and how far it sits from the day the risk number is about.
    """
    try:
        f = pd.read_csv(HERE / "fear.csv", index_col=0, parse_dates=True)["fear_greed"]
    except Exception:
        return None
    if f.empty:
        return None
    when = f.index[-1].normalize()
    gap = abs((risk_date.normalize() - when).days)
    old = (today.normalize() - when).days
    note = f" — פער {gap} ימים מיום הסיכון" if gap > MAX_STALE_DAYS else ""
    if old > MAX_STALE_DAYS:
        note += f", והקריאה עצמה בת {old} ימים"
    return (f"סנטימנט CNN: {f.iloc[-1]:.0f} ({when:%d.%m}){note}"
            " — להקשר בלבד, לא בציון")


def digest_ok(m: dict) -> bool:
    """Do score.csv and score_meta.json come from the same run?"""
    want = m.get("score_sha256")
    if not want:
        return True   # meta from an older stress.py; the freshness gate still applies
    import hashlib
    return hashlib.sha256(CSV.read_bytes()).hexdigest()[:len(want)] == want


def summary(live: bool, verbose: bool = False) -> tuple[dict, str, bool]:
    """The reading, the printable block, and whether it is fit to answer with."""
    m = meta()
    now = pd.Timestamp(datetime.now())
    r = reading(load(CSV), m, now)
    if not digest_ok(m):
        raise RuntimeError("score.csv and score_meta.json are from different runs")
    out = lines(r, live, verbose)
    fear = fear_line(r["date"], now)
    if fear:
        out.append(fear)
    return r, "\n".join(out), r["stale_days"] <= MAX_STALE_DAYS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="read score.csv, download nothing")
    ap.add_argument("--json", action="store_true", help="the reading as JSON, for scripts")
    ap.add_argument("--verbose", "--debug", action="store_true", dest="verbose",
                    help="append every field the summary was built from")
    ap.add_argument("--selftest", action="store_true", help="run test_check.py")
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):  # not every stream is a real console
        sys.stdout.reconfigure(encoding="utf-8")
    if a.selftest:
        import test_check
        return test_check.main()
    try:
        if not a.offline:
            refresh()
        r, text, fresh = summary(live=not a.offline, verbose=a.verbose)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1
    if a.json:
        r = dict(r, date=f"{r['date']:%Y-%m-%d}", live=not a.offline, fresh=fresh)
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        print(text)
    return 0 if fresh else 1


if __name__ == "__main__":
    raise SystemExit(main())
