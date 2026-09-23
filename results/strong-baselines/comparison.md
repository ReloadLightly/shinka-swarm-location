# Strong fixed baselines: detailed development comparison

Generated from the same independently checked timed records as README Section 5.5. Values are descriptive measurements on the recorded runtime, not cross-machine guarantees.

Measured Python/platform: `3.11.16` / `Linux-6.17.0-1022-azure-x86_64-with-glibc2.39`.
Complete comparison wall time: 498.734 seconds. This includes parent proof checks and process startup; it is not the two-second inner search budget.

| Network | Method | 0.02 s coverage (%) | 0.10 s | 0.50 s | 2.00 s | Mean delta vs timed DAG greedy (pp) |
|---|---|---:|---:|---:|---:|---:|
| Anaheim | Singleton ranking | 69.8779 | 69.8779 | 69.8779 | 69.8779 | +6.4933 |
| Anaheim | DAG greedy | 22.2215 | 71.4988 | 79.9092 | 79.9092 | +0.0000 |
| Anaheim | DAG greedy + swap | 22.2215 | 71.3595 | 79.9092 | 79.9100 | -0.0346 |
| Anaheim | Route greedy | 0.0000 | 79.8906 | 79.9092 | 79.9092 | -3.4574 |
| Anaheim | Route CELF | 0.0000 | 79.9092 | 79.9092 | 79.9092 | -3.4528 |
| Anaheim | Route CELF + swap | 0.0000 | 79.9100 | 79.9100 | 79.9100 | -3.4522 |
| Anaheim | Early topk + CELF/swap | 69.8779 | 79.9092 | 79.9100 | 79.9100 | +14.0171 |
| Anaheim | Fixed iterated search | 0.0000 | 79.9100 | 79.9110 | 79.9146 | -3.4508 |
| Anaheim | Anytime DFBnB | 0.0000 | 79.9100 | 79.9100 | 79.9100 | -3.4522 |
| Anaheim | Utility-form APTS | 0.0000 | 79.9100 | 79.9100 | 79.9100 | -3.4522 |
| SiouxFalls | Singleton ranking | 61.0649 | 61.0649 | 61.0649 | 61.0649 | -3.3902 |
| SiouxFalls | DAG greedy | 64.4551 | 64.4551 | 64.4551 | 64.4551 | +0.0000 |
| SiouxFalls | DAG greedy + swap | 65.6614 | 65.6614 | 65.6614 | 65.6614 | +1.2063 |
| SiouxFalls | Route greedy | 64.4551 | 64.4551 | 64.4551 | 64.4551 | +0.0000 |
| SiouxFalls | Route CELF | 64.4551 | 64.4551 | 64.4551 | 64.4551 | +0.0000 |
| SiouxFalls | Route CELF + swap | 65.6614 | 65.6614 | 65.6614 | 65.6614 | +1.2063 |
| SiouxFalls | Early topk + CELF/swap | 65.6614 | 65.6614 | 65.6614 | 65.6614 | +1.2063 |
| SiouxFalls | Fixed iterated search | 65.9664 | 65.9664 | 65.9664 | 65.9664 | +1.5114 |
| SiouxFalls | Anytime DFBnB | 65.6614 | 65.9664 | 65.9664 | 65.9664 | +1.4351 |
| SiouxFalls | Utility-form APTS | 65.9326 | 65.9664 | 65.9664 | 65.9664 | +1.5029 |

## Recorded costs and interruption

Route preparation below is solver-reported diagnostic timing (not the independent submission clock). It is inside the search budget. Proof replay is parent-side measured cost after capture. A missing diagnostic is not silently treated as zero; termination counts use the external parent.

| Network | Method | Route preparation median (ms) / recorded trials | Proof replay median (ms) | Parent deadlines / trials | Guard fallback trials |
|---|---|---:|---:|---:|---:|
| Anaheim | Singleton ranking | Not applicable | Not applicable | 0/36 | 0 |
| Anaheim | DAG greedy | Not applicable | Not applicable | 0/36 | 0 |
| Anaheim | DAG greedy + swap | Not applicable | Not applicable | 0/36 | 0 |
| Anaheim | Route greedy | 46.2436 / 36 | Not applicable | 0/36 | 0 |
| Anaheim | Route CELF | 46.3587 / 36 | Not applicable | 0/36 | 0 |
| Anaheim | Route CELF + swap | 46.4993 / 36 | Not applicable | 0/36 | 0 |
| Anaheim | Early topk + CELF/swap | 45.5026 / 36 | Not applicable | 0/36 | 0 |
| Anaheim | Fixed iterated search | 46.3547 / 36 | Not applicable | 36/36 | 0 |
| Anaheim | Anytime DFBnB | 46.2845 / 36 | 1126.5253 | 18/36 | 0 |
| Anaheim | Utility-form APTS | 46.3252 / 36 | 1086.3055 | 18/36 | 0 |
| SiouxFalls | Singleton ranking | Not applicable | Not applicable | 0/36 | 0 |
| SiouxFalls | DAG greedy | Not applicable | Not applicable | 0/36 | 0 |
| SiouxFalls | DAG greedy + swap | Not applicable | Not applicable | 0/36 | 0 |
| SiouxFalls | Route greedy | 6.1967 / 36 | Not applicable | 0/36 | 0 |
| SiouxFalls | Route CELF | 6.2143 / 36 | Not applicable | 0/36 | 0 |
| SiouxFalls | Route CELF + swap | 6.2272 / 36 | Not applicable | 0/36 | 0 |
| SiouxFalls | Early topk + CELF/swap | 6.2613 / 36 | Not applicable | 0/36 | 0 |
| SiouxFalls | Fixed iterated search | 6.2188 / 36 | Not applicable | 36/36 | 0 |
| SiouxFalls | Anytime DFBnB | 6.2111 / 36 | 30.1860 | 0/36 | 0 |
| SiouxFalls | Utility-form APTS | 6.2210 / 36 | 29.6887 | 0/36 | 0 |

Counters from interrupted solvers are last-emitted diagnostics, not a guarantee of completed work. The raw journals retain exact bound fractions and external receipt times. No route construction is shared for free between methods.

## Per-case paired differences

Each row averages the nine repeat/seed trials of one graph/budget. These are not nine independent source networks.

| Network | Monitors | Method | Mean checkpoint coverage (%) | Final coverage range (%) | Mean delta vs DAG swap (pp) |
|---|---:|---|---:|---:|---:|
| Anaheim | 3 | Singleton ranking | 52.4683 | 52.4683–52.4683 | +7.5617 |
| Anaheim | 3 | DAG greedy | 44.9066 | 52.4683–52.4683 | +0.0000 |
| Anaheim | 3 | DAG greedy + swap | 44.9066 | 52.4683–52.4683 | +0.0000 |
| Anaheim | 3 | Route greedy | 39.3512 | 52.4683–52.4683 | -5.5554 |
| Anaheim | 3 | Route CELF | 39.3512 | 52.4683–52.4683 | -5.5554 |
| Anaheim | 3 | Route CELF + swap | 39.3512 | 52.4683–52.4683 | -5.5554 |
| Anaheim | 3 | Early topk + CELF/swap | 52.4683 | 52.4683–52.4683 | +7.5617 |
| Anaheim | 3 | Fixed iterated search | 39.3512 | 52.4683–52.4683 | -5.5554 |
| Anaheim | 3 | Anytime DFBnB | 39.3512 | 52.4683–52.4683 | -5.5554 |
| Anaheim | 3 | Utility-form APTS | 39.3512 | 52.4683–52.4683 | -5.5554 |
| Anaheim | 6 | Singleton ranking | 61.3704 | 61.3704–61.3704 | -0.0585 |
| Anaheim | 6 | DAG greedy | 61.4289 | 74.4981–74.4981 | +0.0000 |
| Anaheim | 6 | DAG greedy + swap | 61.4289 | 74.4981–74.4981 | +0.0000 |
| Anaheim | 6 | Route greedy | 55.8735 | 74.4981–74.4981 | -5.5554 |
| Anaheim | 6 | Route CELF | 55.8735 | 74.4981–74.4981 | -5.5554 |
| Anaheim | 6 | Route CELF + swap | 55.8735 | 74.4981–74.4981 | -5.5554 |
| Anaheim | 6 | Early topk + CELF/swap | 71.2162 | 74.4981–74.4981 | +9.7872 |
| Anaheim | 6 | Fixed iterated search | 55.8735 | 74.4981–74.4981 | -5.5554 |
| Anaheim | 6 | Anytime DFBnB | 55.8735 | 74.4981–74.4981 | -5.5554 |
| Anaheim | 6 | Utility-form APTS | 55.8735 | 74.4981–74.4981 | -5.5554 |
| Anaheim | 12 | Singleton ranking | 78.9126 | 78.9126–78.9126 | +6.9168 |
| Anaheim | 12 | DAG greedy | 71.9959 | 93.1237–93.1237 | +0.0000 |
| Anaheim | 12 | DAG greedy + swap | 71.9959 | 93.1237–93.1237 | +0.0000 |
| Anaheim | 12 | Route greedy | 69.8428 | 93.1237–93.1237 | -2.1531 |
| Anaheim | 12 | Route CELF | 69.8428 | 93.1237–93.1237 | -2.1531 |
| Anaheim | 12 | Route CELF + swap | 69.8428 | 93.1237–93.1237 | -2.1531 |
| Anaheim | 12 | Early topk + CELF/swap | 89.5709 | 93.1237–93.1237 | +17.5751 |
| Anaheim | 12 | Fixed iterated search | 69.8428 | 93.1237–93.1237 | -2.1531 |
| Anaheim | 12 | Anytime DFBnB | 69.8428 | 93.1237–93.1237 | -2.1531 |
| Anaheim | 12 | Utility-form APTS | 69.8428 | 93.1237–93.1237 | -2.1531 |
| Anaheim | 24 | Singleton ranking | 86.7604 | 86.7604–86.7604 | +11.6917 |
| Anaheim | 24 | DAG greedy | 75.2073 | 99.5466–99.5466 | +0.1385 |
| Anaheim | 24 | DAG greedy + swap | 75.0688 | 99.5498–99.5498 | +0.0000 |
| Anaheim | 24 | Route greedy | 74.6414 | 99.5466–99.5466 | -0.4273 |
| Anaheim | 24 | Route CELF | 74.6599 | 99.5466–99.5466 | -0.4088 |
| Anaheim | 24 | Route CELF + swap | 74.6624 | 99.5498–99.5498 | -0.4064 |
| Anaheim | 24 | Early topk + CELF/swap | 96.3517 | 99.5498–99.5498 | +21.2829 |
| Anaheim | 24 | Fixed iterated search | 74.6680 | 99.5498–99.5773 | -0.4008 |
| Anaheim | 24 | Anytime DFBnB | 74.6624 | 99.5498–99.5498 | -0.4064 |
| Anaheim | 24 | Utility-form APTS | 74.6624 | 99.5498–99.5498 | -0.4064 |
| SiouxFalls | 1 | Singleton ranking | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | DAG greedy | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | DAG greedy + swap | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | Route greedy | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | Route CELF | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | Route CELF + swap | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | Early topk + CELF/swap | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | Fixed iterated search | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | Anytime DFBnB | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 1 | Utility-form APTS | 34.0821 | 34.0821–34.0821 | +0.0000 |
| SiouxFalls | 3 | Singleton ranking | 62.0078 | 62.0078–62.0078 | -4.9085 |
| SiouxFalls | 3 | DAG greedy | 64.5036 | 64.5036–64.5036 | -2.4126 |
| SiouxFalls | 3 | DAG greedy + swap | 66.9163 | 66.9163–66.9163 | +0.0000 |
| SiouxFalls | 3 | Route greedy | 64.5036 | 64.5036–64.5036 | -2.4126 |
| SiouxFalls | 3 | Route CELF | 64.5036 | 64.5036–64.5036 | -2.4126 |
| SiouxFalls | 3 | Route CELF + swap | 66.9163 | 66.9163–66.9163 | +0.0000 |
| SiouxFalls | 3 | Early topk + CELF/swap | 66.9163 | 66.9163–66.9163 | +0.0000 |
| SiouxFalls | 3 | Fixed iterated search | 66.9163 | 66.9163–66.9163 | +0.0000 |
| SiouxFalls | 3 | Anytime DFBnB | 66.9163 | 66.9163–66.9163 | +0.0000 |
| SiouxFalls | 3 | Utility-form APTS | 66.9163 | 66.9163–66.9163 | +0.0000 |
| SiouxFalls | 4 | Singleton ranking | 69.4121 | 69.4121–69.4121 | -5.2690 |
| SiouxFalls | 4 | DAG greedy | 73.4332 | 73.4332–73.4332 | -1.2479 |
| SiouxFalls | 4 | DAG greedy + swap | 74.6811 | 74.6811–74.6811 | +0.0000 |
| SiouxFalls | 4 | Route greedy | 73.4332 | 73.4332–73.4332 | -1.2479 |
| SiouxFalls | 4 | Route CELF | 73.4332 | 73.4332–73.4332 | -1.2479 |
| SiouxFalls | 4 | Route CELF + swap | 74.6811 | 74.6811–74.6811 | +0.0000 |
| SiouxFalls | 4 | Early topk + CELF/swap | 74.6811 | 74.6811–74.6811 | +0.0000 |
| SiouxFalls | 4 | Fixed iterated search | 74.6811 | 74.6811–74.6811 | +0.0000 |
| SiouxFalls | 4 | Anytime DFBnB | 74.6811 | 74.6811–74.6811 | +0.0000 |
| SiouxFalls | 4 | Utility-form APTS | 74.6811 | 74.6811–74.6811 | +0.0000 |
| SiouxFalls | 6 | Singleton ranking | 78.7576 | 78.7576–78.7576 | -8.2085 |
| SiouxFalls | 6 | DAG greedy | 85.8014 | 85.8014–85.8014 | -1.1647 |
| SiouxFalls | 6 | DAG greedy + swap | 86.9662 | 86.9662–86.9662 | +0.0000 |
| SiouxFalls | 6 | Route greedy | 85.8014 | 85.8014–85.8014 | -1.1647 |
| SiouxFalls | 6 | Route CELF | 85.8014 | 85.8014–85.8014 | -1.1647 |
| SiouxFalls | 6 | Route CELF + swap | 86.9662 | 86.9662–86.9662 | +0.0000 |
| SiouxFalls | 6 | Early topk + CELF/swap | 86.9662 | 86.9662–86.9662 | +0.0000 |
| SiouxFalls | 6 | Fixed iterated search | 88.1864 | 88.1864–88.1864 | +1.2202 |
| SiouxFalls | 6 | Anytime DFBnB | 87.8813 | 88.1864–88.1864 | +0.9151 |
| SiouxFalls | 6 | Utility-form APTS | 88.1525 | 88.1864–88.1864 | +1.1863 |

Zero model calls and zero validation/test performance assessments.
