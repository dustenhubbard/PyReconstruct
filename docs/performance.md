# Performance

This distribution is significantly faster than the upstream it forked from on the
open and refresh paths that dominate day-to-day work on large series - **up to
4.19x faster** to open and refresh a series, with **exact geometry equivalence**
(the speedup is not from skipped work).

The wins are algorithmic and single-threaded (NumPy-vectorized trace geometry,
deferred Feret-diameter computation, NumPy point mapping, orjson-backed `.jser`
I/O, and scoped object operations), so they help every machine and
disproportionately help the large autosegmented series that were previously near
unusable.

## Headline results

Median of repeated runs, upstream origin to this fork:

| Series | Size | Traces | Open (origin -> fork) | Open+Refresh speedup |
|---|--:|--:|---|--:|
| crop_1 | 6 MB | 2209 | 1.115 -> 0.325s | 3.44x |
| ZGBJY | 7 MB | 2511 | 1.733 -> 0.409s | 4.19x |
| crop_2 | 92 MB | 27525 | 18.87 -> 4.78s | 3.84x |
| GBSFW | 127 MB | 61121 | 28.32 -> 8.76s | 3.18x |
| NVWXP | 187 MB | 83126 | 38.79 -> 12.04s | 3.2x |
| crop_3 | 312 MB | 89388 | 63.24 -> 16.95s | 3.69x |
| crop_4 | 701 MB | 204622 | 143.14 -> 48.52s | 3.29x |
| crop_ROIsmall | 1400 MB | 492574 | 288.27 -> 100.10s | 3.11x |

Per-series geometry equivalence (section, object, and trace counts, plus summed
area / length / radius) is exact across the board.

## Full report and method

The complete report - including the equivalence checks, per-commit attribution,
hardware and dependency versions, and the measurement methodology - and the
reproducible benchmark harness live in the repository:

- **[benchmarks/REPORT.md](https://github.com/dustenhubbard/PyReconstruct/blob/main/benchmarks/REPORT.md)**
  - the full report.
- **[benchmarks/](https://github.com/dustenhubbard/PyReconstruct/tree/main/benchmarks)**
  - the harness (`harness.py`, `orchestrate.py`, `build_report.py`) and raw
  results.
