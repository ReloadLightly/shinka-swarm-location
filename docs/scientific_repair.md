# Scientific-core repair: scope and evidence

Original repair base: upstream `fc459b5cf56037005b69665f12a24b9e998e936e`.
This document records the repair design; the current run specification is
`README.md`. The later source-route decision is described in
`docs/source_fidelity.md`.

## What the book actually asks

Altshuler, *Applied Swarm Intelligence*, section 4.7.4, printed pp. 198–200,
compares OD-weighted, endpoint-inclusive group coverage, interrupted search,
and incumbent/admissible-upper-bound certificates. Section 4.8 gives 6,716
vertices and 15,823 directed links; the chapter uses 680 OD zones and a one-hour
search limit. The broader number/type/cost decisions in sections 4.3–4.5 are
separate from this fixed-cardinality location problem.

## Repairs implemented

`core.py`: explicitly versioned nonnegative links; exact integer-scaled distances;
topological counting through zero-time ties; no origin revisits; preserve centroid
barriers. For the current TNTP suite, a declared fewest-links secondary criterion
resolves zero-time cycles without an epsilon; it does not count all equal-time
simple paths through these cycles. Dead branches cannot
contribute to OD coverage and are removed from stored DAGs. Large DAGs use compact
count and predecessor mappings; arbitrary-size path counts remain exact.

`tntp_v2.py` and `prepare_search.py`: verified pinned full-size source files,
explicit exclusion and exact accounting of intrazonal non-network demand,
no connector deletion, no graph shrinking. The new catalog contains Winnipeg,
Chicago-Sketch and Chicago-Regional. Chicago variants are ONE source family.
Philadelphia and GoldCoast are the validation families; Barcelona and Birmingham
are the test families. Their pinned files import without scoring them. Independent
assessment remains planned, so large-network transfer is not yet established.
Historical held-out files and old import policies have not been repurposed.

`search.py`: per-origin score/gain queries expose computational allocation as a
real algorithmic choice. Contributions use full-demand normalization. Raw DAGs
remain available. Query counters do NOT account for arbitrary candidate code and
are not advertised as a deterministic computational budget.

`dag_bounds.py`: no route enumeration or finite split catalogue. Search programs
may choose their own branch/frontier/construction/restart policy. The optional
partition helper commits a split only after both children are bounded. The
parent independently replays submitted structural witnesses. Directed integer
rounding at every division, using the exact binary rational values of loaded
floating-point demands, produces valid outward bounds without huge rational
expressions. All closed/pruned leaves remain part of the certificate partition.

`anytime.py`: candidates and fixed controls can both submit independently
verified bounds in the new protocol. Legacy and new witness families are
supported. Existing historical evaluation defaults remain available.

`evaluate_search.py`: fixed controls computed once per versioned suite and
execution environment; candidate-only subsequent evaluation. At each checkpoint,
Q is coverage divided by the offline best feasible control value, and C is the
verified feasible lower bound divided by the strongest submitted admissible upper
bound. The catalog's declared evolutionary score is 100 times the equal-weight
mean of Q and C, averaged by source family. Q and C and final coverage are always
reported separately. This scalarization is a project design choice, NOT a book
formula. Feasible reference values are NOT optima; scores may exceed their
normalizers and are not clipped. Changing fitness weights requires a new cache.

`relabel.py`: each source/replicate receives a reproducible anonymous labeling,
shared by candidate and controls. Centroid identities are explicit sets, not
numeric thresholds after relabeling. Relabeling discourages literal node answers;
it does not prevent structural memorization, hence whole-family holdouts matter.

`search_initial.py` and `controls/`: executable hybrid seed and fixed DAG
DFBnB/utility-potential controls, with editable construction, exploration,
branching, frontier and effort-allocation code. The full EVOLVE block can change.
The new default native launcher selects this seed and evaluator; the historical
suite selects the historical path. Native islands, bandit and meta integration
are preserved. No custom evolutionary loop or paid model run is introduced.

## What this does NOT establish

A larger graph does not prove useful final-solution headroom. A loose LP upper
bound does not measure improvable coverage. The pasted MIP/latency numbers are
not automatically adopted as measurements of this repair. Wall-clock noise
remains; offline references remove a randomized fitness denominator, not all
runtime variation. Deployment and certificate gains must be distinguished.

The fixed controls are project implementations of the chapter's algorithm
families, not recovered source code from its authors. The Israeli source data are
not included. The default 60-second, 12-checkpoint profile is a new research
profile, not a reproduction of the chapter's one-hour experiment. Larger budgets
and checkpoint schedules are suite parameters, not program-search restrictions.

The Docker resource limit is configurable using SWARM_WORKER_MEMORY_MIB. Process
mode is not a security sandbox. This repair does not claim a Docker-host run,
paid evolution, a held-out winner, or externally verified scientific discovery.

## Verification files

See `results/scientific_repair/test_status.json` and the adjacent test logs for
executed tests and exit codes. These are machine-generated from this repair;
missing/failed/timed-out runs are not promoted to passes. Large-instance import
and profiling output is included only when it was actually generated.
