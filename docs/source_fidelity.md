# Source-fidelity record

Primary source: Altshuler, Pentland, and Bruckstein, Chapter 4, "Defending
Large-Scale Critical Infrastructures Using a Swarm of Drones," in Yaniv Altshuler
(ed.), *Applied Swarm Intelligence*, CRC Press, printed pp. 180-209.
Book DOI: https://doi.org/10.1201/9780429276378.
The supplied volume's copyright page says 2025; the upload filename's 2024 is
not used as the bibliographic authority. No source PDF or page image is redistributed.

| Component | Source location (printed page) | Implementation/status |
|---|---|---|
| Directed road graph | Section 4.7.1, p. 193 | Directed edges preserved |
| Endpoint-inclusive routes | Section 4.7.1, p. 193, after Eq. 4.13 | Origin and destination count as covered |
| OD weighting | Section 4.7.2, p. 195, Eq. 4.14 | Nonnegative OD demand weights |
| Travel-time shortest routes | Section 4.7.3, p. 195 | Free-flow regime only in step 1 |
| Group rather than summed individual coverage | Section 4.7.4, p. 198 | A trip counted at most once |
| Marginal greedy selection | Section 4.7.4, p. 198 | Reference baseline and initial candidate |
| DFBnB/Potential Search | Section 4.7.4, pp. 198-200 | Project DAG branch-and-bound and utility-potential-ordered search controls, with independently replayed bounds; author implementations unavailable |
| Economic number/type selection | Sections 4.3-4.6 | NOT implemented; fixed monitor budgets here |
| Original Israeli data | Section 4.8, pp. 204-208 | Not recovered; numerical reproduction remains open |
| Decentralized movement/sensing | Not the executable location model in Section 4.7.4 | Not introduced |

## Explicit emendation of Equation 4.15

The rendered p. 198 prints `sigma_st / sigma_st(M)`. The immediately preceding
text defines `sigma_st(M)` as routes passing through at least one member of M;
the subsequent text describes the net traffic observed. We implement
`sigma_st(M) / sigma_st`, consistent with that definition and with Eq. 4.14.
This is an author-unconfirmed emendation, not a claim to have located official
errata. The printed inverse can divide by zero on unmonitored OD pairs.
Tests explicitly check zero monitors, two tied paths, overlap, and full coverage.

## Further discrepancies retained, not silently repaired

Equation 4.16 on p. 202 gives a GBC Gompertz amplitude of 0.89, while the
corresponding regression label in Figure 4.13 on p. 203 says 0.69. The illustrative
Section 4.6 function on p. 190 evaluates to exp(-0.2), approximately 0.819, at
zero monitors. A literal zero-monitor coverage function needs explicit boundary
interpretation. Neither curve is used as fitness here. Future economic-model
work must compare feasible integer choices, including zero deployment, and
identify any boundary or equation amendments separately.

## Declared project assumptions

Exactly minimum free-flow-time routes on the original graph, with a declared
secondary fewest-links criterion on the TNTP corpus; uniform probability over
all routes tied on **both** criteria. This secondary criterion is our explicit
adaptation to zero-time cycles: infinitely many shortest walks otherwise exist,
while counting every simple shortest path inside cyclic components would require
another representation. It excludes longer zero-time detours, and thus is not
identical to counting every time-shortest simple route. No epsilon is inserted
and no edge or node is deleted. All-minimum-time remains available for acyclic
synthetic data; relevant cycles fail under that convention. Zero-time centroid
connectors are preserved. Chicago-Sketch's source header says first through node
1 despite its 387 zones; our catalog explicitly makes zones 1-387 endpoint-only
and records both the source and effective header values. This is an interpretive
choice, not a correction confirmed by the original data authors.

No edge/node removal or rerouting after monitor placement; equal fixed monitor
quality; all nodes eligible for monitoring including trip endpoints; positive
intrazonal demand is excluded with exact accounting during TNTP import (and
rejected in an unprocessed Instance); positive unreachable OD demand is rejected. Zero-demand
pairs may be unreachable. Parallel directed links are rejected rather than
silently collapsed. TNTP centroid-through restrictions are respected when present.

Path enumeration is a size-limited performance backend, not a route-sampling
approximation. The independent evaluator counts paths on original shortest-path
DAGs. It never computes shortest paths in a graph with monitor nodes deleted.
Rational arithmetic decides shortest-path ties; normalized demand sums use
floating point. This is not exact rational arithmetic for every reported metric.

## Reproduction claim boundary

The current experiment reconstructs the location-search problem, marginal-greedy
rule, anytime comparison and certificate concept, with the stated equation and
route-convention emendations. It evaluates a substituted public corpus. It cannot
reproduce the chapter's Israeli-network statistics, figures, traffic-flow
correlations, economic conclusions, or practical drone performance. The DFBnB and
Potential Search controls are independent project implementations, and the 60-s
development profile differs from the chapter's one-hour experiment.
