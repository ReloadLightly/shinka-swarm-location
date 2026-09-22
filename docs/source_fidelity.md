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
| DFBnB/Potential Search | Sections 4.7.4-4.7.5, pp. 198-200 | NOT implemented; exhaustive search is not renamed as either |
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

Exactly shortest paths; uniform probability over all equally short routes;
strictly positive rational edge costs; no edge/node removal or rerouting after
monitor placement; equal fixed monitor quality; all nodes eligible; positive
intrazonal demand rejected; positive unreachable OD demand rejected. Zero-demand
pairs may be unreachable. Parallel directed links are rejected rather than
silently collapsed. TNTP centroid-through restrictions are respected when present.

Path enumeration is a size-limited performance backend, not a route-sampling
approximation. The independent evaluator counts paths on original shortest-path
DAGs. It never computes shortest paths in a graph with monitor nodes deleted.
Rational arithmetic decides shortest-path ties; normalized demand sums use
floating point. This is not exact rational arithmetic for every reported metric.

## Reproduction claim boundary

Step 1 reconstructs the mathematical location objective and marginal-greedy rule
with a documented correction, and demonstrates them on a substituted public
benchmark. It does not reproduce the chapter's network-size statistics, plots,
traffic-flow correlations, economic conclusions, or practical drone performance.
A transparent reconstruction is not the same as copying every printed formula.
