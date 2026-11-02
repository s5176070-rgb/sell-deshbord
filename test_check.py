"""Checks for the reading layer: `python test_check.py`, or `check.py --selftest`.

Plain asserts, no framework and no network. The unit half feeds `check.py`
hand-built frames; the integration half runs the real command in a scratch copy
of the project with stub scripts, which is the only way to prove that a failed
refresh stops the summary and that `--offline` spawns nothing at all.

The band boundaries are checked here too. They are a published number - a day
at 45.0 is WATCH and a day at 44.9 is not - and a test is the only thing that
makes moving them a deliberate act rather than a typo.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

import check
from cvs import BANDS, regimes

HERE = Path(__file__).parent
META = {"regimes": ["CRITICAL", "ELEVATED", "WATCH", "NORMAL"], "event_depth": -0.05,
        "event_days": 20, "baseline_rate": 15.8, "model_version": "test",
        "calibration": {"bucket_days": 500}}
NOW = pd.Timestamp("2026-09-08")


def frame(rows: int = 7, end: pd.Timestamp = NOW, **over) -> pd.DataFrame:
    """`rows` consecutive days ending on `end`, all fields inside their range."""
    idx = pd.date_range(end=end.normalize(), periods=rows, freq="D")
    df = pd.DataFrame({"score": range(rows), "chance_pct": 20.0,
                       "percentile": [40.0 + i for i in range(rows)],
                       "regime": "WATCH", "walk_forward": True}, index=idx)
    return df.assign(**over) if over else df


def raises(fn, why: str) -> None:
    try:
        fn()
    except RuntimeError:
        return
    raise AssertionError(f"{why} was accepted")


def test_reading() -> None:
    r = check.reading(frame(), META, NOW)
    assert r["stale_days"] == 0, r
    # The three numbers are read from the columns that really hold them.
    assert (r["mss"], r["curve_pos"], r["chance_pct"]) == (46.0, 6.0, 20.0), r
    # Trend moves with the MSS the block prints, not with the display scale.
    assert r["trend"] == 5.0, r        # row 7 minus row 2: five observations back
    assert round(r["lift"], 2) == round(20.0 / 15.8, 2), r
    assert round(r["excess_pp"], 1) == 4.2, r
    assert not r["low_confidence"]
    # Under the window there is no trend to report, and 0.0 would be a lie.
    assert check.reading(frame(3), META, NOW)["trend"] is None
    # A thin bucket is said out loud rather than dressed up with a decimal.
    thin = dict(META, calibration={"bucket_days": 12})
    assert check.reading(frame(), thin, NOW)["low_confidence"]
    assert check.reading(frame(), thin, NOW)["margin_pp"] > 10
    raises(lambda: check.reading(frame(regime="PANIC"), META, NOW), "unknown regime")


def test_validate() -> None:
    for bad, why in [
        (frame().drop(columns=["chance_pct"]), "missing column"),
        (frame().drop(columns=["regime"]), "missing regime"),
        (frame().iloc[:0], "empty frame"),
        (frame(chance_pct=140.0), "chance over 100"),
        (frame(chance_pct=-1.0), "chance under 0"),
        (frame(percentile=101.0), "percentile over 100"),
        (frame(score=float("nan")), "score not finite"),
        (frame(score=float("inf")), "score infinite"),
    ]:
        raises(lambda b=bad: check.validate(b), why)
    # A day written twice keeps the later row rather than doubling the series.
    good = frame()
    twice = pd.concat([good, good.iloc[[-1]].assign(percentile=61.0)])
    assert len(check.validate(twice)) == 7
    assert check.validate(twice)["percentile"].iloc[-1] == 61.0
    # Rows written out of order are sorted before the last one is taken.
    assert check.validate(good.iloc[::-1]).index.is_monotonic_increasing
    # A text index is not a date index, however plausible it looks.
    raises(lambda: check.validate(good.reset_index(drop=True)), "integer index")


def test_lines() -> None:
    """Stale says so, fresh does not, and neither ever tells anyone to act."""
    r = check.reading(frame(), META, NOW + pd.Timedelta(days=30))
    assert r["stale_days"] == 30, r
    out = "\n".join(check.lines(r, live=False))
    assert "אזהרה" in out, out
    assert "--offline" in out, out        # the source is always named
    assert "לא הוראת פעולה" in out, out   # estimate and action stay apart
    assert "סיווג לפי סף על ה-MSS" in out, out
    assert "ממוצע אחוזוני הגורמים" in out, out
    fresh = "\n".join(check.lines(check.reading(frame(), META, NOW), live=True))
    assert "אזהרה" not in fresh, fresh
    assert "רועננו כעת" in fresh, fresh


def test_fear(tmp: Path) -> None:
    """CNN is optional, dated, and never silently aligned to the risk day."""
    old, check.HERE = check.HERE, tmp
    try:
        assert check.fear_line(NOW, NOW) is None          # no file at all
        f = pd.Series([39.5], index=pd.to_datetime(["2026-09-07"]), name="fear_greed")
        f.to_csv(tmp / "fear.csv", index_label="date")
        assert "פער" not in check.fear_line(NOW, NOW)
        f.rename(index={f.index[0]: pd.Timestamp("2026-08-01")}).to_csv(
            tmp / "fear.csv", index_label="date")
        line = check.fear_line(NOW, NOW)
        assert "פער 38 ימים" in line, line
        assert "לא בציון" in line, line   # context, never a scored factor
    finally:
        check.HERE = old


def test_bands() -> None:
    """The published thresholds, one tenth of a point either side of each."""
    for name, enter, exit_at in BANDS:
        assert regimes(pd.Series([float(enter)])).iloc[0] == name
        assert regimes(pd.Series([enter - 0.1])).iloc[0] != name
        # Hysteresis: a band is held down to its exit level, not to its entry.
        held = regimes(pd.Series([float(enter), float(exit_at), exit_at - 0.1]))
        assert held.iloc[1] == name, list(held)
        assert held.iloc[2] != name, list(held)
    assert regimes(pd.Series([0.0])).iloc[0] == "NORMAL"


def project(tmp: Path, stress: str, fear: str = "raise SystemExit(0)") -> Path:
    """A scratch project: the real check.py, stub scripts, one saved reading."""
    home = tmp / f"run{len(list(tmp.iterdir()))}"
    home.mkdir()
    shutil.copy(HERE / "check.py", home / "check.py")
    (home / "fear.py").write_text(fear, encoding="utf-8")
    (home / "stress.py").write_text(stress, encoding="utf-8")
    today = pd.Timestamp.now().normalize()
    frame(end=today).to_csv(home / "score.csv", index_label="date")
    digest = hashlib.sha256((home / "score.csv").read_bytes()).hexdigest()[:16]
    (home / "score_meta.json").write_text(json.dumps(dict(
        META, data_as_of=f"{today:%Y-%m-%d}", computed_at=today.isoformat(),
        score_sha256=digest)), encoding="utf-8")
    return home


def run(home: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "check.py", *args], cwd=home,
                          capture_output=True, text=True, encoding="utf-8",
                          timeout=120, env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def test_refresh_failure(tmp: Path) -> None:
    """A refresh that fails must not fall back to the saved reading."""
    home = project(tmp, stress='import sys; print("boom", file=sys.stderr); '
                               'raise SystemExit(3)')
    r = run(home)
    assert r.returncode == 1, r
    assert "boom" in r.stderr, r.stderr        # what the script said, not a traceback
    assert "Traceback" not in r.stderr, r.stderr
    assert "סיכוי" not in r.stdout, r.stdout   # and no number was printed
    # fear.py failing stops the run before stress.py is even started.
    home = project(tmp, stress="open('ran', 'w')", fear="raise SystemExit(2)")
    assert run(home).returncode == 1
    assert not (home / "ran").exists(), "stress.py ran after fear.py failed"


def test_unchanged_score(tmp: Path) -> None:
    """stress.py exiting 0 without rewriting the file is not a refresh."""
    r = run(project(tmp, stress="pass"))
    assert r.returncode == 1, r
    assert "did not change" in r.stderr, r.stderr


def test_offline_downloads_nothing(tmp: Path) -> None:
    """--offline spawns no subprocess at all, and says where its number came from."""
    home = project(tmp, stress="open('ran', 'w')", fear="open('ran', 'w')")
    r = run(home, "--offline")
    assert not (home / "ran").exists(), "a script ran under --offline"
    assert r.returncode == 0, r
    assert "קריאה שמורה" in r.stdout, r.stdout
    j = json.loads(run(home, "--offline", "--json").stdout)
    assert j["live"] is False and j["fresh"] is True, j
    assert j["date"] == f"{pd.Timestamp.now():%Y-%m-%d}", j


def test_digest_mismatch(tmp: Path) -> None:
    """A score.csv from one run and a meta from another is refused."""
    home = project(tmp, stress="pass")
    frame(6, end=pd.Timestamp.now()).to_csv(home / "score.csv", index_label="date")
    r = run(home, "--offline")
    assert r.returncode == 1, r
    assert "different runs" in r.stderr, r.stderr


def main() -> int:
    test_reading()
    test_validate()
    test_lines()
    test_bands()
    with tempfile.TemporaryDirectory() as raw:
        test_fear(Path(raw))
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        test_refresh_failure(tmp)
        test_unchanged_score(tmp)
        test_offline_downloads_nothing(tmp)
        test_digest_mismatch(tmp)
    print("test_check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
