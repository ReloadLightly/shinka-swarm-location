# M2: exact-route anytime deployment search

## Research basis and decisions

The source task remains Chapter 4, especially Sections 4.7.1–4.7.4 of
*Applied Swarm Intelligence* (copyright page: 2025). Section 4.7.4 uses the net
OD-weighted traffic encountering at least one monitor and discusses interruptible
DFBnB and Potential Search. The chapter uses a one-hour limit. **Our four shorter
checkpoints are a new commissioning protocol, not a reconstruction of that limit.**
The explicit correction of the printed route fraction remains documented in
[source_fidelity.md](source_fidelity.md); no new economic or drone-dynamics model
has been substituted.

External research informed three engineering decisions. ShinkaEvolve's paper [A]
and pinned implementation [B] support native program evolution with islands,
inspirations, novelty, and model selection, rather than a custom imitation loop.
Optimization-benchmarking guidance [C] motivates explicit instances, comparison
budgets, raw measurements, and reproducible protocols. The primal-integral
literature [D] motivates assessing the solution trajectory rather than only the
final value. Our statistic is a **discrete checkpoint mean**, not Berthold's
continuous primal integral, and we do not claim to implement that paper's metric.

## Fixed objective and faster marginal gains

Let H_s be the **original** shortest-path DAG from origin s. Define n_s(v) as its
integer number of shortest prefixes to v, and a_s(v;S) as the number avoiding the
monitor set S. Routing distances are rational and path counts are integers;
demand dependencies, aggregation, and reported coverage use floating point.

For an unselected v, its unnormalized marginal covered demand is

    sum_s a_s(v;S) * sum_t D_st * h_s(v,t;S) / n_s(t),

where h counts suffixes avoiding S. Every path through v splits uniquely into a
prefix and suffix because positive edge costs make the shortest-path structure
acyclic. Thus no covered path is counted twice in the marginal of adding v.

Rather than enumerate suffixes, initialize b_s(t) with D_st and propagate backward:

    b_s(u) += b_s(v) * n_s(u) / n_s(v),  for each DAG edge u -> v,

skipping selected vertices. The marginal contribution at v is

    (a_s(v;S) / n_s(v)) * b_s(v).

Summing over origins and dividing by total OD demand yields all node gains.
This costs O(sum_s (|V_s|+|E_s|)) **arithmetic operations** per gain pass. It is not a
bit-complexity claim: large integer counts still have nonconstant arithmetic cost.
Using ratios of prefix counts avoids converting exponentially large counts
individually into floating point. The test suite includes a compact graph with
2^1100 equally short routes. No route sampling, path deletion/rerouting, or
restriction of candidate locations is introduced.

`SearchProblem` inherits M1's score and routing semantics. Parent-side verification
uses M1's independent avoiding-path score, not the new reverse-dependency gain
function. Small-graph tests also compare gains against independently enumerated
all-simple-path minima. This is a project derivation/implementation; neither
algorithmic novelty nor reproduction of Puzis et al.'s code is claimed.

## Candidate contract and timing boundary

    solve(problem, k, random_seed, report, time_budget) -> list[int] | None

A candidate may redesign its construction, exchanges, restarts, adaptive search
control, and allocation of computation. Only code within the EVOLVE block changes.
`problem` exposes the graph instance, DAGs, score, and all-node marginal gains.
`report(S)` submits a feasible incumbent, including partial groups with |S| <= k.
The final returned group is also submitted, but gets no retrospective timestamp.

For every trial a parent process copies the fixed worker/package and candidate
into a fresh temporary directory. The worker builds the same fixed DAG interface,
signals READY, and waits. The parent starts a monotonic clock and sends GO. Only
then does the worker import the candidate and execute its search. **Candidate
imports, candidate-specific preprocessing, search, and report transmission count.**
Common package/interpreter setup and common DAG construction are excluded from
the search budget and reported separately. The primary comparison is therefore a
warm prepared-problem search comparison, not total deployment latency.

The parent stamps complete received messages; supplied scores and timestamps are
rejected. Messages arriving after the last checkpoint are not credited. The entire
process group is terminated at the deadline and the best valid prior incumbent is
retained. A normal deadline is not a correctness failure. Invalid selections,
malformed messages, excess output, or an abnormal worker exit are failures.
Scoring occurs after capture to avoid delaying subsequent receipts with evaluator
computation. Ordinary stdout is not a submission channel. Candidate stderr is
currently discarded to bound logs; a crash is reported by exit status.

The same package, preprocessing interface, clock, and reporting protocol are used
for random, individual-centrality, greedy, fixed greedy+swap, and candidates.
Execution order is deterministically shuffled within each paired case. No other
candidate evaluation is run concurrently by the native preset. OS scheduling and
message transport can still add timing noise, especially at the earliest checkpoint.
No confidence interval or hardware-independent speed claim follows from this run.

## Commissioning suite and scoring

The immutable upstream revision is
`977ee75c6906337c0c7d229a1336107c7cdb533e` of Transportation Networks for Research.
The downloader verifies each original TNTP file's Git blob hash before parsing.
Prepared JSON inputs are individually SHA-256 verified by the suite loader.

| Source network | Role | Location budgets |
|---|---|---|
| Sioux Falls | Development/debugging, not realistic | 1, 3, 4, 6 |
| Anaheim (1992) | Development/historical benchmark | 3, 6, 12, 24 |

Seeds are 0, 1, 2 and checkpoints are 0.02, 0.10, 0.50, 2.00 seconds. This gives
24 paired network-budget-seed cases. The seed controls randomness where used;
repeated deterministic solvers primarily reveal timing variation, not new networks.
Checkpoints were fixed before the comparative run, not optimized to favor a
candidate. All nodes remain eligible, including centroid endpoints. Centroids
that TNTP forbids as through-nodes cannot become intermediate routing vertices.
Positive intrazonal demands, parallel directed links, nonpositive travel costs,
demand-total mismatches, and unparsed records fail explicitly rather than being
silently discarded or transformed.

Let C_i(A,t_j) be best valid coverage received by checkpoint t_j. The scientific
score is the equal-case/equal-checkpoint mean difference from same-budget greedy:

    Delta(A) = 100/(N*J) * sum_i sum_j [C_i(A,t_j) - C_i(greedy,t_j)].

Native `combined_score` is `100 + Delta(A)`. This affine shift keeps valid scores
nonnegative; it is not an additional objective. The unshifted percentage-point
value and the corresponding difference against **fixed greedy+swap** are reported.
A run with any candidate or reference failure gets `correct=false` and score zero;
failed cases are not dropped from averages. No claimed upper-bound certificate is
fabricated. Better coverage than greedy alone is not sufficient evidence of an
evolutionary contribution.

The manifest can express development, validation, and test partitions. Repeated
source_graph IDs and identical file hashes may not cross partitions. Only the
requested partition's bytes are loaded. **Both supplied networks are development
networks**; no validation/test result exists. Source labels are declared metadata,
not an isomorphism detector: future relabelled/perturbed copies must retain their
original source identity. Additional whole-network holdouts and repeated independent
evolutionary runs are necessary before a transfer claim.

## Native integration and the next evolutionary run

`run_evo.py --native-seed` executes the installed, commit-verified native
`JobScheduler` and `LocalJobConfig`, which invoke `evaluate_anytime.py`. It does not
sample proposals. `--check-native` constructs the real EvolutionConfig,
DatabaseConfig, and LocalJobConfig without creating LLM clients. `--run` instantiates
`ShinkaEvolveRunner` and calls its native run method, not a local substitute.

The editable preset has 100 generation slots, four islands, archive/inspiration
sampling, 10-generation migration with rate 0.1, diff/full/cross proposals,
cost-aware UCB mutation-model selection, novelty, text feedback, and meta
recommendations every ten generations. Model names for mutation, interpretation,
novelty, and embeddings must be supplied explicitly. The **meta model is a separate
client**, not implicitly chosen by the mutation-model bandit. No current cheapest
provider is claimed; select an economical supported pool using actual prices and
available credentials when launching. The API threshold stops new submissions
but can overshoot with in-flight calls; it is not a payment-provider hard limit.

The task prompt specifies the domain model, executable API and permissible search
space. Feedback exposes measured per-source/per-budget effects and the stronger
control. Interpretations are hypotheses, never additions to fitness. Resume identity
records source/configuration/data hashes; resuming does not silently change the
benchmark. The code connects the full native run path, but a successful seed job
alone does not exercise mutations, migrations, novelty calls or meta calls.

## Execution isolation and limits

The temporary working directory, stripped environment, output bound, parent-side
scoring, and before/after source checks limit accidental leakage and corruption.
**They are not a hostile-code sandbox.** Same-user subprocesses can access other
readable host files. Run untrusted generated candidates on a disposable isolated
worker/container/VM and independently re-evaluate finalists in a fresh environment.
This milestone does not certify OS-level isolation, memory containment, or defense
against deliberate evaluator exploitation.

No original Israeli dataset has been recovered. No empirical congestion,
heterogeneous fleet, threat pursuit, cooperative flight, or infrastructure-loss
outcome has been added. A useful M2 result is a functioning search/evaluation
interface and measured fixed baselines. Zero paid provider calls and zero evolved
descendants were required to commission that interface.

## References

[A] Lange, Imajuku & Cetin. *ShinkaEvolve: Towards Open-Ended and Sample-Efficient
Program Evolution*. https://arxiv.org/abs/2509.19349

[B] SakanaAI, pinned commit `9912af12d423504b8d580f4179fd15f5f88b8c50`.
https://github.com/SakanaAI/ShinkaEvolve/tree/9912af12d423504b8d580f4179fd15f5f88b8c50
Configuration guide: https://sakanaai.github.io/ShinkaEvolve/configuration/
The pinned source, not a moving documentation page, determines executable fields.

[C] Bartz-Beielstein et al. *Benchmarking in Optimization: Best Practice and Open
Issues*. https://arxiv.org/abs/2007.03488

[D] Berthold (2013). *Measuring the impact of primal heuristics*.
https://www.sciencedirect.com/science/article/abs/pii/S0167637713001181

Data: https://github.com/bstabler/TransportationNetworks/tree/977ee75c6906337c0c7d229a1336107c7cdb533e
Anaheim documentation identifies the historical 1992 scenario and original providers.
Academic-research-only use and attribution remain applicable; no source book or
third-party page image is included.
