# Exact headroom, exchange neighborhoods and escape barriers

## What was already implemented, and what is new

The preceding certificate milestone already contains exact Sioux Falls optimum
proofs for budgets 1–8, verified upper bounds for Anaheim, and completed fixed
baseline coverage. `scripts/quality_study.py` and the committed reference artifacts
remain the source for those optima. The present study rechecks all 48 saved
certificates and 24 bound witnesses. It does not replace that machinery or claim
that a second implementation of the same exact references is new research.

The new contribution is a reproducible **landscape diagnostic** on the six-monitor
Sioux Falls development case identified by the earlier exploratory audit. It
answers how many deployments improve the fixed swap incumbent, how far away
improving deployments are under simultaneous replacement, whether neutral moves
provide an exit, and what temporary loss is unavoidable along single-exchange
paths. It is not an anytime benchmark, an evolved candidate or a new fitness.

## Relationship to the source chapter

Section 4.7.4 of *Applied Swarm Intelligence* (2025 edition), printed pp. 198–200,
defines group monitoring coverage and compares Greedy, DFBnB and Potential Search.
It motivates anytime search and quality certificates. That is the source of the
repository's **location-selection problem**, subject to the already documented
source emendation and benchmark substitutions in `source_fidelity.md`.

The chapter does not report this Sioux Falls exchange landscape, the baseline's
six selected nodes, this neutral component, or this escape barrier. Those are
project-specific, development-only findings. Greedy+swap is an additional project
control, not an algorithm claimed to be supplied by the chapter's authors. No
original Israeli-network numerical reproduction is implied. Potential Search is
not implemented in this milestone.

## Fixed mathematical problem

The routing, directed links, OD weights, tie handling, endpoint inclusion and
single-counting of covered routes are unchanged. Let C(S) be normalized covered
demand. For an exactly k-element deployment S, define its radius-r exchange sphere

    N_r(S) = { T : |T| = k, |S \ T| = |T \ S| = r }.

It contains exactly binomial(k,r) * binomial(n-k,r) deployments. Taking all radii
from 0 through min(k,n-k) partitions all binomial(n,k) deployments without
duplicates. Because C is monotone and k <= n, every smaller feasible deployment
can be padded to size k without lowering coverage. A complete size-k census can
therefore establish the optimum also for the repository's |S| <= k objective.
The path and neighborhood definitions below, however, keep **exactly k** locations
at each state; they are not statements about every possible search representation.

`ExchangeProblem` reuses the exact route weights and common-denominator integer
backend from the certificate module. Integer comparisons distinguish equal from
strictly greater coverage with no tolerance or rounded-decimal test. Demand means
the exact value of the loaded Instance numbers, as in the existing certificate
module, not a new interpretation of source decimals. Tractable route enumeration
is auxiliary here; it does not replace the campaign's non-enumerating DAG scorer.
Explicit route/census limits reject an oversized request rather than sample it.

The census records lower/equal/higher counts, exact extrema and example locations
for every radius. Counts are exhaustive even though example lists are bounded.
A SHA-256 digest commits to the deterministic stream of integer-valued records;
a digest alone is not a mathematical proof. `--verify` recomputes the complete
census and checks its scientific fields exactly. Reported witnesses are also
checked with the independent rational avoiding-DAG scorer, and their floating-point
production scores are compared for numerical agreement.

## Complete six-monitor census

The completed fixed swap deployment is {8,10,11,13,17,22}. Its integer coverage is
9408/10818 = 1568/1803 (about 86.9661675%). All 134,596 size-six deployments were
examined, including this starting point. Counts at radii 1 through 6 are
108, 2,295, 16,320, 45,900, 51,408 and 18,564 respectively.

There are zero strictly better deployments at radii 1, 2 and 3; one at radius 4;
two at radius 5; and zero at radius 6. There is exactly one other equal-coverage
deployment. Thus only three of the other 134,595 deployments are better. The
nearest improvement is a four-for-four replacement. The global best is 9540/10818
= 530/601 (about 88.1863561%), agreeing exactly with the previously proved optimum.
These counts are properties of this particular starting point and model, not
frequencies across a population of networks or a success rate for ShinkaEvolve.

## Neutral plateau: the previously unanswered question

A neutral move is an exactly equal-value one-for-one replacement. Breadth-first
exploration exhausts the connected neutral component and checks every outgoing
single-exchange edge. The component is exactly

    {8,10,11,13,17,22}
    {8,10,11,17,22,24}.

It has no strict single-exchange exit. We also exhaustively check radius-two and
radius-three exchanges from both members; neither has a strict improvement there.
The full census confirms there are no additional equal-valued deployments outside
these two. Thus traversing the neutral plateau does not remove this local trap.
A truncated component never receives a no-escape proof flag.

## Minimum temporary loss under single exchanges

Consider paths in the graph whose vertices are exactly k-element deployments and
whose edges are one-for-one replacements. For an initial deployment S0 and a path
ending at any T with C(T) > C(S0), define the path bottleneck as its smallest
coverage. The escape loss is

    C(S0) - max_over_escape_paths min_over_path_states C(S).

A widest-path search proposes a path with maximum bottleneck. The result is not
accepted solely on the search implementation's status. An independent verifier
checks a path and a **cut** that jointly establish the minimum loss.

For the present case, a feasible four-step path has integer coverage values

    9408 -> 9282 -> 9258 -> 9324 -> 9480,

with denominator 10818. Every step replaces one monitor and the final coverage
strictly exceeds the starting coverage. The path achieves bottleneck 9258/10818.
The cut witness consists of 18 states, includes the initial state, contains no
state better than the initial state, and all its states have value strictly above
9258/10818. The verifier enumerates all 1,944 outgoing/within-cut one-exchange
transitions and confirms that every neighbor outside the cut has coverage at most
9258/10818. Any path to a strictly better deployment must leave the cut. Therefore
no path can have a larger bottleneck than 9258/10818. The feasible path attains it,
proving the minimum required drop is

    (9408 - 9258) / 10818 = 25/1803 coverage,
    or 2500/1803 percentage points (approximately 1.3865779257 pp).

This concerns an **exploratory working solution**. An anytime algorithm may keep
and report its best incumbent throughout; the result does not require deploying
or reporting an operationally worse configuration. A restart, larger simultaneous
exchange, different state representation, or branch-guided construction can
bypass the restriction used to define the barrier. No runtime advantage is
established for the offline widest-path computation.

## Verification and interpretation

Tests compare 160 small-instance censuses with independently enumerated k-subsets
scored on the rational avoiding-DAG backend. Twenty small start-state cases check
minimum-loss results against an independent threshold-connectivity method, rather
than another invocation of the widest-path search. Other tests cover exact ties,
tiny gains, zero/full budgets, truncated neutral components, resource limits,
corrupted paths/cuts and the published Sioux Falls regression case.

The study separately verifies every displayed path/cut/extremal witness against
exact DAG scoring, recomputes the saved scientific record, and checks the original
reference proof. Source hashes and the unchanged campaign/evaluator hashes are
recorded. Timing covers the offline computation and is not used to rank campaign
algorithms. Historical result files, baseline algorithms, mutable seeds, routing,
fitness, checkpoint budgets and held-out performance remain unchanged.

The scientifically useful next hypothesis is whether a reusable search procedure
can recognize stalled local search and allocate computation to mechanisms capable
of leaving it. This study does not test an evolved mechanism, authorize replacing
the frozen seed, or establish transfer to other graphs. The starting case was
selected after an exploratory development audit; it is not a preregistered
held-out success. No LLM calls or native evolutionary generations were performed.

## Reproduction

From the repository root, with development data prepared:

```bash
python -m pip install -r requirements-certificates.txt  # For the full test suite.
python -m unittest discover -s tests -v
python scripts/prepare_suite.py --download
python scripts/exchange_study.py --output results/local_exchange_study
python scripts/exchange_study.py --output results/local_exchange_study --verify
```

The new diagnostic itself uses only the standard library. Its reuse of the saved
LP witnesses requires exact verification, not a new SciPy optimization call.
`--output` must be a new directory for execution. The separate verification mode
recomputes scientific values without overwriting the original execution record.

## Reference

Altshuler, Y., Pentland, A., and Bruckstein, A. (2025). Defending Large-Scale
Critical Infrastructures Using a Swarm of Drones. In Y. Altshuler (ed.), *Applied
Swarm Intelligence*, Section 4.7.4, pp. 198–200. CRC Press.
Book DOI: 10.1201/9780429276378. Source year follows the supplied copyright page.
