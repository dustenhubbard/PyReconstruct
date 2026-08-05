"""The dual write from `Section` into the columnar store.

Slice 3 of the Phase 1 rewiring. Every `Section` carries a `SectionColumns`
beside its `self.contours`, mirrors every mutation into it, and checks the two
against each other. Nothing reads the store yet; this exists so that the store
is driven by real code on real data before one call site is flipped to read
from it.

WHAT CHANGED ON 2026-08-05, AND WHAT THIS FILE NOW HAS TO PROVE
---------------------------------------------------------------
This landed as a **test-only** harness behind `PYRECON_TEST_ONLY_COLUMNAR_DUAL_
WRITE`, and half of this file existed to prove the gate was unreachable from a
real launch. That property was deliberately removed: with the store built only
under the gate, `Section._columns` was `None` forever in production and there
was nothing for a consumer to read at all. The store is now built in every
session.

So the invisibility tests are **not deleted, and not left asserting something
that is now false**. Each one is replaced by the property that took its place:

  * "no shipped file may name the gate" became **the gate does not exist**, in
    any file, and no environment variable decides whether the store is built
    (`test_no_environment_variable_anywhere_decides_whether_the_store_exists`,
    `test_section_py_neither_reads_nor_writes_the_environment`). The same
    repository-wide deny-list walk is kept; only the question it asks changed.
  * "a section without the gate carries no store" became **every section
    carries a store**, whatever the environment says
    (`test_every_section_carries_a_store_whatever_the_environment_says`).
  * "mutating an ungated section stays storeless" became **mutating a section
    keeps the store in step** (`test_mutating_a_section_keeps_the_store_in_
    step`).
  * "nothing outside `Section` knows the harness exists" became **nothing
    outside `Section` writes to the store**, with the three modules that call
    the public *repair* enumerated by name so a fourth is a visible act
    (`test_only_section_py_writes_the_store_and_the_repair_sites_are_pinned`).

What did NOT change is the property the object model still has: **it is still
authoritative.** Nothing here reads a value out of the store to answer a
question, `getDict`/`save` serialize `self.contours`, and the store is a shadow
copy that is written and checked. `test_the_object_model_is_still_authoritative`
pins that directly.

THE CHECK'S SCOPE NARROWED IN TWO PLACES, ON PURPOSE, AND BOTH ARE TESTED
--------------------------------------------------------------------------
Under the gate the whole-section comparison ran after every mutation AND at
every build. Always-on made both impossible -- measured on `autoseg745`, a
whole-section comparison is ~85 ms on the median section and ~129 ms on the
busiest against a 0.002 ms `addTrace`, and a store is built at every section
load. So:

  * the per-mutation check is targeted at the row that moved
    (`test_a_mutation_does_not_materialize_the_whole_section`),
  * the build checks row arity and not values
    (`test_building_a_store_does_not_run_the_whole_section_comparison`,
    `test_building_a_store_still_checks_the_row_arity`),
  * the whole-section comparison runs at `save()`
    (`test_the_whole_section_check_runs_on_save`).

Both narrowings are asserted rather than described, so restoring the old scope
turns those tests red and reopens the cost question with a reviewer present.
What did NOT narrow is what the comparison compares: the `test_a_dropped_*`
family still drives real `Section` methods with a store entry point silently
broken and still requires the raise, and
`test_addTrace_alone_no_longer_detects_a_stale_row_map` pins the one detection
that was genuinely lost.

**That the consistency check actually catches divergence.** A safety net that is
written and trusted is worth nothing; a safety net that has been fired at is
worth what it caught. So every field the check compares gets deliberately
corrupted in the store and the check is required to notice
(`test_a_corrupted_*`), and four of the five store mutation entry points get
deliberately broken -- silently dropped, or dropped in one column only -- while a
real `Section` method drives a real mutation through them, and the assertion is
required to fire (`test_a_dropped_*`, `test_an_appendRow_that_loses_only_the_tags_
is_still_caught`). Those tests fail if the check is weakened, which is the
property that makes the rest of this file mean something.

WHAT THE FIXTURE SERIES CAN AND CANNOT EXERCISE
-----------------------------------------------
Same split `test_columnar_store_parity.py` documents: the real checked-in series
has no tagged, negative or hidden trace and no coordinate needing more than 7
decimal places, so the synthetic `tests/fixtures/parity_series.jser` carries
those domains and the tag/negative/hidden assertions run against it.
"""
import ast
import shutil
from pathlib import Path

import pytest

from PyReconstruct.modules.datatypes import Trace
from PyReconstruct.modules.datatypes import section as section_module
from PyReconstruct.modules.datatypes.columnar_store import SectionColumns
from PyReconstruct.modules.datatypes.section import ColumnarDualWriteMismatch


## The environment variable that used to gate this. Kept as a literal, and only
## here, because two tests below assert it appears nowhere else: a gate that was
## removed by deleting its `if` and left named in a launcher is a gate somebody
## rewires.
RETIRED_GATE = "PYRECON_TEST_ONLY_COLUMNAR_DUAL_WRITE"

SECTION_SOURCE = Path(section_module.__file__).resolve()
PACKAGE_ROOT = SECTION_SOURCE.parents[2]
REPO_ROOT = PACKAGE_ROOT.parent

SYNTHETIC_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "parity_series.jser"


# --- fixtures ----------------------------------------------------------------

def _busiest(sections):
    populated = [s for s in sections if s.contours]
    assert populated, "the fixture series has no populated section"
    return max(populated, key=lambda s: len(s.tracesAsList()))


@pytest.fixture
def real_section(real_series):
    """The busiest section of the real fixture series.

    No gate fixture any more, and that absence is the point: a section loaded by
    ordinary means has a store.
    """
    section = _busiest(
        [real_series.loadSection(n) for n in sorted(real_series.sections)]
    )
    assert section._columns is not None
    return section


@pytest.fixture
def synthetic_series(tmp_path):
    """The synthetic series, opened from a copy.

    A copy for the same reason the parity suite copies: `Series.openJser` builds
    a hidden working directory beside the file it is handed.
    """
    from PyReconstruct.modules.datatypes import Series

    destination = tmp_path / "parity_series.jser"
    shutil.copy(SYNTHETIC_FIXTURE, destination)
    series = Series.openJser(str(destination))
    yield series
    series.close()


@pytest.fixture
def synthetic_section(synthetic_series):
    """The busiest section of the synthetic series."""
    section = _busiest(
        [synthetic_series.loadSection(n) for n in sorted(synthetic_series.sections)]
    )
    assert section._columns is not None
    return section


def _aTrace(section, name="dual_write_probe", points=None):
    """A plausible trace, drawn near an existing one so it is in range."""
    trace = Trace(name, (11, 22, 33), closed=True)
    trace.points = points if points is not None else [
        (0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)
    ]
    return trace


def _anyTrace(section):
    """One real trace off the section, deterministically chosen."""
    name = sorted(section.contours, key=str)[0]
    return section.contours[name][0]


# =============================================================================
# The safety properties that replaced invisibility
# =============================================================================

def test_every_section_carries_a_store_whatever_the_environment_says(
    real_series, monkeypatch
):
    """The decision, at the object, and the thing Track C needs to be true.

    Replaces `test_a_section_loaded_without_the_gate_carries_no_store`, whose
    assertion is now false by design. Every value the retired gate could have
    held -- unset, "0", "1", nonsense -- produces the same section, because
    nothing reads it any more.
    """
    snum = sorted(real_series.sections)[0]

    for value in (None, "0", "", "1", "true", "2"):
        if value is None:
            monkeypatch.delenv(RETIRED_GATE, raising=False)
        else:
            monkeypatch.setenv(RETIRED_GATE, value)

        section = real_series.loadSection(snum)
        assert section._columns is not None, (
            f"no store with {RETIRED_GATE}={value!r}; the environment must not "
            "decide this any more"
        )
        assert len(section._columns) == len(section.tracesAsList())
        assert set(map(id, section._column_rows)) == {
            id(t) for t in section.tracesAsList()
        }


def test_mutating_a_section_keeps_the_store_in_step(real_series):
    """The runtime half, driving the same mutations the old ungated test drove.

    Replaces `test_mutating_an_ungated_section_stays_storeless`. Same sequence,
    opposite expectation: every hook does real work now, and the two
    representations agree at the end of it.
    """
    section = _busiest(
        [real_series.loadSection(n) for n in sorted(real_series.sections)]
    )
    trace = _aTrace(section)
    section.addTrace(trace)
    section.closeTraces([trace], closed=False)
    section.hideTraces([trace], hide=True)
    section.translateTraces(0.1, 0.1)
    section.setMag(section.mag * 2)
    section.removeTrace(trace)

    section._assertColumnsMatchObjectModel("the whole mutation sequence")
    assert len(section._columns) == len(section.tracesAsList())
    assert section_module.Section._column_rows == {}, (
        "the class-level default row map was written to"
    )


def test_the_object_model_is_still_authoritative(real_section):
    """The property that did NOT change, pinned so it cannot erode quietly.

    Always-on removed invisibility. It did not make the store a source of truth:
    `self.contours` still owns every value, and `getDict` -- what `save` writes
    -- is built from the object model alone. Corrupt the store and the section
    still serializes correctly, because nothing reads the store to answer a
    question.
    """
    trace = _anyTrace(real_section)
    row = real_section._column_rows[trace]
    expected = real_section.getDict()

    _corruptName(real_section._columns, row)
    _corruptColor(real_section._columns, row)

    assert real_section.getDict() == expected, (
        "getDict changed when only the store was corrupted, so something is "
        "reading the store as if it were authoritative"
    )
    ## And the divergence is still loud when the section is asked to check.
    with pytest.raises(ColumnarDualWriteMismatch):
        real_section._assertColumnsMatchObjectModel("a corrupted shadow copy")


def test_a_section_that_never_ran_its_constructor_is_unaffected():
    """`Section.__new__` with a handful of hand-set attributes, still working.

    A dozen test modules in this suite drive one `Section` method against a bare
    `Section.__new__` instance carrying only the attributes that method touches,
    deliberately, so the method is tested without a series, a file or a
    filesystem. `__init__` never runs on those, so a hook that reached for an
    attribute `__init__` sets would break all of them -- which is what happened
    on the first draft of this change, and is why `_columns` and `_column_rows`
    are class-level defaults as well as instance ones.

    KEPT UNCHANGED except for dropping the gate it used to set. It matters more
    now than it did: `_columns is None` used to be the shipped state and is now
    the ONLY remaining one, so this is the whole of what still has to tolerate
    it.
    """
    bare = section_module.Section.__new__(section_module.Section)
    bare.n = 1
    bare.contours = {}
    bare.added_traces = []
    bare.removed_traces = []

    trace = _aTrace(None)
    bare.addTrace(trace, log_event=False)
    bare.removeTrace(trace, log_event=False)

    assert bare._columns is None
    assert bare.added_traces == [trace]
    assert bare.removed_traces == [trace]
    assert section_module.Section._column_rows == {}


## Files allowed to name the retired gate: the tests and changelog that record
## that it was removed. Anything else is a live reference to a gate that no
## longer exists.
def _mentionsAllowed(path : Path) -> bool:
    relative = path.relative_to(REPO_ROOT)
    if relative.parts[0] in ("tests", "changelog.d", "CHANGELOG.md"):
        return True
    return False


def test_no_environment_variable_anywhere_decides_whether_the_store_exists():
    """The successor to the invisibility scan, asking the inverted question.

    This test used to prove the gate's name appeared in exactly one shipped
    file, so that no launcher could turn the harness on. The gate is gone, so
    the property worth protecting inverted with it: **the name must appear in NO
    shipped file at all**. A gate removed by deleting its `if` and left named in
    a launcher, a workflow or a settings module is a gate somebody rewires, and
    the failure mode of a half-removed gate is worse than the gate -- a store
    that exists on one machine and not another, with a consumer reading it.

    The scan machinery is kept exactly as it was, because it was hardened for a
    reason and the reason still applies; only the assertion changed.

    THE SELECTION IS A DENY-LIST, AND THAT IS THE POINT
    ---------------------------------------------------
    This test used to select files by an allow-list of fifteen "text file types
    we thought of". That list silently omitted `.command` -- the three macOS
    launchers under `launch/mac/`, including the one a user double-clicks to run
    PyReconstruct -- along with `.iss` (the Inno Setup installer script), `.in`
    (`packaging/linux/pyreconstruct.desktop.in`, the desktop-entry template the
    Linux installer expands), `.org` and every extensionless file (`Makefile`,
    `dev/Makefile`, thirteen `dev/scripts/*`). It also listed `.desktop`, which
    matches no file in this repository at all. So the detector was blind on
    precisely the shipped launch surface it exists to protect, and an allow-list
    goes blind again the moment somebody adds a file type nobody enumerated.

    Inverted, the failure mode reverses: a new file type is covered by default,
    and the only way to lose coverage is to add a suffix to `binary_suffixes`
    below -- a visible, reviewable act. Nothing here is skipped for being
    "probably fine"; the deny-list names formats that cannot hold a readable
    environment-variable export, and anything that fails to decode as UTF-8 is
    skipped by the decoder, not by a guess about its name.
    """
    ## Formats that cannot carry a shell-readable export. Everything else --
    ## `.command`, `.iss`, `.in`, `.org`, `.jser`, `.lock`, `.svg`, `.csv`, and
    ## every extensionless script -- is read.
    binary_suffixes = {
        ".png", ".ico", ".cur", ".icns", ".tif", ".tiff", ".jpg", ".jpeg",
        ".gif", ".bmp", ".webp", ".pdf",
        ".zip", ".gz", ".bz2", ".xz", ".zst", ".7z", ".tar", ".whl",
        ".pyc", ".pyo", ".pyd", ".so", ".dylib", ".dll", ".exe", ".o", ".a",
        ".ttf", ".otf", ".woff", ".woff2",
        ".npy", ".npz", ".h5", ".hdf5", ".mp4", ".mov",
    }
    ## Any hidden directory except `.github`, plus the two build/vendor trees.
    ## `.github` is deliberately NOT skipped: a CI workflow exporting the gate
    ## into a job is one of the ways a half-removed gate comes back.
    skip_dirs = {"__pycache__", "node_modules", "build", "dist"}

    def skipped(relative) -> bool:
        ## Directory components only. Checking the filename too would skip every
        ## dotfile -- `.gitignore`, and any `.envrc`/`.profile` somebody drops
        ## next to a launcher, which is exactly the shape of the leak this test
        ## is looking for.
        return any(
            part in skip_dirs or (part.startswith(".") and part != ".github")
            for part in relative.parts[:-1]
        )

    offenders = []
    scanned = 0
    for path in REPO_ROOT.rglob("*"):
        relative = path.relative_to(REPO_ROOT)
        if skipped(relative):
            continue
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() in binary_suffixes:
            continue
        if _mentionsAllowed(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError, ValueError):
            continue
        scanned += 1
        if RETIRED_GATE in text:
            offenders.append(str(relative))

    ## A selection bug that silently emptied the walk would otherwise leave this
    ## test passing vacuously, which is the failure mode that produced the
    ## allow-list hole in the first place. The repository ships far more than
    ## 200 readable files; this only has to be large enough to notice a walk
    ## that collapsed.
    assert scanned > 200, (
        f"the repository walk read only {scanned} files, so this test is not "
        "checking what it claims to check"
    )
    for launcher in (
        "launch/mac/run.command",
        "launch/windows/run.bat",
        "launch/linux/run.sh",
        "packaging/windows/PyReconstruct.iss",
        "packaging/linux/pyreconstruct.desktop.in",
    ):
        assert (REPO_ROOT / launcher).is_file(), (
            f"{launcher} moved; confirm the walk above still reaches the real "
            "launch surface before editing this list"
        )

    assert offenders == [], (
        "the retired dual-write gate is still named in a shipped file, so the "
        "removal is half done and somebody can rewire it: "
        f"{offenders}"
    )


def test_section_py_neither_reads_nor_writes_the_environment():
    """`section.py` has no environment dependency left at all.

    This used to prove only that the module could not *write* the gate. It now
    proves the stronger thing the removal is supposed to have achieved: the
    module does not consult the environment either, so there is no value any
    launcher, profile or CI job can set that changes whether a section carries a
    store. `os` is still imported and still used for paths; only `os.environ`
    and the `getenv`/`putenv` family are banned.
    """
    tree = ast.parse(SECTION_SOURCE.read_text(encoding="utf-8"))

    reaches = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "environ":
            reaches.append("os.environ")
        if isinstance(node, ast.Name) and node.id == "environ":
            reaches.append("bare environ")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("getenv", "putenv", "unsetenv"):
                reaches.append(node.func.attr)

    assert reaches == [], (
        f"section.py still consults or edits the environment: {reaches}"
    )


## The modules allowed to call `resyncColumnarStore`, and what each is
## repairing. Enumerated rather than counted so that adding a fourth is a
## visible edit to this list with a reviewer looking at it. Every one of these
## edits a section's traces or contours WITHOUT going through a `Section`
## mutator, so no dual-write hook sees it -- and every one of them was a
## `ColumnarDualWriteMismatch` raised in a real session before it called the
## repair. There are six sites across the three modules:
##
##   state_manager.py   undoState, redoState            whole-dict / per-key rebind
##   series.py          deleteObjects                   contour key deleted
##   series.py          hideObjects                     trace.setHidden in place
##   series.py          hideAllTraces                   trace.setHidden in place
##   series.py          restoreObjectVisibility         trace.setHidden in place
##   conversions.py     seriesToLabels group deletion   contour keys deleted
REPAIR_SITES = {
    "modules/backend/func/state_manager.py": "undoState / redoState",
    "modules/datatypes/series.py": (
        "deleteObjects / hideObjects / hideAllTraces / restoreObjectVisibility"
    ),
    "modules/backend/autoseg/conversions.py": "seriesToLabels group deletion",
}


def test_only_section_py_writes_the_store_and_the_repair_sites_are_pinned():
    """`Section` still owns every write to the store. The repair is public.

    Replaces `test_nothing_outside_section_py_knows_the_harness_exists`, whose
    assertion is now false: three modules legitimately name
    `resyncColumnarStore`, because always-on made their out-of-class trace and
    contour edits into crashes that only a rebuild can fix.

    What survives, and is the property that actually protects the design, is
    narrower and sharper than "nobody has heard of it": **nothing outside
    `section.py` performs a store write.** No module calls a `_dualWrite` hook,
    reaches into `_column_rows`, or drives `SectionColumns`' six mutation entry
    points against a section's store. The single exception is
    `resyncColumnarStore`, the public repair, and it is allowed only at the
    sites named in `REPAIR_SITES`.

    `self._columns` is deliberately not scanned. It collided with an unrelated
    `TraceView._columns` (`columnar_store.py`, Phase 1 slices 4/6) the first
    time both landed on the same tree: the name is common enough that two
    independent classes picked it for unrelated fields.
    """
    ## Scanned through the AST rather than by substring, which is the difference
    ## between "this file references the name" and "this file mentions the name
    ## in a comment saying why it calls the repair". The repair sites explain
    ## themselves in prose, and prose is not a call.
    private_names = ("_column_rows", "ColumnarDualWriteMismatch")

    def identifiers(tree):
        found = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                found.add(node.id)
            elif isinstance(node, ast.Attribute):
                found.add(node.attr)
        return found

    private_offenders = {}
    repair_callers = {}
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path.resolve() == SECTION_SOURCE:
            continue
        relative = str(path.relative_to(PACKAGE_ROOT))
        names = identifiers(ast.parse(path.read_text(encoding="utf-8")))

        hits = sorted(
            name for name in names
            if name in private_names or name.startswith("_dualWrite")
        )
        if hits:
            private_offenders[relative] = hits

        if "resyncColumnarStore" in names:
            repair_callers[relative] = True

    assert private_offenders == {}, (
        "the dual write's private surface leaked out of Section: "
        f"{private_offenders}"
    )
    assert set(repair_callers) == set(REPAIR_SITES), (
        "the set of out-of-class sites calling resyncColumnarStore() changed. "
        "Every one of these replaces Section.contours from outside Section and "
        "is a ColumnarDualWriteMismatch in a real session without the repair, "
        f"so adding or losing one is a design change: {sorted(repair_callers)} "
        f"against {sorted(REPAIR_SITES)}"
    )


def test_the_retired_gate_is_gone_from_the_module_that_defined_it():
    """No constant, no predicate, no dormant branch.

    A gate left as a constant nobody reads is a gate a later change re-wires by
    adding one `if`. `section.py` must not carry the name, the predicate that
    read it, or an exported symbol either could hang off.
    """
    source = SECTION_SOURCE.read_text(encoding="utf-8")
    assert RETIRED_GATE not in source
    assert not hasattr(section_module, "DUAL_WRITE_ENV_VAR")
    assert not hasattr(section_module, "dualWriteRequested")


# =============================================================================
# The dual write itself, on real material
# =============================================================================

def test_a_freshly_loaded_section_already_agrees(real_section):
    """Construction alone puts the two representations in step.

    `Section.__init__` builds the store from the contours it just parsed, and
    the check runs there too -- so a load that produced a store disagreeing with
    the section it was built from never gets as far as a mutation.
    """
    assert len(real_section._columns) == len(real_section.tracesAsList())
    assert real_section._column_rows
    real_section._assertColumnsMatchObjectModel("a check with nothing wrong")


def test_the_row_map_is_an_identity_map(real_section):
    """Keyed on the trace object, which is what the object model matches on.

    `Trace` defines neither `__eq__` nor `__hash__`, so the dict below is keyed
    on identity -- the same identity `Contour.remove` runs on via `list.remove`.
    Two traces that are equal field-for-field are two different rows, and this
    pins that rather than leaving it to be inferred.
    """
    original = _anyTrace(real_section)
    twin = original.copy()
    real_section.addTrace(twin)

    assert real_section._column_rows[original] != real_section._column_rows[twin]
    assert len(real_section._columns) == len(real_section.tracesAsList())


def test_addTrace_then_removeTrace_stays_consistent(real_section):
    before = len(real_section._columns)
    trace = _aTrace(real_section)

    real_section.addTrace(trace)
    assert len(real_section._columns) == before + 1
    assert real_section._columns.getPoints(real_section._column_rows[trace]) == [
        tuple(p) for p in trace.points
    ]

    real_section.removeTrace(trace)
    assert len(real_section._columns) == before
    assert trace not in real_section._column_rows


def test_a_trace_with_too_few_points_enters_neither_representation(real_section):
    """`addTrace` refuses a one-point trace, and the store must refuse it too.

    The guard is the first thing `addTrace` does, before the store hook, so this
    is really a test that the hook sits on the far side of the early return.
    """
    before = len(real_section._columns)
    real_section.addTrace(_aTrace(real_section, points=[(0.0, 0.0)]))
    assert len(real_section._columns) == before
    real_section._assertColumnsMatchObjectModel("a refused addTrace")


def test_a_two_point_trace_is_forced_open_in_both(real_section):
    """`addTrace` flips `closed` for a two-point trace before appending.

    Which means the store has to be written from the *coerced* trace, not the
    one the caller handed over. Reading `trace.closed` after the coercion is
    what makes that true, and this is the test that would catch the hook being
    moved above it.
    """
    trace = _aTrace(real_section, points=[(0.0, 0.0), (1.0, 1.0)])
    assert trace.closed is True
    real_section.addTrace(trace)
    assert trace.closed is False
    assert real_section._columns.getFlag(
        real_section._column_rows[trace], "closed"
    ) is False


def test_editTraceAttributes_renames_recolours_retags_and_refills(real_section):
    """The composite path, all four fields at once, including a rename.

    A rename moves the trace between contours in the object model and between
    contour indices in the store; the check compares the whole contour set, so a
    rename that landed in one and not the other is caught by the contour-set
    complaint rather than by a field comparison.
    """
    trace = _anyTrace(real_section)
    old_name = trace.name

    real_section.editTraceAttributes(
        [trace],
        name="renamed_by_the_dual_write_test",
        color=(9, 8, 7),
        tags={"alpha", "beta"},
        mode=("solid", "selected"),
    )

    assert "renamed_by_the_dual_write_test" in real_section._columns.contourNames()
    rows = real_section._columns.rowsForContour("renamed_by_the_dual_write_test")
    assert len(rows) == 1
    assert real_section._columns.getTags(rows[0]) == {"alpha", "beta"}
    assert real_section._columns.getColor(rows[0]) == [9, 8, 7]
    assert real_section._columns.getFillMode(rows[0]) == ["solid", "selected"]
    assert old_name not in real_section._columns.contourNames() or rows[0] not in \
        real_section._columns.rowsForContour(old_name)


def test_translateTraces_moves_the_stored_coordinates(real_section):
    trace = _anyTrace(real_section)
    real_section.addSelectedTrace(trace)
    before = [tuple(p) for p in trace.points]

    real_section.translateTraces(0.25, -0.5)

    after = [tuple(p) for p in trace.points]
    assert after != before
    row = real_section._column_rows[trace]
    assert real_section._columns.getPoints(row) == after


@pytest.mark.parametrize(
    "drive",
    [
        pytest.param(lambda s, t: s.editTraceRadius([t], 0.9), id="editTraceRadius"),
        pytest.param(
            lambda s, t: s.editTraceShape([t], [(0, 0), (1, 0), (1, 1), (0, 1)]),
            id="editTraceShape",
        ),
        pytest.param(lambda s, t: s.makeNegative([t], negative=True), id="makeNegative"),
        pytest.param(lambda s, t: s.deleteTraces([t]), id="deleteTraces"),
    ],
)
def test_the_other_remove_mutate_add_composites_stay_consistent(real_section, drive):
    """Six `Section` methods are built out of removeTrace/addTrace, not two.

    The design proposal named four mutation paths to route. Reading the class
    says `editTraceAttributes`, `translateTraces`, `editTraceRadius`,
    `editTraceShape`, `makeNegative` and `deleteTraces` are all composed of the
    two primitives, so hooking the primitives covers all of them -- and each of
    them is driven here rather than left as a claim about the source.
    """
    drive(real_section, _anyTrace(real_section))
    real_section._assertColumnsMatchObjectModel("a composite mutation")


def test_the_composites_write_through_the_primitives_and_nothing_else(
    real_section, monkeypatch
):
    """Pin the composition, so a future hook cannot be added and double-write.

    `editTraceAttributes` must produce exactly one store removal and one store
    append per trace, through `removeTrace`/`addTrace`, and must not reach any
    in-place hook. If somebody later gives `editTraceAttributes` its own hook,
    this fails rather than the store quietly gaining a duplicate row.
    """
    calls = []
    for hook in ("_dualWriteAppend", "_dualWriteRemove", "_dualWriteAttribute",
                 "_dualWriteAllCoordinates"):
        real = getattr(real_section, hook)

        def wrapper(*args, __hook=hook, __real=real, **kwargs):
            calls.append(__hook)
            return __real(*args, **kwargs)

        monkeypatch.setattr(real_section, hook, wrapper)

    real_section.editTraceAttributes(
        [_anyTrace(real_section)], name=None, color=(1, 2, 3), tags=None, mode=None
    )

    assert calls == ["_dualWriteRemove", "_dualWriteAppend"]


@pytest.mark.parametrize(
    "drive, attribute, expected",
    [
        pytest.param(
            lambda s, t: s.hideTraces([t], hide=True), "hidden", True, id="hideTraces"
        ),
        pytest.param(
            lambda s, t: s.closeTraces([t], closed=False), "closed", False,
            id="closeTraces",
        ),
    ],
)
def test_the_in_place_attribute_mutators_reach_the_store(
    real_section, drive, attribute, expected
):
    """The four mutators that never leave the contour need their own hooks.

    `hideTraces`, `hideOtherTraces`, `unhideAllTraces` and `closeTraces` write a
    trace attribute in place and do not go through addTrace/removeTrace, so the
    primitives do not cover them. Two are driven here; the other two below.
    """
    trace = _anyTrace(real_section)
    drive(real_section, trace)
    row = real_section._column_rows[trace]
    assert real_section._columns.getFlag(row, attribute) is expected


def test_unhideAllTraces_and_hideOtherTraces_reach_the_store(real_section):
    keep = _anyTrace(real_section)
    real_section.hideOtherTraces(keep=[keep])
    for trace in real_section.tracesAsList():
        row = real_section._column_rows[trace]
        assert real_section._columns.getFlag(row, "hidden") == trace.hidden

    real_section.unhideAllTraces()
    for trace in real_section.tracesAsList():
        assert real_section._columns.getFlag(
            real_section._column_rows[trace], "hidden"
        ) is False


def test_setMag_rewrites_every_stored_coordinate(real_section):
    """`setMag` scales every trace's points in place and never touches a contour.

    The one mutator that needs `setCoordinates` rather than an attribute write,
    and the one that moves every row of the section at once.
    """
    before = {
        id(t): [tuple(p) for p in t.points] for t in real_section.tracesAsList()
    }
    generation = real_section._columns.generation

    real_section.setMag(real_section.mag * 2)

    for trace in real_section.tracesAsList():
        row = real_section._column_rows[trace]
        assert real_section._columns.getPoints(row) == [tuple(p) for p in trace.points]
        assert [tuple(p) for p in trace.points] != before[id(trace)]
    assert real_section._columns.generation > generation


def test_the_tform_setter_moves_the_generation_and_no_row(real_section):
    """An alignment change rewrites rendered geometry and no stored byte.

    The store's docstring is explicit that a counter which did not move here
    would reproduce a measured stale-render bug in a new place, so the hook
    exists even though nothing this slice does reads the counter.
    """
    from PyReconstruct.modules.datatypes import Transform

    generation = real_section._columns.generation
    rows = real_section._columns.rowCount

    real_section.tform = Transform([2, 0, 5, 0, 2, 5])

    assert real_section._columns.generation > generation
    assert real_section._columns.rowCount == rows
    real_section._assertColumnsMatchObjectModel("a transform change")


def test_tags_negative_and_hidden_survive_a_mutation_on_synthetic_material(
    synthetic_section
):
    """The domains the real fixture series does not carry at all.

    Measured in `test_columnar_store_parity.py`: the checked-in real series has
    no tagged, negative or hidden trace, so a dual-write suite that only used it
    would leave three of the eight compared fields untested on real material.
    """
    tagged = [t for t in synthetic_section.tracesAsList() if t.tags]
    assert tagged, "the synthetic fixture stopped carrying a tagged trace"

    trace = tagged[0]
    synthetic_section.editTraceAttributes(
        [trace], name=None, color=None, tags={"kept", "added"}, mode=None
    )
    synthetic_section._assertColumnsMatchObjectModel("a tag edit")

    stored_tags = {
        frozenset(synthetic_section._columns.getTags(row))
        for row in synthetic_section._columns.rowsForContour(trace.name)
    }
    assert frozenset({"kept", "added"}) in stored_tags


def test_importTraces_rebuilds_the_store_from_the_result(real_series):
    """The one path that replaces contour lists wholesale instead of mutating.

    `Contour.importTraces` rebinds `self.traces` outright, so there is no
    sequence of row operations to mirror and the store is rebuilt from the
    object model afterwards. Stated as a limit in the source and pinned here:
    what is guaranteed is that the two agree once the import returns.
    """
    numbers = sorted(real_series.sections)
    keeper = _busiest([real_series.loadSection(n) for n in numbers])
    donor = real_series.loadSection(keeper.n)

    extra = _aTrace(donor, name="imported_by_the_dual_write_test")
    donor.addTrace(extra)

    keeper.importTraces(donor)

    keeper._assertColumnsMatchObjectModel("an import")
    donor._assertColumnsMatchObjectModel("an import, on the donor")
    assert len(keeper._columns) == len(keeper.tracesAsList())


# =============================================================================
# Mutation-testing the safety net: prove the check catches things
# =============================================================================

def _corruptName(store, row):
    store.setAttribute(row, "name", "a_name_the_object_model_does_not_have")


def _corruptPoints(store, row):
    store.setCoordinates(row, [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)])


def _corruptPointValue(store, row):
    points = store.getPoints(row)
    points[0] = (points[0][0] + 1e-9, points[0][1])
    store.setCoordinates(row, points)


def _corruptColor(store, row):
    current = store.getColor(row)
    store.setAttribute(row, "color", [(current[0] + 1) % 256, current[1], current[2]])


def _corruptFillMode(store, row):
    current = store.getFillMode(row)
    replacement = ("solid", "selected") if current != ["solid", "selected"] \
        else ("transparent", "unselected")
    store.setAttribute(row, "fill_mode", replacement)


def _corruptTags(store, row):
    store.setTags(row, {"a-tag-the-object-model-does-not-have"})


def _corruptRowCount(store, row):
    store.removeRow(row)


@pytest.mark.parametrize(
    "corrupt, expected_in_message",
    [
        pytest.param(_corruptName, "contours only in", id="name"),
        pytest.param(_corruptPoints, "points:", id="points-length"),
        pytest.param(_corruptPointValue, "points[0]:", id="points-value"),
        pytest.param(_corruptColor, "color:", id="color"),
        pytest.param(_corruptFillMode, "fill_mode:", id="fill_mode"),
        pytest.param(_corruptTags, "tags:", id="tags"),
        ## The chosen trace is its contour's only one, so losing its row loses
        ## the whole contour from the store. `test_a_missing_row_inside_a_shared
        ## _contour_is_caught` covers the other shape, where the contour
        ## survives with one trace too few.
        pytest.param(_corruptRowCount, "contours only in the object model",
                     id="removed-row"),
        pytest.param(
            lambda store, row: store.setAttribute(
                row, "closed", not store.getFlag(row, "closed")
            ),
            "closed:", id="closed",
        ),
        pytest.param(
            lambda store, row: store.setAttribute(
                row, "negative", not store.getFlag(row, "negative")
            ),
            "negative:", id="negative",
        ),
        pytest.param(
            lambda store, row: store.setAttribute(
                row, "hidden", not store.getFlag(row, "hidden")
            ),
            "hidden:", id="hidden",
        ),
    ],
)
def test_a_corrupted_column_is_caught_by_the_check(
    real_section, corrupt, expected_in_message
):
    """Every field the check compares, deliberately broken, one at a time.

    This is the mutation test for the safety net. A check that compared six of
    the eight fields would pass every other test in this file and would let a
    real divergence through in the two it skipped; the only way to know it
    compares all of them is to break each one and watch it fire.

    The corruptions go through the store's own public mutation entry points, so
    each one is a divergence of a shape a genuinely buggy hook could produce --
    a write that landed on the wrong value, not an impossible state poked into a
    private list.
    """
    trace = _anyTrace(real_section)
    row = real_section._column_rows[trace]

    ## Sanity: the check passes before the corruption. Without this the test
    ## could be green because the section was already broken.
    real_section._assertColumnsMatchObjectModel("a check with nothing wrong")

    corrupt(real_section._columns, row)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section._assertColumnsMatchObjectModel("a deliberate corruption")

    assert expected_in_message in str(caught.value)
    assert "a deliberate corruption" in str(caught.value)


def test_a_missing_row_inside_a_shared_contour_is_caught(real_section):
    """A contour that survives with one trace too few.

    The parametrized case above removes the only row of its contour, which the
    contour-set comparison catches. This is the harder one: the contour is still
    in both, the names still line up, and only the length differs -- which is
    what a routing bug that dropped one `addTrace` out of two would look like.
    """
    trace = _anyTrace(real_section)
    twin = trace.copy()
    real_section.addTrace(twin)
    assert len(real_section.contours[trace.name]) >= 2

    real_section._columns.removeRow(real_section._column_rows[twin])

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section._assertColumnsMatchObjectModel("a lost row")

    assert "the store holds" in str(caught.value)
    assert "traces, the object model holds" in str(caught.value)


def test_a_dropped_appendRow_is_caught_by_addTrace(real_section, monkeypatch):
    """Break the store write, drive the real method, require the raise.

    The corruption tests above call the check directly. This family goes through
    `Section`'s own mutators with a store entry point silently doing nothing,
    which is the shape a real routing bug has: the object model moves, the store
    does not, and nothing else in the process notices.
    """
    monkeypatch.setattr(SectionColumns, "appendRow", lambda self, **kwargs: None)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section.addTrace(_aTrace(real_section))

    assert "addTrace" in str(caught.value)


def test_a_dropped_removeRow_is_caught_by_removeTrace(real_section, monkeypatch):
    trace = _anyTrace(real_section)
    monkeypatch.setattr(SectionColumns, "removeRow", lambda self, row: None)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section.removeTrace(trace)

    assert "removeTrace" in str(caught.value)


def test_a_dropped_setAttribute_is_caught_by_closeTraces(real_section, monkeypatch):
    trace = _anyTrace(real_section)
    monkeypatch.setattr(
        SectionColumns, "setAttribute", lambda self, row, attribute, value: None
    )

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section.closeTraces([trace], closed=not trace.closed)

    assert "closed" in str(caught.value)


def test_a_dropped_setCoordinates_is_caught_by_setMag(real_section, monkeypatch):
    monkeypatch.setattr(SectionColumns, "setCoordinates", lambda self, row, points: None)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section.setMag(real_section.mag * 2)

    assert "points" in str(caught.value)


def test_an_appendRow_that_loses_only_the_tags_is_still_caught(
    synthetic_section, monkeypatch
):
    """The subtle break, not the total one.

    A store write that succeeds in seven columns and drops the eighth is what a
    real hook bug looks like -- a forgotten keyword argument -- and it is the
    case a check comparing "the same number of traces in the same contours"
    would sail straight past. Run on the synthetic series because the real one
    has no tagged trace to lose.
    """
    tagged = [t for t in synthetic_section.tracesAsList() if t.tags]
    assert tagged, "the synthetic fixture stopped carrying a tagged trace"
    trace = tagged[0]

    real_append = SectionColumns.appendRow

    def appendWithoutTags(self, **kwargs):
        kwargs["tags"] = ()
        return real_append(self, **kwargs)

    monkeypatch.setattr(SectionColumns, "appendRow", appendWithoutTags)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        ## A remove/mutate/add composite, so the broken append is reached
        ## through a real edit rather than by adding an invented trace.
        synthetic_section.editTraceAttributes(
            [trace], name=None, color=None, tags=None, mode=("solid", "selected")
        )

    assert "tags:" in str(caught.value)


def test_a_trace_the_store_has_no_row_for_is_refused_loudly(real_section):
    """The other half of "raise loudly": an unmirrored trace, not a bad value.

    A `Section` mutator handed a trace that never entered through `addTrace` has
    no row to write to. Guessing one, or skipping the write, would be exactly
    the silent divergence this slice exists to prevent.
    """
    stranger = _aTrace(real_section, name=_anyTrace(real_section).name)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section.hideTraces([stranger], hide=True)

    assert "holds no row for" in str(caught.value)


def test_the_check_reports_every_divergent_field_not_only_the_first(real_section):
    """One bad mutation usually breaks more than one column.

    Reporting only the first difference makes the second one invisible until the
    first is fixed, which turns one debugging session into three.
    """
    trace = _anyTrace(real_section)
    row = real_section._column_rows[trace]
    _corruptColor(real_section._columns, row)
    _corruptTags(real_section._columns, row)
    real_section._columns.setAttribute(row, "hidden", not trace.hidden)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section._assertColumnsMatchObjectModel("three corruptions at once")

    message = str(caught.value)
    assert "color:" in message and "tags:" in message and "hidden:" in message


def test_resyncing_repairs_a_corrupted_store(real_section):
    """The escape hatch the import path uses, and its only guarantee.

    `resyncColumnarStore` throws the store away and rebuilds it from the object
    model, so it *cannot* report a divergence that happened before it ran. That
    is why it is used only where there is no per-row mutation to mirror, and
    saying so here is part of the record.
    """
    row = real_section._column_rows[_anyTrace(real_section)]
    _corruptTags(real_section._columns, row)
    with pytest.raises(ColumnarDualWriteMismatch):
        real_section._assertColumnsMatchObjectModel("a corruption")

    real_section.resyncColumnarStore()
    real_section._assertColumnsMatchObjectModel("after a resync")


def _undoStyleRestore(section):
    """An out-of-class whole-dict rebind to equal-valued copies.

    The shape `backend/func/state_manager.py` restores a section with. Every
    trace is a `Contour.copy()` product: equal field for field to the trace it
    replaces, and a different object.
    """
    section.contours = {
        name: contour.copy() for name, contour in section.contours.items()
    }


def test_an_out_of_class_rebind_is_caught_even_though_every_value_matches(
    real_section
):
    """The staleness the value comparison alone could not see.

    An undo restore replaces `Section.contours` wholesale with copies. Reading
    values back out of the store finds nothing wrong -- the copies are equal
    field for field -- while `_column_rows` is left keyed on traces no contour
    holds any more. Before the row map was compared as well, this passed, and
    the run then died several mutations later on a "holds no row for" naming a
    trace that was plainly still in its contour. The failure belongs here, at
    the first hooked mutation after the rebind, naming the rebind.
    """
    _undoStyleRestore(real_section)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section._assertColumnsMatchObjectModel("after an undo-style restore")

    message = str(caught.value)
    assert "the row map is stale" in message
    assert "resyncColumnarStore" in message


@pytest.mark.parametrize(
    "drive",
    [
        pytest.param(lambda s: s.removeTrace(_anyTrace(s)), id="removeTrace"),
        pytest.param(
            lambda s: s.hideTraces([_anyTrace(s)], hide=True), id="hideTraces"
        ),
        pytest.param(
            lambda s: s.closeTraces([_anyTrace(s)], closed=False), id="closeTraces"
        ),
        pytest.param(lambda s: s.setMag(s.mag * 2), id="setMag"),
    ],
)
def test_a_mutation_touching_an_existing_trace_still_names_a_stale_row_map(
    real_section, drive
):
    """Driven through a `Section` method, because that is how it would happen.

    REWRITTEN, AND THE REWRITE IS THE HONEST PART
    ----------------------------------------------
    This used to drive `addTrace` and require the raise, on the strength of the
    whole-section check running after every mutation. Always-on made that check
    unaffordable per mutation (85-129 ms on `autoseg745`), so the per-mutation
    check is targeted at the row that moved -- and `addTrace` after an
    undo-style rebind writes a brand-new row that is perfectly correct, so
    **`addTrace` no longer detects a stale row map.** That is a real narrowing,
    it is pinned by `test_addTrace_alone_no_longer_detects_a_stale_row_map`
    below rather than left for somebody to discover, and it is why the four
    out-of-class rebind sites now call the repair instead of relying on
    detection.

    What survives is the case that matters more: any mutation that touches a
    trace the section already held goes through `_rowFor`, which cannot find the
    replaced object in the identity map and says so. That is every edit a user
    performs on existing work.
    """
    _undoStyleRestore(real_section)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        drive(real_section)

    assert "holds no row for" in str(caught.value)


def test_addTrace_alone_no_longer_detects_a_stale_row_map(real_section):
    """The gap the narrowed check leaves, pinned rather than left to be found.

    A brand-new trace gets a brand-new row, and a targeted check compares that
    row against that trace and finds them in agreement -- correctly, because
    they are. Nothing about the append can see that every OTHER row is now keyed
    on a discarded object. `save()` catches it, and the four out-of-class rebind
    sites do not reach here at all because they repair first.

    If a future change puts a whole-section comparison back on the mutation
    path, this test fails, and that is the right outcome: it means the cost
    trade was reopened and somebody should look at the measurement again.
    """
    _undoStyleRestore(real_section)

    real_section.addTrace(_aTrace(real_section))  # does not raise

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section._assertColumnsMatchObjectModel("the coarse net, by hand")
    assert "the row map is stale" in str(caught.value)


def test_resyncing_after_an_out_of_class_rebind_is_the_documented_remedy(
    real_section
):
    """The harness comment says to call `resyncColumnarStore()`. It works.

    A detector that fires with no way to clear it is a detector nobody keeps, so
    pin the remedy next to the detection.
    """
    _undoStyleRestore(real_section)
    with pytest.raises(ColumnarDualWriteMismatch):
        real_section._assertColumnsMatchObjectModel("after an undo-style restore")

    real_section.resyncColumnarStore()
    real_section._assertColumnsMatchObjectModel("after the remedy")
    real_section.addTrace(_aTrace(real_section))
    real_section.removeTrace(_anyTrace(real_section))


def test_a_trace_removed_from_its_contour_from_outside_is_caught(real_section):
    """The other direction: the map holds a row the object model dropped.

    `Contour.remove` reached directly, bypassing `Section.removeTrace` and so
    bypassing the hook. The columns still carry the row, so the arity comparison
    would catch this one too -- both complaints are wanted, because together
    they say which side moved.
    """
    trace = _anyTrace(real_section)
    real_section.contours[trace.name].remove(trace)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section._assertColumnsMatchObjectModel("an out-of-class removal")

    assert "the row map is stale" in str(caught.value)


# =============================================================================
# The out-of-class repair sites: the paths always-on turned into crashes
# =============================================================================
#
# Under the gate none of these could reach a section carrying a store, and the
# source comment said only that they "owe the resync". Always-on made each one a
# `ColumnarDualWriteMismatch` raised at the user on the next edit, which was the
# single largest thing this change had to fix. Each is driven for real here --
# not simulated with `_undoStyleRestore` -- because a repair call that is present
# but unreachable, or placed before the rebind instead of after it, would pass
# every simulated test and still crash a session.

def test_deleting_an_object_leaves_every_touched_section_consistent(real_series):
    """`Series.deleteObjects` drops a contour key from outside `Section`.

    It also removes from a list it is iterating, so `removeTrace` is not reached
    for every trace of a multi-trace contour. Either alone leaves rows in the
    store for traces the object model no longer has.
    """
    name = sorted(real_series.data["objects"])[0]

    touched = [
        snum for snum, section in real_series.enumerateSections(show_progress=False)
        if name in section.contours and len(section.contours[name])
    ]
    assert touched, "the fixture object is on no section"

    real_series.deleteObjects([name])

    for snum in touched:
        section = real_series.loadSection(snum)
        assert name not in section.contours or section.contours[name].isEmpty()
        section._assertColumnsMatchObjectModel("after deleteObjects")
        ## And the section takes another edit without raising, which is what the
        ## user does next and what used to fail.
        section.addTrace(_aTrace(section))
        section.save()


def test_a_section_edited_after_an_undo_does_not_raise(real_section, real_series):
    """The undo restore, driven through `SectionStates` itself.

    `undoState` replaces `section.contours` from outside `Section` -- the whole
    dict on the single-state branch, one key at a time on the multi-state one --
    and both branches end in the repair. Without it the `addTrace` at the bottom
    of this test raises `ColumnarDualWriteMismatch`, which is a crash in the
    user's face on the first stroke after Ctrl+Z.
    """
    from PyReconstruct.modules.backend.func.state_manager import SectionStates

    states = SectionStates(real_section, real_series)

    before = len(real_section.tracesAsList())
    states.addState(real_section, real_series)
    real_section.addTrace(_aTrace(real_section, name="undone_by_the_dual_write_test"))
    assert len(real_section.tracesAsList()) == before + 1

    states.undoState(real_section, real_series)
    assert len(real_section.tracesAsList()) == before, (
        "the undo restored nothing, so this test is not exercising the rebind"
    )

    ## The rebind really did replace the trace objects: this is the state that
    ## used to leave `_column_rows` keyed on discarded traces.
    real_section._assertColumnsMatchObjectModel("after an undo")
    assert set(map(id, real_section._column_rows)) == {
        id(t) for t in real_section.tracesAsList()
    }

    ## The next real edit, which is what actually broke.
    real_section.addTrace(_aTrace(real_section, name="the_stroke_after_the_undo"))
    real_section.save()


def test_a_section_edited_after_a_redo_does_not_raise(real_section, real_series):
    """Same for `redoState`, which restores contour keys one at a time.

    Asserted on the store rather than on how much the redo restored: what this
    test owns is that the rebind leaves a consistent store and a section that
    accepts another edit. The fixture's redo happens to restore the pre-edit
    contours here, and pinning that number would make this test fail for
    reasons that have nothing to do with the dual write.
    """
    from PyReconstruct.modules.backend.func.state_manager import SectionStates

    states = SectionStates(real_section, real_series)

    states.addState(real_section, real_series)
    real_section.addTrace(_aTrace(real_section, name="redone_by_the_dual_write_test"))
    states.undoState(real_section, real_series)
    assert states.redo_states, "nothing to redo, so this test proves nothing"

    states.redoState(real_section, real_series)

    real_section._assertColumnsMatchObjectModel("after a redo")
    assert set(map(id, real_section._column_rows)) == {
        id(t) for t in real_section.tracesAsList()
    }
    real_section.addTrace(_aTrace(real_section, name="the_stroke_after_the_redo"))
    real_section.save()


def test_the_generation_counter_survives_a_rebuild(real_section):
    """A resync must not restart the counter at 0.

    `SectionColumns`' own docstring says the generation "is monotonic and is
    never reset by anything", because a cache stores the value it was built at
    and compares. A rebuild makes a NEW store, so without carrying the count
    forward an undo would hand every cache a generation below the one it holds
    and every cache would conclude it was current -- the stale-render bug class
    the counter exists to prevent, arriving through the repair. Unreachable
    under the gate, because nothing outside a test rebuilt a store; live now.
    """
    for _ in range(5):
        real_section.addTrace(_aTrace(real_section))
    before = real_section._columns.generation
    assert before > 0, "the setup did not move the counter at all"

    real_section.resyncColumnarStore()

    assert real_section._columns.generation >= before, (
        f"the rebuilt store restarted its generation at "
        f"{real_section._columns.generation}, below the {before} a cache may "
        "already hold"
    )
    ## And it keeps moving from there.
    real_section.addTrace(_aTrace(real_section))
    assert real_section._columns.generation > before


def test_the_whole_section_check_runs_on_save(real_section):
    """The coarse net's new home.

    Per-mutation checking is targeted at the row that moved and cannot see drift
    caused from outside the class. `save()` is the one non-per-frame path that
    is already O(section), so the whole-section comparison runs there -- one
    save cycle after any such drift at worst, rather than never.
    """
    trace = _anyTrace(real_section)
    real_section.contours[trace.name].remove(trace)  # out of class, no hook

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section.save()

    assert "save" in str(caught.value)


# =============================================================================
# Track C: a normal consumer can reach the store
# =============================================================================

def test_a_normal_consumer_reaches_a_live_store_on_every_section(real_series):
    """What the decision was made to unblock, checked as a consumer would.

    No environment set, no gate, nothing test-only: load the series the way any
    code in the application does and every section answers with a store that
    agrees with its contours. This is the precondition the first consumer flip
    (`svg_conversion.py`) found missing, and the whole reason D2 was reopened.

    Deliberately NOT flipping a consumer here -- that is separate work, and it
    is separately blocked on `SectionColumns.contourNames()` being sorted-only
    where `Section.contours` is insertion-ordered, which this change does not
    address and does not claim to.
    """
    from PyReconstruct.modules.datatypes.columnar_store import ContourView

    checked = 0
    for snum, section in real_series.enumerateSections(show_progress=False):
        store = section._columns
        assert store is not None, f"section {snum} has no store"
        assert len(store) == len(section.tracesAsList())

        for name in store.contourNames():
            view = ContourView(store, name)
            assert len(view) == len(section.contours[name])
            checked += 1

    assert checked > 0, "the fixture series produced no contour to read"


def test_the_store_ordering_mismatch_is_still_open_and_still_reproduces(
    real_section
):
    """The known, deliberately unfixed difference, pinned so it stays visible.

    `SectionColumns.contourNames()` is sorted; `Section.contours` is insertion
    ordered. The first attempted consumer flip found this and it is his call,
    not this change's -- so it is recorded as a live difference rather than
    quietly worked around. If somebody fixes it, this test fails and says why.
    """
    real_section.addTrace(_aTrace(real_section, name="aaa_added_last"))

    object_order = list(real_section.contours)
    store_order = real_section._columns.contourNames()

    assert object_order[-1] == "aaa_added_last"
    assert store_order[0] == "aaa_added_last"
    assert object_order != store_order, (
        "the store's contour ordering now matches the object model's, so the "
        "open ordering question was answered somewhere -- update the rewiring "
        "spec and delete this test"
    )


# =============================================================================
# The narrowing itself, pinned so that putting it back is a visible act
# =============================================================================
#
# Two places gave up whole-section checking when this became a production path,
# both because of the same measurement (`autoseg745`: a whole-section check is
# ~85 ms on the median section, ~129 ms on the busiest, against a 0.002 ms
# `addTrace`). Neither is a quiet loss: each is asserted here, so a change that
# restores the old scope turns these red and reopens the cost question with a
# reviewer looking at it.

def test_a_mutation_does_not_materialize_the_whole_section(real_section, monkeypatch):
    """The per-mutation check touches one row, not every row.

    `materializeContours` is the O(section) read; a single-row mutation must not
    reach it. This is the assertion that makes the per-mutation cost a property
    of the code rather than a claim in a comment.
    """
    calls = []
    real = SectionColumns.materializeContours

    def counted(self):
        calls.append(1)
        return real(self)

    monkeypatch.setattr(SectionColumns, "materializeContours", counted)

    trace = _aTrace(real_section)
    real_section.addTrace(trace)
    real_section.hideTraces([trace], hide=True)
    real_section.closeTraces([trace], closed=False)
    real_section.removeTrace(trace)

    assert calls == [], (
        f"{len(calls)} whole-section materializations for four single-row "
        "mutations; the per-mutation check went back to O(section)"
    )


def test_building_a_store_does_not_run_the_whole_section_comparison(
    real_series, monkeypatch
):
    """A store is built at every section load, so the build cannot be O(section)
    twice.

    `fromSection` copies values straight out of the object model, so the only
    divergence a build-time value comparison can find is a bug in the store's own
    encode/decode -- which does not vary section to section and which
    `test_columnar_store_parity.py` covers directly. Running it per load cost a
    measured 11x on section load and 8.2x on a full-series pass.
    """
    calls = []
    real = SectionColumns.materializeContours

    def counted(self):
        calls.append(1)
        return real(self)

    monkeypatch.setattr(SectionColumns, "materializeContours", counted)

    section = real_series.loadSection(sorted(real_series.sections)[0])
    assert section._columns is not None
    assert calls == [], "building a store materialized the whole section"


def test_building_a_store_still_checks_the_row_arity(real_section, monkeypatch):
    """What the build DOES still check, and why it is worth its O(contours).

    The row map is built by zipping each contour's traces against the rows the
    store reports for that contour. If those ever stop lining up -- a change to
    `fromSection`'s walk order, a contour index that drops a row -- every trace
    on the section is silently mapped to the wrong row, and every later check
    then compares the wrong pair. That is a per-section question, so it stays.
    """
    real = SectionColumns.rowsForContour

    def short(self, name):
        rows = real(self, name)
        return rows[:-1] if len(rows) > 1 else rows

    monkeypatch.setattr(SectionColumns, "rowsForContour", short)

    with pytest.raises(ColumnarDualWriteMismatch) as caught:
        real_section.resyncColumnarStore()

    assert "building the store" in str(caught.value)
