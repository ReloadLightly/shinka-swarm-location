# Strong fixed anytime baselines: methods, source mapping and executed study

## Why this is the next scientific step

At base commit `73e702843bd3d834121f4be58f6853e809d6db15`, the repository already
had independently verified optimum bounds and a complete six-monitor Sioux Falls
exchange-landscape diagnosis. These were offline references, not competing timed
algorithms. The actual anytime controls remained random placement, singleton
ranking, marginal greedy, and greedy followed by strict single-node exchanges.
The missing comparison was therefore a **strong, executable fixed solver set**,
not another objective, simulator, certificate formula, or evolutionary framework.

Chapter 4, Section 4.7.4, printed pp. 198–200 [1], explicitly compares greedy,
depth-first branch and bound (DFBnB) and Potential Search. It explains both their
interruptibility and their incumbent/upper-bound certificates. Its limit is one
hour on the Israeli network. Our two-second development comparison is a declared
adaptation on substitute data, not a numerical reproduction of that experiment.
The chapter's [103] is Stern, Puzis and Felner (2011) [2]. We checked the original
paper, including its KPP-COM group-betweenness maximization case and anytime
extension; Potential Search here is not an algorithm inferred from its name.

## Fixed problem and unchanged research boundary

The objective is the existing endpoint-inclusive, OD-weighted fraction of original
shortest routes encountering at least one selected node. Routes remain directed,
positive-cost, equally weighted within each tied-shortest-path OD pair, and subject
to the original centroid-through restrictions. Monitoring does not reroute traffic.
The budget is at most k distinct nodes. No drone flight, threat dynamics, congestion
assignment, or fleet-cost model is added. The previous equation emendation and
source/data limitations remain documented in `source_fidelity.md`.

The original DAG scorer and bulk marginal-gain backend are unchanged. So are the
old fixed-solver implementations, mutable seeds, native campaign configuration and
historical result files. The parent worker, protocol driver and optional comparator
allowlist receive explicit extensions so the new methods can run under the same
clock. The default evolutionary score and default comparator set do not change.
New controls can be requested through a manifest's `extra_baselines`; this does not
silently add them to an already frozen campaign.

## Solver set and what each comparison isolates

| Method identifier | Implemented method | Source relationship |
|---|---|---|
| `topk` | Existing singleton-demand ranking | Existing individual-centrality control |
| `greedy` | Existing bulk-DAG marginal greedy | Chapter's selection rule |
| `greedy_swap` | Existing DAG greedy and best strict 1-swap | Existing additional control |
| `route_greedy` | Full marginal greedy on exactly enumerated, guarded routes | Same selection rule, different representation |
| `celf` | Unit-cost lazy greedy using stale marginal upper bounds | Cardinality specialization of CELF [3] |
| `route_swap` | CELF followed by exact best strict 1-swap | Representation/improvement control |
| `early_celf_swap` | Report complete DAG-topk first, then separately run CELF + 1-swap; retain the best | Project fixed anytime control |
| `iterated` | Seeded increasing-radius perturbation/local descent and periodic whole-set restart; retain best | Project variable-neighborhood-inspired control [4] |
| `dfbnb` | CELF + 1-swap warm start, then include/exclude depth-first branch and bound | Chapter-aligned family; project implementation |
| `potential` | Same warm start and partition tree; utility-form anytime Potential Search ordering | Explicit maximization adaptation of [2], not recovered author code |

Random placement remains available and its historical evidence is preserved. The
new comparison concentrates on these ten stronger/relevant methods. It does not
claim that every possible optimizer has been included. Sampling-based stochastic
greedy and approximate group-betweenness algorithms remain future scalability
comparisons; none is silently used by the scorer or the new route backend.

### Exact route representation and guard behavior

`RouteSearch` consumes the already prepared original shortest-path DAGs. It counts
routes before enumerating them, preserves every equally short route, aggregates
identical vertex sets, and constructs an inverted node-to-route bitset index.
Demand is converted with `Fraction(q)`, representing the **loaded binary float**
exactly, consistently with the existing certificate layer. This does not silently
reinterpret a source decimal. Normalized route masses are scaled to integers;
coverage, marginal gains and comparisons within the new route controls are exact.

Defaults cap enumeration at 20,000 raw routes, traversal at 1,000,000 visits, and
integer scaling at 4,096 bits. A bounded 8,192-entry route-weight cache is local to
each solver trial. These are fixed implementation choices, not fitted per dataset.
When a guard rejects the representation, the method records the reason and falls
back to the existing DAG greedy+swap using **only its remaining time**. It never
samples paths, changes edge costs or excludes locations. If the deadline expires
during preparation, the last feasible incumbent remains available; it is not a
completed exact search. No arbitrary-size scaling claim follows from success on
the two current development networks.

All representation construction, cache population and warm starts occur **after
GO** inside the timed solver. These helpers are copied into the candidate worker
as well; future candidates are not denied a primitive used by fixed controls.
Candidate use of those helpers also incurs its own timed preparation.

### CELF without a misleading implementation comparison

For this unit-cost cardinality problem, stale marginal values remain upper bounds
because coverage is submodular. The heap selects the largest stored marginal,
recomputes it when stale, and accepts it only when it is current and still ranks
first. Exact ties select the smaller canonical node index. Tests compare the
entire selection sequence with full route greedy, not only final coverage.

This implements the cardinality specialization of the lazy mechanism in [3], not
the paper's full unequal-cost selection procedure. We compare it both to full
route greedy and the existing bulk-DAG greedy. That distinction matters: the DAG
backend obtains all gains in one pass, whereas a naively implemented lazy method
could repeatedly pay for whole-graph singleton calculations. A difference between
DAG and route timings must not be credited solely to the lazy heap.

## DFBnB and Potential Search: valid bounds during interrupted search

### Partition state, branch variable and admissible bound

A tree state specifies selected nodes S, undecided nodes R, and all previously
excluded nodes implicitly. Let V be covered integer mass and r=k-|S|. Completion
of this subtree is bounded by

    U(S,R) = min(inherited upper bound,
                 V + mass of uncovered routes touchable by R,
                 V + sum of the r largest uncovered marginal masses in R).

Every feasible descendant is represented by one include/exclude branch. Splitting
chooses the undecided node with largest current marginal gain, breaking ties by
canonical index. This branching rule is a project choice; the original KPP-COM
presentation describes adding vertices to partial groups. Both changes in search
representation and the endpoint-inclusive chapter convention are explicit rather
than presented as recovered source code.

If no slot or undecided node remains, the subtree is terminal. If all undecided
nodes fit, their union gives its exact best completion. Otherwise the bound follows
from union coverage and diminishing returns. The **r** in this subtree-completion
bound is appropriate because completions retain S. It must not be confused with
the top-**k** bound for the unrestricted optimum in the older certificate layer.

DFBnB uses a stack and considers the include child first. Both children and their
bounds are computed before replacing their parent in the partition. A deadline
interrupting an expansion therefore leaves the parent represented. Closed/pruned
leaves remain in the bound ledger, together with OPEN leaves. The global upper
bound is the maximum leaf bound (and feasible incumbent); no omitted active
subtree can manufacture an optimality certificate.

The same CELF + strict 1-swap warm start is used by both bound-guided methods and
is fully timed. `route_swap` isolates what that warm start can do without a tree.
Search limits of 50,000 committed splits and 100,000 open nodes stop with a valid
remaining bound, not an unconditional claim of convergence on arbitrarily large
instances. Exhausting the finite tree establishes optimality; otherwise exact
incumbent/bound equality can establish it earlier. A status string alone cannot.

### Utility-form anytime Potential Search

The original paper [2] formulates bounded-cost search, derives orderings from
heuristic-error models, evaluates a group-betweenness maximization application,
and extends the method to anytime search by updating the target and rekeying OPEN
when the incumbent changes. Its relative-error cost ordering is not copied with
unchanged signs into a maximization problem.

Here let V be partial covered mass, H=U-V its admissible additional-utility
estimate, and T=L_best+1 the next strictly improving integer target. If, as a
**heuristic ordering model**, the unknown additional utility is H* = H X with a
common relative-error distribution, then

    Pr(V + H* >= T) = Pr(X >= (T - V)/H).

For V<T and H>0, maximizing this tail probability orders states by decreasing

    potential = H / (T - V).

The implementation compares this ratio as an exact rational. Already-satisfying
states are handled separately; states with U<T cannot improve the incumbent.
Every incumbent improvement updates T and rebuilds the entire OPEN heap. Reusing
old keys after changing the target would implement a different ordering.

**We do not establish the common-error-distribution assumption on these networks
or claim that the ratio is a calibrated probability.** Its role is search order;
the completeness/quality guarantees come from the admissible bounds and complete
partition, not a learned probability model. The paper's fitted KPP-COM error-model
coefficients are not transplanted into our traffic data. This is a documented
utility-form APTS adaptation, not a claim to reproduce every implementation detail
or experimental result of Stern et al. or the book's authors.

### Timed bound messages and independent proof replay

DFBnB and Potential Search emit an initial universal bound and incremental
partition snapshots. A snapshot contains new split operations, the feasible
incumbent and a rational global upper bound. Root, improving-incumbent, periodic
128-split, and final snapshots limit reporting overhead. Bound calculation,
priority updates, journal construction, serialization and transport consume solver
time. Complete messages receive timestamps from the existing parent clock.

The new parent protocol accepts bound messages **only from explicitly named fixed
bound-guided solvers**, not from arbitrary candidate programs. Candidate-supplied
scores, times or unsupported bound messages remain invalid. Every deployed node
list is still independently scored using the unchanged production DAG scorer.

After capture ends, `baseline_proofs.py` reconstructs the partition using the
pre-existing exact certificate representation and its own bound arithmetic. It
replays every include/exclude operation, retains all leaves, verifies the bound,
and checks feasible coverage. Reordered, missing, duplicate or malformed operations
cannot be accepted as the claimed proof. Termination metadata is not trusted.
Verification time is recorded separately and is not hidden inside a solver-speed
claim. Invalid bound evidence invalidates the trial rather than being discarded.

This differs from earlier posthoc certificates: the **bound was actually computed
and transmitted during search**; only checking its proof happens afterward. If a
hard deadline truncates a message, the last complete earlier bound is still valid
(possibly looser). The updated feasible incumbent can use that older valid bound.
There is no claim that an untransmitted final bound was available at a checkpoint.

## Fixed exploratory escape control

`iterated` first constructs the same CELF + single-exchange local optimum, then
perturbs a working solution by replacing an increasing number of monitors. It
locally descends after each perturbation and periodically restarts from a uniformly
sampled full group. Improvement of the global incumbent resets the perturbation
radius; otherwise the radius increases. A seeded RNG makes the proposal stream
reproducible before time truncation.

Unlike a strictly improving VNS acceptance policy, this project control can retain
a worse **working** solution and continue from it. It is therefore described as
variable-neighborhood-inspired, not an exact implementation of the canonical VNS
algorithm [4]. Its best-so-far report never deteriorates. This supplies a simple
fixed comparison against claims that evolution discovered the need for larger
moves or temporary losses. No known optimal node sets, benchmark answers, or
numerical escape-barrier constants occur in the solver.

## Development-only experiment and measurement boundaries

`configs/strong_baselines.json` fixes ten methods and three repeats of every M2
development case. Sioux Falls uses k=1,3,4,6; Anaheim uses k=3,6,12,24; seeds are
0,1,2. This produces **72 paired cases and 720 solver trials**, with the existing
0.02, 0.10, 0.50 and 2.00 second checkpoints. Case order and method order within
cases are reproducibly shuffled. No concurrent solver trial is launched.

The manifest is written before the comparative run and records the configuration,
source hashes, suite/data hashes, runtime and scope. Development preflight tests
were performed while implementing the methods; this is not a blind confirmatory
or preregistered benchmark. No per-network parameter sweep selected the reported
methods or thresholds after the comparative results. Failed trials remain in raw
records and summaries. An interrupted study remains incomplete, not silently
replaced by a favorable rerun.

A complete 720-trial precursor was executed on the local Linux process backend,
and an independent canonical 720-trial run uses the same frozen solver code on a
GitHub-hosted Linux process backend. The original local summaries, source hashes
and replay verification are preserved separately, with complete local raw data
in the associated delivery archive. The canonical run's complete raw data are
committed in the repository. Neither is selected according to favorable timings,
and the two host measurements are not pooled. The canonical study does not measure
Docker overhead or establish identical timing on WSL, another CPU, or the previous
GitHub/Docker runs. Existing common interpreter/DAG preparation remains outside
the warm search budget. Candidate/solver imports, route compilation, warm starts,
search and reporting occur inside it. Parent proof replay and score verification
occur afterward and have separately recorded costs. Thus this is not an end-to-end
latency comparison.

Repeated deterministic methods vary chiefly through timing. The three repeats
and three solver seeds are not nine independent road networks. Tables report
descriptive paired means and per-checkpoint values, not population confidence
intervals or statistically proven superiority. Very early checkpoints remain
sensitive to scheduling, imports and reporting overhead. The existing same-code
A/A warning remains relevant when interpreting small differences.

The study verifier replays saved deployments and every transmitted bound witness,
checks source identities and case completeness, recomputes all summaries, and
compares displayed deployments with exact-rational DAG scoring. It does **not**
rerun timed solvers to reproduce favorable timings. The 18 added tests also compare
route coverage and CELF sequences with independent references, check exact optimum
and interrupted bounds on small exhaustive cases, test rekeying, resource/deadline
semantics, corrupted journals, candidate-protocol rejection, fallback behavior,
seeded escape and the opt-in comparator integration.

## Interpretation and remaining scope

The executed findings and any negative comparisons belong in README Section 5.5
and the saved results, not in assumptions about which named algorithm must win.
Improving on plain greedy is no longer enough to establish an evolutionary
contribution. Improvements must be compared with appropriate strong fixed controls
and with representation/preprocessing differences accounted for.

No LLM calls, evolved descendants, original-Israeli-data reconstruction, validation
selection or test performance evaluation occurs in this study. The existing
subscription-authenticated native campaign still needs its authorized runner.
Sampling-based controls and broader independent benchmarks remain optional later
scientific extensions, not silently implemented components of this milestone.

## References

[1] Altshuler, Y., Pentland, A., & Bruckstein, A. (2025). Defending Large-Scale
Critical Infrastructures Using a Swarm of Drones. In *Applied Swarm Intelligence*,
Chapter 4, especially Section 4.7.4, pp. 198–200 and reference [103].
https://doi.org/10.1201/9780429276378

[2] Stern, R., Puzis, R., & Felner, A. (2011). Potential Search: A Bounded-Cost
Search Algorithm. *ICAPS*, 21(1), 234–241.
https://doi.org/10.1609/icaps.v21i1.13455
Publisher: https://ojs.aaai.org/index.php/ICAPS/article/view/13455
Original full text uploaded by coauthor Rami Puzis:
https://www.researchgate.net/publication/220936354_Potential_Search_A_Bounded-Cost_Search_Algorithm
See "Linear Relative h-Model", "Key Player Problem in Communication", and
"Potential Search as an Anytime Algorithm". No author source code was recovered.

[3] Leskovec, J., Krause, A., Guestrin, C., Faloutsos, C., VanBriesen, J., & Glance,
N. (2007). Cost-effective Outbreak Detection in Networks. *KDD*, 420–429.
https://snap.stanford.edu/class/cs224w-readings/leskovec07outbreak.pdf
See Section 4 and Algorithm 1; our unit-cost specialization is stated above.

[4] Mladenović, N., & Hansen, P. (1997). Variable Neighborhood Search. *Computers &
Operations Research*, 24(11), 1097–1100. https://doi.org/10.1016/S0305-0548(97)00031-2
Author technical report: https://www.gerad.ca/en/papers/G-96-49

### Historical identity checks are not weakened

The previous exchange-study verifier deliberately pins even files that were not
used by its mathematical calculation, including the old protocol driver. This
milestone legitimately extends three of those interface files. Its strict verifier
is left unchanged: CI replays the original study in a separate checkout of
`73e702843bd3d834121f4be58f6853e809d6db15`, and additionally recomputes the entire
scientific record with the current mathematical modules. Both must agree. This
preserves the original identity requirement instead of rewriting historical hashes
or deleting a failing check. Historical optimum/certificate artifacts are likewise
independently rechecked with their unchanged source implementations.
