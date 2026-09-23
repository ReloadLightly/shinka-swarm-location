# M6: early-incumbent controls for existing anytime search

## Question and source boundary

How much of a useful early answer can be obtained by reporting a cheap complete
singleton-ranked deployment before running the existing advanced fixed solver?
Does this improve the original quality-time objective, and what final-quality or
search-time cost does it incur? This is an engineering ablation, not a claim of a
new optimizer, an evolved program, or decentralized robot control.

Applied Swarm Intelligence, Chapter 4, Section 4.7.4, printed pp. 198–200, defines
the group monitoring problem and compares greedy, DFBnB and Potential Search.
Printed p. 199 explicitly describes interrupting either search and returning its
best solution; p. 200 describes incumbent/upper-bound certificates. That is the
chapter basis. It does not prescribe this singleton-prefix comparison. These
three variants, their equal deadlines, substitute development networks and the
block schedule below are explicit project choices. The prior formula-emendation,
fixed-route assumptions and original-Israeli-data limitations remain unchanged.

## Exactly what changes

`early_iterated`, `early_dfbnb`, and `early_potential` are new registered names in
`strong_baselines.solve`. They execute the very same prefix as the existing
`early_celf_swap`: calculate empty-set DAG marginal gains, sort by descending
singleton gain with node-ID tie breaking, select k nodes, and report that complete
deployment before `RouteSearch` construction. All method-specific imports remain
in the existing after-GO worker path; none is moved into free preprocessing.

There is one start time and one deadline. The prefix consumes that same budget.
After the exact representation exists, the early deployment is scored by that
representation and retained as the initial best incumbent. The existing CELF
construction and strict 1-swap descent then run. The iterated version retains its
existing perturbations, working-state initialization, RNG, radius/reset policy,
and descent. The two bound-guided variants call the unchanged `PartitionSearch`
with the corresponding original `dfbnb` or `potential` mode and best incumbent.
No routes, optima, bounds or deployments are read from benchmark result files.

This is **not merely output buffering**: retaining a better incumbent can alter
bound pruning and the iterated method's improvement-triggered radius reset.
Consequently, it is not assumed to produce the same later search trajectory or
final result as its parent. Conversely, computing the prefix can reduce time
available for later search. The study must report both costs and benefits.

The original names retain their old paths. A frozen copy of the actual M5 source
in `tests/fixtures/strong_baselines_m5.py` checks identical legacy deployments,
bound operations and non-timing diagnostics at fixed work on synthetic instances.
The small method-dispatch addition can itself change interpreter/import timing;
therefore both variants and parents are freshly measured under the same current
implementation. Historical source hashes and measurements are not relabelled.

Best-incumbent retention is implemented inside the exact search path and again by
the independent external best-so-far scorer. On a route-limit fallback the latter
also preserves any earlier better report. Tests cover a deliberately worse later
warm start, interruption during route construction, no free initialization at a
zero time budget, zero monitors, fallback, exact small-instance optima and online
proof verification for the new bounded names.

## Protocol frozen before measurement

`configs/early_controls_m6.json` declares six complete repetitions of the existing
24 development cases (Sioux Falls and Anaheim, four k values and three algorithm
seeds each). The eight method roles are the original/new three pairs, singleton
ranking and the existing early CELF/swap. A ninth role executes byte-identical
`early_celf_swap` again with the same inputs and algorithm seed, to observe timing
variation on this particular host session.

The 1,296 solver invocations run serially in fresh Docker workers using the same
immutable executor as M5. Each gets the unchanged 20 ms, 100 ms, 500 ms and 2 s
checkpoints and the same one-CPU bandwidth quota, 768 MiB memory and isolation
settings. CPU bandwidth quota is not a dedicated physical core. The parent
continues to timestamp complete received messages; internal solver timestamps
never substitute for receipt times.

Each even-indexed block has deterministically shuffled cases and method roles;
the following block reverses both. The entire schedule, source/configuration/data
hashes, runtime identity and resource probe are saved before the first solver.
No measurement is stopped because a preferred method wins. The output directory
must be new, every raw trial is journaled, and interrupted/failed outcomes remain
explicitly incomplete. No silent retry or successful-case-only average is allowed.

## Analysis and interpretation

The primary contrast is each new method minus its named original in the unchanged
mean checkpoint objective. All individual checkpoint and final differences are
reported separately, overall and by source and k. Whole-suite block means are the
reporting unit for SD and range; algorithm seeds and checkpoints are not treated
as independent network samples. All six values are retained, including losses.
The exact mean incumbent step functions have no interpolation between solutions.
The report also measures receipt of a complete k-node deployment, not merely an
empty or partial message, at each deadline.

The duplicate control is descriptive. It does not calibrate every algorithm's
noise distribution, establish significance, or produce a universal promotion
threshold. In particular, **the M5 1.97 pp guard is not portable to this new host
session or implementation**. Small differences must not be declared discoveries.
M5 calibration can be repeated on the future execution host; its source identity
records the declared fixed-method extension, rather than falsely calling that
file unchanged. Its original saved study is still replayed against its original
source commit.

Independent replay checks every submitted deployment against the existing DAG
scorer and the exact rational scorer, and verifies every online bound snapshot.
Summary arithmetic and complete case/order identity are reconstructed from the
losslessly compressed journal. Failure prevents a positive comparative report.

## Integration without rewriting old campaigns

`configs/comparisons_m6.json` keeps the M4 four-control development screen and
adds all three variants to both validation and test: ten controls in total. This
choice is made before measurement, not selected from the eventual winners. It is
activated only by `configs/m6_launch_request.json` (or an explicitly prepared M6
suite). Existing M3/M4 configs, fitness, native island/bandit/meta settings and
holdout selection rules remain unchanged. With 40 assessment cases, the ten
controls plus candidate require 440 solver invocations, each with its own budget.
This is a planned assessment cost, not performed holdout evaluation. Development
feedback names all planned assessment controls through the existing M4 machinery.

The M5 results, previous README result blocks and source references stay intact.
`check_m4_continuity.py` requires an explicit, narrowly allowed source-change flag
for `strong_baselines.py`, reports both old and current hashes and never excludes
results/data from protection. Historical verification workflows use their pinned
original source checkouts, not revised manifests.

## Commands

Prepare only development data and run on the actual Docker campaign host:

```bash
python scripts/prepare_research.py --split development --download \
  --comparison-profile configs/comparisons_m4.json --output data/commissioning_m4
python scripts/early_control_study.py --suite data/commissioning_m4/suite.json \
  --docker-image "$IMAGE_ID" --output results/local_early_controls
python scripts/early_control_study.py --suite data/commissioning_m4/suite.json \
  --output results/local_early_controls --verify
```

Use the immutable image ID resolved from the workflow's explicit registry digest.
Replay requires the measured source revision but does not require Docker or rerun
any solver. The journal and manifests support independent analysis. No paid LLM
run, evolutionary advantage or research validation/test performance is implied.

## References

1. Altshuler, Y., Pentland, A., and Bruckstein, A. M. Chapter 4, “Defending
   Large-Scale Critical Infrastructures Using a Swarm of Drones,” in Y. Altshuler
   (ed.), *Applied Swarm Intelligence*, CRC Press, first edition 2025, §4.7.4,
   printed pp. 198–200. The user's supplied edition is the source of the section
   mapping; no copyrighted source pages are included in this repository.
2. Stern, R., Puzis, R., and Felner, A. (2011). “Potential Search: A Bounded-Cost
   Search Algorithm.” *ICAPS* 21(1), 234–241. DOI: 10.1609/icaps.v21i1.13455.
   [Publisher abstract](https://ojs.aaai.org/index.php/ICAPS/article/view/13455).
   The bounded-cost/anytime family motivates the existing utility-form adaptation;
   M6 does not redefine its ordering or claim recovered author code.
3. Docker, [Resource constraints](https://docs.docker.com/engine/containers/resource_constraints/),
   CPU section, consulted 2026-09-23. `--cpus` sets bandwidth quota; `--cpuset-cpus`
   is a separate affinity restriction. M6 changes neither.
