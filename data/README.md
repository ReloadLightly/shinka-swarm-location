# Data provenance and permitted use

`sioux_falls.json` is a transformation of the Sioux Falls TNTP network and
origin-destination demand tables from the Transportation Networks for Research
Core Team. It is a public **debugging-benchmark substitution**, not the Israeli
transportation dataset in Chapter 4 and not observations of current traffic.
The upstream README explicitly describes this network as not realistic.

Pinned repository: https://github.com/bstabler/TransportationNetworks
Pinned commit: `977ee75c6906337c0c7d229a1336107c7cdb533e`.

| Source | Git blob SHA-1 | SHA-256 of source bytes |
|---|---|---|
| `SiouxFalls/SiouxFalls_net.tntp` | `66d0eca4ddcfb82f861bea040060deab7a741b2f` | `ace99b24cec69c273ff0cf3d6d074110177f0cc0ae24b0c7a9f4f4cb5e27635c` |
| `SiouxFalls/SiouxFalls_trips.tntp` | `db70eda57738877811e9ac07c25a567973d3b6a0` | `56f9566857f3f66730fd5c4232258d7ee3ac2931a476526331afd062f4958de7` |

Both reconstructed source-byte files were verified against the pinned upstream
Git blob hashes before converting this fixture. `scripts/prepare_data.py` checks
those same hashes when rebuilding from a local download or explicit network fetch.
The JSON hash used in each run is recorded in its results file.

## Transformation

Keep all 24 nodes and 76 directed links. Use the fifth TNTP field, free-flow travel
time, as the positive edge cost. Preserve its decimal value as a rational number.
Keep every positive OD entry (528 pairs, total 360,600 supplied demand units).
Omit zero-demand entries; no positive demand is dropped. Preserve
`FIRST THRU NODE=1`. All nodes are eligible monitor locations and endpoints count.
No flow assignment, congestion model, coordinates, toll, or capacity calculation
is added. No current physical time or monetary interpretation is imposed on the
upstream units. Uniform weighting across equally shortest routes is the project's
explicit modeling convention, not a measurement of drivers' route choices.

## Rebuild

From repository root, using previously downloaded pinned files:

```bash
python scripts/prepare_data.py --source-dir /path/to/SiouxFalls
```

Or download only the two pinned files explicitly:

```bash
python scripts/prepare_data.py --download
```

The base benchmark and seed evaluation run offline using the committed JSON.

## Terms and citations

The upstream repository states that its datasets are for **academic research
purposes only** and requires attribution of the dataset source in publications.
The code's MIT license does not override those terms or license the book.

- Transportation Networks for Research Core Team. *Transportation Networks for Research*.
  https://github.com/bstabler/TransportationNetworks (accessed 2026-09-22).
- Dataset history and unit caveats:
  https://github.com/bstabler/TransportationNetworks/blob/977ee75c6906337c0c7d229a1336107c7cdb533e/SiouxFalls/README.md
- Repository terms and TNTP conventions:
  https://github.com/bstabler/TransportationNetworks/blob/977ee75c6906337c0c7d229a1336107c7cdb533e/README.md
- LeBlanc, L. J., Morlok, E. K., and Pierskalla, W. P. (1975).
  An efficient approach to solving the road network equilibrium traffic assignment
  problem. *Transportation Research*, 9, 309-318. Cited as the source by the dataset maintainers.
