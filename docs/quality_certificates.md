# Coverage, certified quality, and remaining improvement

## Source relationship and implemented scope

Chapter 4 of *Applied Swarm Intelligence*, Section 4.7.4, compares Greedy,
Depth First Branch and Bound (DFBnB), and Potential Search. Printed p. 200
explains the certificate as the achieved solution value divided by an upper bound
on the optimum. Figure 4.11 on printed p. 201 plots that quality perspective.
This extension implements that **coverage-plus-certificate** concept for the
repository's existing, explicitly documented fixed-route model. It is not a
reproduction of the chapter's Israeli data, its complete algorithms, or its plots.
The Eq. 4.15 emendation is unchanged; see `source_fidelity.md`.

Source-derived: the group coverage interpretation and solution/upper-bound ratio.
External mathematical basis: submodular maximization and online bounds [1,2].
Project additions: the exact-rational implementation, proof-artifact schema,
small-instance partition verifier, LP-dual reconstruction, and posthoc workflow.
The new DFBnB routine is our reference implementation. Potential Search has **not**
been implemented or relabelled from another algorithm in this change.

No evolution, model access, new infrastructure-defense scenario, or holdout
performance assessment is needed for these calculations. `evaluate_anytime.py`,
the scorer, mutable seeds, four checkpoints, fitness and campaign configuration
remain byte-for-byte unchanged. The new modules are not copied into candidate
workers by the existing trusted-worker file list.

## 1. Fixed weighted coverage is monotone submodular

For the original routes P and their nonnegative normalized demand weights:

    C(S) = sum_{p in P} w_p 1[p intersects S],     sum_p w_p = 1.

Origins/destinations count and encountering multiple monitors does not multiply a
route's contribution. Positive costs make each original shortest-path graph
acyclic. Placing monitors does not remove nodes or recalculate routes.

For A subset B and v outside B, the routes newly covered by adding v to B are a
subset of those newly covered by adding v to A. With nonnegative weights this
proves Delta(v|A) >= Delta(v|B); adding a node never reduces C. The objective is
therefore normalized, monotone and submodular. This argument applies to the
implemented fixed model, not arbitrary adaptive routing or negative weights.

The classical completed exact-marginal greedy guarantee is

    C(G_k) >= [1 - (1 - 1/k)^k] OPT_k >= (1 - 1/e) OPT_k,   k >= 1.

Nemhauser, Wolsey and Fisher establish the cardinality-constrained result [1].
We do not use that guarantee to certify arbitrary algorithms, partially completed
greedy at a deadline, or floating-point tie choices without additional analysis.
The implemented certificates below are independently calculated for the actual
submitted group and are not contingent on the solver being greedy.

## 2. What a certificate says

For a feasible deployment S with L=C(S), let B be the best independently scored
feasible reference value (including S) and U any verified global upper bound:

    L <= B <= OPT_k <= U.

For U>0:

    quality_lower_bound = L/U <= L/OPT_k,
    remaining gain lies in [B-L, U-L],
    relative shortfall is at most 1-L/U.

Coverage percentages describe modeled demand, whereas the quality percentage
describes a fraction of the optimum. They are not interchangeable. Multiplication
by 100 turns a normalized absolute gain into **percentage points**, not percent.
A large U-L can mean that the bound is loose; it does not prove a better deployment
exists. Conversely, B>L is an explicit feasible witness of improvement potential.

`optimum_value_proved` requires B=U in exact arithmetic.
`deployment_optimality_proved` requires L=U. A poor deployment can have a known
optimum without itself being optimal. At k=0, the unique possible value is zero;
the code declares it optimal and uses quality=1 by an explicit 0/0 convention.
An empty deployment with k>0 does not inherit that convention.

### Arithmetic and displayed rounding

`ExactCoverage` certifies the mathematical model with the **already loaded
Instance's demand values**. Each float is converted with `Fraction(q)`, which
preserves its exact binary value. It does not reinterpret q as `Fraction(str(q))`
or silently substitute the original decimal source value. Rational coverage is
normalized by the exact sum of those represented values. Existing production
scores use floating aggregation and are compared separately for agreement.

This is a numerical-representation convention, not a change to the route model or
production fitness. Guarantees concern exact underlying model values, not every
intermediate machine-rounded instruction, uncertain traffic observations, or
real-world outcomes. The previous auxiliary audit used exact supplied decimals;
its numeric witnesses were **not** blindly imported into this implementation.

Exact values are stored as rational strings. Quality guarantees are displayed
rounded **down**, and upper bounds / maximum remaining gains rounded **up** to six
decimal places. Coverage columns use ordinary rounding. Consequently displayed
lower and upper columns can differ in their last digit even when exact values
coincide. Exact proof flags, not rounded equality, determine optimality.

## 3. Three independently checked bound sources

### 3.1 General DAG-based submodular bounds

For any anchor A (not necessarily the optimum), define

    U_k(A) = min(1, C(A) + sum of the k largest Delta(v|A), v outside A).

By monotonicity, C(O) <= C(A union O); by submodularity, the additional contribution
is at most the sum of the individual marginals of O outside A. There are at most k
such nodes. Taking the k largest gains therefore bounds every feasible O. Taking
the minimum of several valid anchor bounds remains a valid global upper bound.
The empty anchor yields the singleton-sum bound. The total-coverage cap is one.
This is the unit-cost specialization of the online-bound perspective in [2].

**The sum uses k, not k-|A|.** The latter only bounds completions forced to keep A,
not unrestricted solutions that replace its members. A regression test exhibits
the false-optimality claim caused by this mistake when |A|=k.

The exact implementation uses forward avoiding-path counts and reverse demand
dependencies on the original DAGs. It does not enumerate or sample routes.
Scores are cross-checked against a separate avoiding-path score; small-graph tests
also compare with independent simple-path enumeration. Rational arithmetic and
proof checking have additional cost and run outside candidate timing.

### 3.2 Small-instance exact DFBnB with a partition witness

For tractable references only, original routes can be enumerated exactly and
aggregated by node set. We refuse inputs above a route-count limit; there is no
fallback sampling. Rational route weights are rescaled to integers. Large integer
scales are also rejected explicitly. The default search is limited to <=32 nodes
and 100,000 expanded branching states.

A state fixes chosen nodes A and leaves a candidate set R. Its completions can add
at most k-|A| nodes, so a state-specific sum of that many largest residual gains
is admissible. A binary include/exclude split on a node partitions all feasible
completions. Terminal states can be solved directly when their remaining nodes
all fit. Completed and unfinished searches retain the entire feasible partition.

The solver emits a prefix-ordered proof: a node-index token creates the two
branches; -1 closes a leaf. A separate verifier reconstructs the partition,
recomputes every leaf's admissible bound, and takes the maximum leaf bound. It
rejects missing branches, extra tokens, invalid splits, mismatched instances and
incorrect scalar claims. It never trusts the solver's incumbent, reported upper
bound, pruning counters or completion status to establish the bound.

A verified feasible group supplies the lower bound. Equality proves the optimum.
At the expansion limit, unexpanded frontier states remain as bounded leaves,
so an incomplete search supplies a valid interval, not a false exact optimum.
The recorded time covers the reference routine's route preparation, search and
verification; shared DAG construction and the externally supplied completed
baseline warm start are outside that routine and are not hidden end-to-end wins.
This is offline reference work, not a matched-time baseline comparison.

### 3.3 Optional route-based LP-dual witnesses

With variables x_v >= 0, 0 <= y_p <= 1, constraints

    y_p <= sum_{v in p} x_v,       sum_v x_v <= k,

maximizing sum_p w_p y_p gives a relaxation of integer coverage. Upper bounds on
x are unnecessary for validity of this relaxation. For any alpha_p in [0,w_p],
set lambda=max_v sum_{p contains v} alpha_p. Then

    U_dual = min(1, k lambda + sum_p(w_p-alpha_p))

is a valid global upper bound. One direct proof bounds each covered route's alpha
mass by the sum over its selected nodes (possibly counting it repeatedly), and
bounds the remaining route mass by sum(w-alpha).

SciPy/HiGHS [3] proposes numerical multipliers. The construction rationalizes and
clips them, then a separate checker verifies **every exact coefficient**, recomputes
all node loads and derives U. Received proofs with negative/excessive coefficients
are rejected, not silently repaired. Solver status/objective alone is never a
certificate. If the optional numerical solve fails, the study preserves the DAG
bound and records LP unavailability. Verification and default certificates require
only the standard library; `requirements-certificates.txt` pins the optional
proposal dependency used for the recorded experiment.

## 4. Reporting without changing the experiment

`certify.py` consumes completed existing traces plus their exact hash-verified
suite. It reconstructs each accepted checkpoint deployment from the saved events,
checks the production scores, independently scores each group, and writes a **new
sidecar**. Reference artifacts must match the effective instance, model and k;
each bound is reverified. Invalid solver trials are marked not certified.

It does not run a candidate, change a timestamp, overwrite metrics/traces or
modify `combined_score`. Reference calculation and exact scoring costs are logged
as postprocessing. A certificate attached to a historical checkpoint means:

    Using an offline-verified bound, we can now certify the quality of the group
    that was available at that checkpoint.

It does **not** mean the solver knew or produced that certificate by that time.
An actual runtime certificate benchmark would need a distinct protocol charging
bound computations to solver time. This extension does not silently implement one.

The default partition is development. Validation/test require an explicit split
and an already completed matching trace; the current study calls neither.
`quality_study.py` accepts development data only, so it cannot produce holdout
reference performance while the campaign is still pending.

## 5. Executed study and limitations

The supplied result files contain 12 reference cases: Sioux Falls k=1..8 and
Anaheim k=3,6,12,24. Extra Sioux Falls budgets are labeled supplementary; the M2/M3
campaign budget lists are unchanged. Fixed topk, greedy and greedy+swap are allowed
to complete for this reference study. They are not rerun as timed M2 replacements.

Eight Sioux Falls optima are proved by replayed integer partition witnesses.
Anaheim receives exactly verified LP-dual bounds, which need not be tight. In
particular a displayed near-100% guarantee is not changed into exact optimality.
The 96 stored M2 baseline trials are annotated at all four checkpoints and at their
final returned deployment, using the original recorded timings without execution.

These results are **not** evolutionary discoveries. They do not fix the separately
identified timing-noise issue, implement Potential Search, recover original
Israeli data, add a new drone controller, or establish empirical detection rates.
They supply the missing distinction between achieved coverage and certified
closeness to the optimum under a fixed explicit model.

## References

[1] Nemhauser, G. L., Wolsey, L. A., & Fisher, M. L. (1978). An analysis of
approximations for maximizing submodular set functions—I. *Mathematical
Programming*, 14, 265–294. https://doi.org/10.1007/BF01588971

[2] Leskovec, J., Krause, A., Guestrin, C., Faloutsos, C., VanBriesen, J., &
Glance, N. (2007). Cost-effective Outbreak Detection in Networks. *KDD 2007*.
https://snap.stanford.edu/class/cs224w-readings/leskovec07outbreak.pdf

[3] SciPy 1.17.0. `linprog(method='highs')` documentation.
https://docs.scipy.org/doc/scipy-1.17.0/reference/optimize.linprog-highs.html

[4] Altshuler, Y., Pentland, A., & Bruckstein, A. (2025). Defending Large-Scale
Critical Infrastructures Using a Swarm of Drones. In Y. Altshuler (ed.), *Applied
Swarm Intelligence*, Chapter 4, especially pp. 198–201. CRC Press.
https://doi.org/10.1201/9780429276378
