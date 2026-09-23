# M5: timing calibration on the campaign Docker backend

## Question and unchanged experiment

How much apparent anytime improvement can repeated identical code acquire from
execution timing, and how large should a **screening** advantage be before paying
for confirmation? This is measurement work on the existing §4.7.4-derived
placement problem, not a new swarm simulator, optimizer, objective or benchmark.

The primary checkpoints remain 0.02, 0.10, 0.50 and 2.00 seconds. The scalar remains
100 plus mean checkpoint improvement over freshly timed greedy, in percentage
points. All M1–M4 data, configurations, measured results, solver implementations,
source conventions and README result blocks are preserved. The new profile does
not overwrite any previous campaign. No model or research holdout calls occur.

## Research basis versus project choices

Docker documents `--cpus=1` as a CPU bandwidth quota, **not** a dedicated core or a
CPU-affinity guarantee [1]. We therefore measure the actual unchanged containment
backend rather than assume process timings are portable. Mytkowicz et al. explain
how apparently innocuous execution details can bias performance comparisons and
motivate setup randomization [2]. Kalibera and Jones emphasize repetitions at the
right experimental levels and accounting for uncertainty [3]. Cawley and Talbot
explain how a noisy selection criterion can itself be overfit [4].

Our exact repetition counts, six-role null schedule, 0.10 pp practical floor,
0.05 pp padding, empirical-envelope rule and five-repeat confirmation requirement
are **predeclared project choices**. They are not algorithms or constants stated
by these sources or by the book. They provide a useful finite screening guard,
not a new statistical theorem, 95% guarantee or correction for arbitrary numbers
of adaptively generated candidates.

## Frozen design

`configs/timing_m5.json` specifies 12 complete null blocks and five complete
strong-control blocks. Every block contains the same 24 development cases: the
original two complete published networks, their four monitor budgets, and solver
seeds 0–2. These are repetitions of a fixed finite suite, not new independent
networks. The 24 cases and four checkpoints do not inflate the block sample size.

A null case executes six roles separately:

| Role pair | Executed code identity | What the difference measures |
|---|---|---|
| candidate_a / candidate_b | Same unchanged `anytime_initial.py` file through the same loader | Same candidate, independently timed |
| greedy_a / greedy_b | Identical `greedy` dispatch and same fixed solver bytes | Reference timing variation |
| early_a / early_b | Identical `early_celf_swap` dispatch and solver bytes | Timing of the stronger early-answer control |

Let C_A,C_B,G_A,G_B be complete-suite checkpoint means in percentage points.
The refreshed-fitness contrast is `(C_A-G_A)-(C_B-G_B)`. Its greedy references
are separately executed, not shared and cancelled algebraically. We additionally
report C_A-G_A and C_B-G_B: these implement the same greedy selection rule but
**different loading/dispatch paths**, so they are not byte-identical nulls. We
retain their systematic offsets rather than center them away. Including these
discrepancies in the screening envelope is deliberately conservative.

Each strong-control case executes the unchanged seed plus all seven M4 controls:
greedy, greedy_swap, topk, early_celf_swap, iterated, dfbnb and potential. This is
960 timed trials; the null blocks add 1,728, for **2,688 planned study trials**.
All budgets belong to each solver independently. No representation, warm start,
proof serialization or algorithmic work is shared for free between trials.

Block order is shuffled before measurements. Within each phase, adjacent numbered
repeat pairs use the same seeded random order with **reversed case and role order**
on the second repeat. This counterbalances role positions. The fifth control
block has no reverse partner. The complete planned schedule is written and hashed
before any study solver executes. Its role count/order deliberately differs from
an ordinary five-role M4 screening evaluation; it is an explicit calibration
schedule using the **same** worker, clocks, resource limits and scoring code.

No outliers, failed cases or unfavorable repeats are discarded. A failed trial
invalidates the derived guard. Interruption preserves the partial journal/status;
it never silently launches a replacement measurement or overwrites evidence.

## Runtime and interpretation boundary

The unchanged `run_anytime` and `isolation.command` perform all timed work.
A separate diagnostic container made with the same launch helper records the
actual user, Python version, CPU bandwidth quota, memory and PID limits. The
study freezes the immutable image ID, host CPU model, kernel, parent affinity,
clock details, Docker version, memory/load observations and a hashed boot-session
identity. No credentials, entire environment dump or source book are recorded.

Execution is serial. Common DAG preprocessing and Docker startup remain outside
the inner clock, but are not hidden from total measurement costs. CPU pinning,
frequency policy, quotas, clocks, checkpoints and the worker protocol are **not**
changed to produce a nicer result. No causality claim about throttling follows
merely from observing the quota. Iterated-search variation at a fixed seed can
include deadline-dependent search progress; it is not a fresh random seed.

The accessible measured machine is a **GitHub Actions host using the campaign's
Docker backend**, not the user's WSL workstation. Matching the backend is not
matching every physical host. Any future campaign on another machine, image,
boot/runtime session or changed implementation needs its own calibration. The
optional screen checks that identity; it does not impose a new global prohibition
on native evolution. Load can drift even within one session. Twelve null blocks
cannot characterize all rare scheduling events, arbitrary candidate programs,
future host load or an entire adaptive search's false-positive probability.

## Screening and confirmation

For each of the six suite-level probes above, retain every block value. Let E be
the maximum absolute value across those probes and blocks. The empirical guard is

    T = round_up_to_0.01_pp(max(0.10_pp, E) + 0.05_pp).

It is not calculated from per-case maxima or from a pseudoreplicated sample of
checkpoints. All per-source/budget/checkpoint null distributions remain available
to show where noise occurs. Final coverage is separate from the checkpoint mean.

An optional fresh development screening measurement proposes confirmation only
when its paired checkpoint-mean advantages over **both** greedy and the early
hybrid strictly exceed T. This is not an oracle portfolio baseline and does not
modify `combined_score`, native selection or any historical configuration.
A winner below T is not proved useless; it simply lacks strong enough evidence
for this conservative automatic screen. Final-only improvements can be examined
in a separately declared scientific analysis rather than relabelled anytime wins.

For a promoted program, freeze the source before **five fresh complete development
assessments against all seven fixed controls**. Preserve all five, report paired
block means/ranges for every comparator and both metrics, and do not select the
best repeat or retune the program on the confirmation result. A defensible next
stage requires a consistently positive effect against the relevant stronger
comparators and an explanation of early versus final performance. This finite
heuristic is not a formal significance test or a requirement that every useful
method dominate every baseline on every individual case. Validation/test still
follow the ordinary frozen-shortlist protocol; this utility never opens them.

## Reproduction and evidence

Prepare development data only, build/pull an explicitly chosen image once, resolve
its immutable image ID, and use a new measurement directory:

```bash
python scripts/prepare_research.py --split development --download \
  --comparison-profile configs/comparisons_m4.json --output data/commissioning_m4
python scripts/calibrate_timing.py --suite data/commissioning_m4/suite.json \
  --docker-image "$IMAGE_ID" --output results/local_timing
python scripts/calibrate_timing.py --suite data/commissioning_m4/suite.json \
  --output results/local_timing --verify
```

On that same host/session, an optional explicit fresh screen is:

```bash
python scripts/calibrate_timing.py --screen-program path/to/candidate.py \
  --calibration results/local_timing --suite data/commissioning_m4/suite.json \
  --docker-image "$IMAGE_ID" --output results/local_screen
```

The study retains the full external-receipt incumbent traces and online-bound
journals, not just scalar scores. Replay checks every scheduled identity, replays
original scoring, cross-checks exact rational coverage, verifies transmitted
bounds, and regenerates the statistics and exact **mean step-function** curves.
No linear interpolation invents intermediate deployments. The compressed raw
journal is lossless; an interrupted run retains its uncompressed partial journal.

`results/timing-calibration/study/` and README §5.7 record the executed study when
available. Planned counts above are not a claim of completion. A separately
recorded seed-screen check, when executed, is not included in the 2,688 study
trials. No longer-budget assessment is performed in M5. One may be predeclared for
a later experiment, but it may not replace these primary results after inspection.

## References

1. Docker, *Resource constraints*: https://docs.docker.com/engine/containers/resource_constraints/
2. Mytkowicz, Diwan, Hauswirth and Sweeney (2009), *Producing Wrong Data Without Doing Anything Obviously Wrong!*, ASPLOS. https://doi.org/10.1145/1508244.1508275
3. Kalibera and Jones (2013), *Rigorous Benchmarking in Reasonable Time*, ISMM. https://doi.org/10.1145/2464157.2464160 ; author record https://kar.kent.ac.uk/33611/
4. Cawley and Talbot (2010), *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation*, JMLR 11:2079–2107. https://www.jmlr.org/papers/v11/cawley10a.html
