# Handover — branch `claude/project-artifact-destination-0qd00e`

Written 1 September 2026 for [PR #2](https://github.com/s5176070-rgb/sell-deshbord/pull/2),
covering `7c3e4dc..6773a71`.
Delete this file when the PR merges; it describes one piece of work, not the project.

## What changed

Seven commits, oldest first.

| | |
|---|---|
| `7673400` | Ten sessions of `^VIX3M` into `patches.csv`, and a README that finally mentions CBOE |
| `f49a820` | The walk-forward table on the daily page; `spells` and two intervals in `event_rate` |
| `5af858a` | The selftests in CI — the repo had no workflows at all |
| `d82b9e2` | `event_rate` stops scoring the twenty rows whose forward window is cut short |
| `ba57ada` | The headline README table flagged as predating both `event_rate` changes |
| `6afd90c` | This file |
| `6773a71` | The table restated from a run that had market data — see below |

## What turned up along the way

Five findings, roughly in order of how much they matter.

**`event_rate` was scoring twenty rows it should not have.** `rank_against_drawdown`
drops the final `EVENT_DAYS` rows at every January cut, and `since2000` drops them
before its own rates. `event_rate` never did. The last row was judged on one
session, the row before it on two, and only rows twenty back got the full window.

The interesting part is the direction, because the first draft of that fix got it
wrong. Copying the reasoning from `rank_against_drawdown` — where the tail reads
calmer, and correctly so for the correlation it guards — produced a comment that
measurement then contradicted:

| | tail scored | tail dropped |
|---|---|---|
| market already sliding when the data ends | 75.0% | 67.5% |
| market calm at the edge | 8.3% | 12.5% |

Both signs occur. So the tail is not a biased estimate of the same quantity that
could be corrected; it is an answer to a shorter-horizon question, and averaging
the two together is the defect. That is why the fix drops rather than adjusts.

**Day counts overstate the sample, and by a lot.** The forward window is twenty
sessions, so two adjacent days share nineteen twentieths of the path they are
judged on. 112 days above 85 are a handful of episodes, not 112 draws. `spells`
counts unbroken runs, and each rate now carries two intervals: `ci_days`, which
makes the table look precise and is wrong, and `ci_spells`, which is defensible
and much wider. On one synthetic series they came out 2.8 against 48.9.

The arithmetic already settles a claim the README makes in words. On day counts
alone, 85+ is 22.3% ±7.7 and 70–84 is 22.5% ±3.9 — the second sits entirely
inside the first, before the spell count widens either.

**The band was being read off the wrong scale.** Bands are cut on the raw
percentile (`MSS`); the dashboard publishes the calibrated 0–100 score. They are
different scales, and 36 on one is not 36 on the other. This was a live mistake
made during this work — an artifact was published marking today's band from the
score — caught by reading `band_of`'s callers and corrected. `simple()` now
carries a docstring saying so, because the mistake is easy and silent.

**`--serious` was never defined in the light palette.** `band_colour` has always
emitted `var(--serious)` for the 70–84 band; `BROADSHEET_CSS` defined only
`--good`, `--warn` and `--crit`. Latent rather than live — nothing on the light
page called it until this branch did — and it would have failed by silently
losing the colour, not by erroring.

**The README described a world the code had left.** Known limits told you to top
`patches.csv` up by hand and never mentioned that `cvs.py` fetches CBOE's own
daily file first. That stale paragraph is what sent this session hand-collecting
ten sessions of `^VIX3M` that the code may well have fetched on its own.

## Where this stopped, and how it was unblocked

**The model could not be scored where the branch was written.** `python stress.py
--bench` returned `CONNECT tunnel failed, response 403` from the egress proxy for
all twenty tickers, and `stress.build` correctly refused with `no price data came
back` — an organization network policy, not a code problem, with no route around
it from there. Everything that does not need market data was run and passed: five
selftests on 3.11 and 3.12, `compileall` clean, and the new code exercised against
synthetic series built so the counts were known in advance.

**`6773a71` cleared it**, run on a machine with market access, and the table was
copied from that run rather than edited by hand. Its arithmetic was checked
afterwards against its own rate and count columns: every `±days` and `±spells`
figure reproduces to within 0.02 points, so the table is internally consistent
and safe to quote.

| Score | Days | Spells | 5% fall in 20 sessions | vs base | ±days | ±spells |
|---|---|---|---|---|---|---|
| all days | 3,657 | — | 13.29% | 1.00× | 1.10 | 66.53 |
| 0–44 | 1,574 | 203 | 8.26% | 0.62× | 1.36 | 3.79 |
| 45–69 | 1,585 | 294 | 15.21% | 1.14× | 1.77 | 4.10 |
| 70–84 | 419 | 108 | 21.96% | 1.65× | 3.96 | 7.81 |
| 85+ | 79 | 17 | 29.11% | 2.19× | 10.02 | 21.60 |

**The answer is worse for the model than the old figures suggested, and it is the
spell count that says so.** On days alone the top band looks sharper than ever —
29.11%, a 2.19× lift, up from 1.67×. On its seventeen spells the interval is
7.5–50.7%. That contains 70–84's 14.2–29.8% whole *and* reaches under the 13.29%
base, so the sample does not establish that 85+ beats an average day, let alone
the band beneath it. A lift that travels 1.67× → 2.19× on one recount is the same
finding from the other side: it was never resting on a sample.

Day counts went **up**, 3,646 → 3,657, not down by twenty. Roughly thirty-one
sessions were added between the two measurements, which more than covers the
twenty rows `event_rate` now drops.

## Next

1. ~~Run `python stress.py --bench`~~ — **done**, on a machine with market
   access. The answer to the question this branch could not settle: the top
   band's edge does *not* survive its own interval. 85+ is 29.11% on 79 days
   and seventeen spells, and ±21.60 on the spell count puts it at 7.5–50.7%.
   That contains 70–84's 14.2–29.8% whole, and its lower end sits under the
   13.29% base — so seventeen spells do not establish that the top band beats
   average, never mind the band below it. The lift itself moved from 1.67× to
   2.19×, which is the same point from the other side: a number that jumps that
   far on a recount was never resting on a sample.
2. ~~Replace the README table from that output.~~ **done** — copied, and the two
   paragraphs that quoted the old figures (`2.4×` at the top, and the
   "indistinguishable" note under "What the score does not say") restated from
   the same run. `stress.py:318`'s comment on why `FLAG` is 85 carried the same
   stale pair and was restated too.
3. **Merge the PR.** Nothing outstanding — selftests and `compileall` pass.

Two things deliberately left alone, in case they look like oversights:

- **`cvs.py:105` emits `UserWarning: Boolean Series key will be reindexed`.**
  Traced to the degenerate path where no column returned any data at all — which
  is exactly what a fully blocked download produces. It should not fire on a real
  run. Untouched because it is outside this branch and unverifiable without data.
- **`±spells` is meaningless on the `all days` row, and the table shows why.**
  Every day is in that row, so it is one unbroken spell, and an interval on a
  sample of one comes out ±66.53. The pushed table renders its `Spells` cell as
  `—`, which is right, but keeps the interval beside it. `event_rate` still
  returns both. Either suppress the pair for that row or leave it — it is
  obvious enough on the page not to mislead, and it is not worth a commit on
  its own.
- **Nothing was added to the score.** Every change here measures the existing
  score more honestly or documents it. `MIN_CORR`, the band edges, the factor
  list and `FLAG` are all untouched, so the reading itself does not move — only
  the confidence attached to it, and the twenty rows that should never have been
  in the table.
