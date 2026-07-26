# PyReconstruct Modernization Plan — Strengthened After Adversarial Review

**Provenance.** This plan is the output of a three-way process (July 2026): an initial
Fable 5 plan (typed Python → Rust kernels → TypeScript web), an independent Opus 5
session's plan (Python-first, Qt-free core, Rust demoted), and a 16-agent adversarial
review workflow that attacked the combined claims against this repo — 5 dimension
reviewers, one independent skeptic per finding, and a synthesis pass. **10 findings
were raised; all survived verification (none refuted), several plan-breaking.** Every
file/line citation below was independently re-checked by at least two agents.

---

## 1. What the review changed (one bullet per applied amendment, with evidence)

- **Dropped `grid.py` as the flagship PyO3 target** (CONFIRMED, plan-breaking). The
  knife tool no longer uses `Grid` at all: the live `cutTraces`
  (`PyReconstruct/modules/calc/grid.py`) delegates to shapely
  (`cut_closed_traces`/`cut_open_traces` in `calc/polygon.py`), and the old Grid-based
  `cutTraces` is a commented-out block. `Grid` is only constructed without a cutline
  (in `getExterior` and `mergeTraces`), so every knife/cut branch is dead code. All
  live callers are one-shot user gestures (trace close, lasso select, merge menu,
  option-gated auto-merge — `field_widget_2_trace.py:491, 595, 1063`,
  `trace_layer.py`), never per-frame, and the heavy steps
  (`cv2.findContours/approxPolyDP/pointPolygonTest`) are already C++. Replacement
  work: delete dead code; only if profiling shows per-gesture latency matters, use
  `cv2.polylines` + numpy — no Rust.

- **Removed `pointInPoly`/`getDistanceFromTrace` from the PyO3 candidate list**
  (CONFIRMED, plan-breaking). Both are single-expression `cv2.pointPolygonTest`
  wrappers (`quantification.py:206` and `:220`) — already C-backed; a Rust rewrite
  duplicates OpenCV. The hot consumer `Section.findClosest` is already tuned (bbox
  reject + vectorized `mapPointsArray`). The real remaining cost is the
  per-point/per-trace loop in `TraceLayer.getTraces` (`trace_layer.py:178-181`) —
  which, if profiled to matter, should be batched with shapely 2.x `contains_xy`
  (shapely==2.1.1 is already pinned; do **not** reach for `matplotlib.path`, which is
  not a dependency).

- **Cancelled the Trace/Flag/Transform dataclass migration; replaced with in-place
  type annotations** (CONFIRMED, plan-breaking). `Trace` has no `__eq__` and the
  codebase depends on identity semantics for `remove`/`in`/`index`
  (`contour.py:59/67`, `section.py:457/501-502/943-944`, `field_widget_2_trace.py`)
  while value-equal duplicates are a normal state (`isSameTrace` exists precisely for
  tolerant comparison, `trace.py:82`). A default `@dataclass` (eq=True) would silently
  delete/deselect the wrong trace **and** set `__hash__=None`, raising `TypeError` at
  the `set(selected_traces)` sites (`section.py:750-751`, `trace_layer.py:530`). No
  generated method survives anyway: `name` is a validating property backed by `_name`
  (`trace.py:40/53`), `copy()` is a custom `__dict__` swap, serialization is bespoke
  positional. Any future conversion must use `eq=False`, `default_factory`, a written
  call-site inventory, and regression tests — treated as behavioral change.

- **Replaced "TypedDict/pydantic schema for .jser" with TypedDicts for dict-shaped
  levels + documentation-grade aliases for positional rows, keeping `fast_json` as
  sole serializer** (CONFIRMED, significant). The .jser leaves are heterogeneous
  positional lists (`Trace.getList` even has a wrong `-> dict` annotation,
  `trace.py:147/151`), which TypedDict cannot express; the top-level `"sections"` is a
  JSON array with `None` holes, not a dict. `fast_json.py`'s `\uXXXX` escaping,
  `OPT_NON_STR_KEYS`, and raise-based stdlib fallback are load-bearing byte-level
  invariants. Pydantic enters only transitively (via cloud-volume) with uncontrolled
  version; do not add it as a direct dependency.

- **Made schema stabilization a prerequisite workstream, not a byproduct of TS
  codegen** (CONFIRMED, significant). No version field exists anywhere in the format;
  `Series.updateJSON` runs ~15 in-place migration branches including silently pruning
  options keys (`series.py:588-590`). TS codegen can only ever snapshot the current
  writer. Amendment: add `schema_version`, freeze canonical v1, put parse+migrate in
  exactly one dual-compiled owner, seed conformance tests from
  `tests/test_section_contour.py`, keep XML legacy (`datatypes_legacy/`) out of the
  typed contract entirely.

- **Dropped "separate maturin wheel the package depends on" as an unqualified
  mechanism** (CONFIRMED, plan-breaking). PyPI publishing is disabled on this fork
  (`publish-pypi.yml` line 3: "DISABLED ON THIS FORK — releases are
  GitHub-installer-only for now") and the three real delivery paths each break:
  PyInstaller legs need per-platform wheels or a Rust toolchain each (macOS-Intel
  runner sunsets ~Fall 2027), Linux is a pip git-source install
  (`install.sh:26`), and contributors run `uv sync --frozen` against fully pinned
  deps. The plan must pick option (a) vendor-in-tree optional extension, or (b) a
  priced-in PyPI + Trusted Publisher + 4-platform-matrix prerequisite phase.

- **Moved equivalence gating from `benchmarks/` to the pytest suite, and added a Rust
  decision gate** (CONFIRMED, plan-breaking). The harness cannot gate: private data
  paths hardcoded to one developer's machine, missing files silently skipped
  (`orchestrate.py:28`), aggregate-sum metrics where offsetting per-trace errors
  cancel, no assertion or nonzero exit. Real gates are
  `tests/test_perf_equivalence.py`/`test_geometry.py` against in-repo fixtures
  (`shapes1.jser`, `shapes2.jser`, `class_series.jser` under
  `PyReconstruct/assets/checker/files/`). Bus factor: `git shortlog -sn HEAD` = 50
  commits, all one maintainer. Rust is capped to at most one leaf function, only after
  a profiled residual hotspot, else cut.

- **Struck the 3.3 GB / 6374 MB headline memory figures as motivation** (CONFIRMED,
  plan-breaking). They are cold+warm means compared against warm-only origin runs:
  >700 MB series get zero warmups, the fork runs first (cold: full parse + unpack),
  `Series.openJser` skips the parse when the hidden dir exists and the harness never
  deletes it; median-of-2 = mean of cold+warm reproduces REPORT.md's numbers exactly.
  The defensible like-for-like regression is warm-vs-warm: ~630→1560 MB (crop_4,
  2.5×) and ~1069→2915 MB (crop_ROIsmall, 2.7×), consistent with the uncontaminated
  crop_3 row (2.1×). Cold-vs-cold was never measured on origin, so the cold spike's
  attribution is unknown until re-run.

- **Replaced the "Rust-owned compact geometry store" with a targeted Python fix for
  the single regressing field — with the CPU trade stated honestly** (PARTIAL — the
  one finding whose amendment was revised in verification). The only NumPy object
  `TraceData` retains is the deferred-Feret point stash (`self._feret_points = pts` in
  `series_data.py`; the in-code comment confirms lazy Feret was "a third of the
  geometry cost"). All other cached geometry is plain Python scalars, and TraceData
  feeds only tables/CSV/sorting, never Qt/shapely rendering — so a Rust store here
  reclaims nothing on the render path while adding FFI to every table read.
  Verification correction adopted: "stash hull vertices" is *not* free — the convex
  hull is ~100% of `feret()`'s runtime, so eager hulling re-pays much of the
  lazy-Feret win on exactly the autoseg series it was added for. See the options
  ladder in Phase 1d.

- **Reframed the WASM/web workstream from "extract existing kernels" to "author a new
  engine and migrate the desktop onto it, or drop the drift-free claim"** (CONFIRMED,
  plan-breaking). No extractable kernel exists: the affine is `QTransform`
  (`transform.py`), pixels come from `QPainter` (`trace_layer.py` 797 lines,
  `image_layer.py` 437 lines), and `calc/` leans on OpenCV and shapely/GEOS. The
  kernel-shaped fraction of the codebase is tiny (~2–5% depending on counting method)
  and non-portable. While desktop pixels come from Qt's scanline rasterizer and web
  pixels from Rust/WASM, drift is guaranteed by construction. The web version is a
  rewrite of ~40k+ lines of gui/backend/datatypes (gui/ 25,066; backend/ 7,475;
  datatypes/ 8,196), not a port.

---

## 2. Revised phased plan

### Phase 0 — Measurement ground truth (prerequisite for everything below)

**Goal:** replace the two poisoned motivations (headline RAM numbers; assumed Python
hotspots) with defensible measurements.

1. Re-run the two >700 MB series **warm-vs-warm and cold-vs-cold** on both checkouts:
   delete the hidden unpack dir before every rep, give both checkouts identical warmup
   treatment. Record which portion of the cold spikes is checkout-attributable.
   (`benchmarks/orchestrate.py` fix: remove the fork-first ordering dependence and the
   silent `MISSING … continue` skip, or at minimum print a loud manifest of what
   actually ran.)
2. Profile one real interactive session (open large series → pan/zoom → hover → lasso
   → knife → merge) with `py-spy`/`cProfile` against the in-repo fixtures plus one
   autoseg series. This profile is the *only* admissible evidence for any future Rust
   candidate.
3. Update `benchmarks/REPORT.md` to strike the 3276/6374 MB figures and record the
   warm-vs-warm numbers (~630→1560, ~1069→2915 MB) as the real steady-state
   regression.

### Phase 1 — Typed Python (the main workstream)

**1a. In-place type annotations, no dataclasses.**
- Annotate `Trace`, `Flag`, `Transform`, `Contour`, `Section`, `Series` as-is. Fix
  known-wrong annotations first (e.g. `Trace.getList`'s `-> dict`, `trace.py:147`).
- Explicit rule in CONTRIBUTING: no `@dataclass` conversion of any type used with
  `in`/`remove`/`index`/`set()` without `eq=False`, `default_factory`, a written
  call-site inventory, and duplicate-trace regression tests.
- Stand up mypy (or pyright) in `test.yml` on `modules/datatypes/` and
  `modules/calc/` first; ratchet outward.

**1b. .jser typing without pydantic.**
- TypedDicts for dict-shaped levels only: jser root
  (`{"sections": list[SectionDict | None], "series": SeriesDict, "log": str}`),
  section dicts, series dict.
- Documentation-grade aliases for positional rows
  (`TraceRow: TypeAlias = list  # [name?, x, y, color, closed, negative, hidden, fill_mode, tags]`);
  structural validation stays in the existing `fromList` decoders, optionally wrapped
  by one `validate_jser()`.
- `fast_json.py` remains the sole (de)serializer; pydantic is not added as a direct
  dependency.

**1c. Schema stabilization (prerequisite for any web work).**
- Add `schema_version` to the .jser root; freeze canonical v1 (prefer keyed objects
  for trace/flag rows; if positional is kept for size, document the tuple layout
  normatively).
- One owner for parse+migrate ("read any legacy .jser → emit canonical v1"); seed its
  conformance suite from `tests/test_section_contour.py` migration tests and pre-port
  round-trip fixtures.
- Treat `options` as an explicitly versioned, prunable bag (today `updateJSON`
  silently deletes unknown keys, `series.py:588-590`). Keep XML legacy
  (`datatypes_legacy/`, `xml_json_conversions.py`) out of the typed contract — it is a
  desktop-only import path that emits v1.

**1d. Memory fix (pure Python).**
Fix the deferred-Feret stash in `TraceData.__init__` (`series_data.py`), choosing per
maintainer decision (see §3), cheapest first:
- (a) `pts.astype(np.float32)` — near-zero CPU, ~50% reclaim, feret no longer
  bit-exact (table rounds to 5 dp, CSV to 7 dp);
- (b) stash convex-hull vertices in float64 via shapely's C hull — bit-exact
  (verified 700/700 trials), ~90% reclaim (4128→~430 B/trace), eager cost
  ~30–130 µs/trace;
- (c) drop the stash; compute feret from the live Section via
  `Trace.getFeret(tform)` — full reclaim, zero refresh cost, touches
  `exportTracesCSV`.
Gate with per-element pytest assertions against the in-repo fixtures. Note this does
**not** cure the cold-open spike — that belongs to the JSON-load path
(streaming/incremental parse), pending Phase 0 cold-vs-cold data.

**1e. Cheap cleanups surfaced by the review.**
- Delete `grid.py` dead knife/cut code (commented `cutTraces`, `getInteriors`,
  `removeCuts`, knife branches of `_drawGridLine`).
- If (and only if) Phase 0 profiling flags lasso select: hoist the polygon conversion
  out of the loop in `TraceLayer.getTraces` and batch with shapely `contains_xy`.
- Vectorize the scalar `tform.map` loops in `backend/volume/objects_3D.py`
  (lines 84, 210, 281, 351) with the existing `mapPointsArray` — the 3D meshing path
  missed the vectorization the 2D path already got.

### Phase 2 — Rust (now gated, capped, and possibly empty)

**Decision gate (must pass before any Cargo.toml exists):** the Phase 0 interactive
profile must show a residual hotspot that is (i) pure-Python-hot, (ii) on a
per-frame/per-paint path, and (iii) not addressable by the already-landed
numpy/orjson techniques or by batching into existing C libraries (OpenCV, shapely,
Qt). `grid.py`, `pointInPoly`, `getDistanceFromTrace`, and the TraceData cache are
all disqualified by the findings above.

If the gate passes:
- **Cap: one leaf function.** The Python implementation remains the canonical
  reference; per-element (never summed) equivalence tests in
  `tests/test_perf_equivalence.py`/`test_geometry.py` compare both, running in the
  existing `test.yml` PR gate against in-repo fixtures. `benchmarks/` stays an
  optional local perf study — it cannot gate anything.
- **Distribution: pick exactly one** (maintainer's call, §3): (a) vendor the crate
  in-tree, compiled only inside the three installer CI legs, with pip/git/uv installs
  always taking the pure-Python path; or (b) a prerequisite phase registering a
  fork-owned PyPI project + Trusted Publisher + 4-platform maturin matrix,
  exact-pinned in pyproject.toml/uv.lock, with the macOS-Intel-runner sunset
  (~Fall 2027) and future signing/notarization costs priced in.

If the gate fails: **cut the Rust workstream entirely.** With 50/50 commits by one
maintainer and university-lab contributors, permanent dual implementations cost more
than they return.

### Phase 3 — Web (rescoped as a rewrite behind the v1 schema)

- **Precondition:** Phase 1c (canonical v1 + single migrator) complete. TS codegen
  targets the v1 write format only; the web app rejects or delegates conversion of
  anything older (server-side or via a wasm migrator) and never parses legacy layouts
  natively.
- **Drop the "no desktop-vs-web numerical drift" claim** unless the maintainer
  explicitly funds migrating desktop rasterization off QPainter onto a shared Rust
  engine (Qt reduced to a blit target). Short of that, characterize drift with
  golden-file tests instead of denying it.
- If a shared engine is funded, sequence it: (1) replace `QTransform` inside
  `datatypes/transform.py` with the Rust affine — low-risk, since `mapPointsArray`
  proves the 6-number affine is the whole contract and provides a 5.9M-point
  bit-for-bit oracle; (2) replace cv2/shapely calls in `calc/` with Rust equivalents,
  budgeted as *new numerics* with characterized differences; (3) only then
  rasterization.
- **Budget honestly:** kernel reuse covers at most a few percent of the codebase;
  gui/ (25,066), backend/ (7,475), and datatypes/ (8,196) are a rewrite, including
  replacing `series.py`'s direct-filesystem jser I/O with browser storage.
- Prior art to lean on: images already stream as multiscale zarr, and
  `funlib.show.neuroglancer` is already a dev dependency — the image/label viewer
  half is closer to configuration than development if built in the neuroglancer
  ecosystem.

### Cross-cutting (from the Opus 5 session, verified here)

- **Finish the Qt-free core (M11 seam).** `backend/settings_store.py`, `progress.py`,
  and `notifier.py` already port GUI concerns behind seams; `series.py` no longer
  imports from `gui` (`tests/test_notifier_seam.py`). Two cords remain:
  `constants/getdatetime.py:3` imports `QSettings` just to read a boolean UTC
  preference (the first failure on `import ...datatypes`, and apparently unnoticed —
  the seam-test docstring doesn't name it), and `transform.py:3`'s `QTransform`
  (four 3×3 operations, with `mapPointsArray` as a bit-exact NumPy oracle). Cutting
  both is the maintainability fix, makes the memory work measurable headlessly, and
  is the only viable web foundation.
- **The fork constraint.** This fork tracks upstream and merges its fixes; any
  language change to shared code severs that permanently, leaving a single maintainer
  owning 100% of a published tool. Weigh every Rust/web decision against it.

---

## 3. Open questions for the maintainer

1. **Rust: does it survive at all?** Phase 2's decision gate may well come back
   empty — the review found every proposed candidate already C-backed, dead, or off
   the hot path. Pre-commit to cutting the workstream if the profile shows nothing,
   given the bus factor of 1?
2. **Rust distribution model (if kept):** vendor-in-tree optional extension
   (near-zero infra; pip/git/uv users never get the speedup) vs. fork-owned PyPI +
   Trusted Publisher + 4-platform matrix (real infra; macOS-Intel runner sunsets
   ~Fall 2027; native binaries raise the signing bar). Incompatible cost profiles —
   the plan is incomplete until one is picked.
3. **Feret stash fix — which trade?** (a) float32 (cheap, trailing digits can change
   in table/CSV), (b) shapely-hull stash (bit-exact, ~90% reclaim, small eager
   per-trace cost on autoseg refresh), or (c) drop the stash and compute feret from
   the live Section (full reclaim, touches `exportTracesCSV`). Is bit-exactness of
   displayed/exported feret values a hard requirement?
4. **.jser v1 canonical format:** keyed objects for trace/flag rows (clean TS types,
   larger files, a real on-disk migration for a git-versioned format) or keep
   positional arrays with a normative layout doc (no file churn, TS gets unlabeled
   tuples)? Does byte-stability of saved files across the v1 cutover matter for
   git-diff workflows?
5. **Web ambition:** worth a ~40k-line rewrite plus a schema-stabilization
   prerequisite, or should the near-term deliverable shrink to a read-only .jser
   viewer (v1 parser + canvas rendering) that defers the engine question entirely?
6. **Line-count bookkeeping:** `calc/` measures 1,290 lines directly; one verifier
   counted 3,152 including calc-adjacent helpers. Both support the same conclusion,
   but pick a canonical counting method before quoting percentages externally.
7. **Benchmark data:** the eight lab .jser files live only on one machine. Generate
   and commit (or LFS-host) a sanitized/synthetic large-series fixture so Phase 0's
   warm/cold re-run is reproducible by anyone?
