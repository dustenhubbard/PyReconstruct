"""Tests for invert-selection and object-level "hide unselected".

Motivation: proofreading a dense auto-seg ROI. An object spans many sections,
so the isolation a proofreader needs is OBJECT-level and VOLUME-wide: pick the
object(s) to work on and hide every other object throughout the whole series,
so it stays isolated as they page through sections -- without losing Ctrl+Z.

Two features are covered:

  * Invert selection
      - field / current section (traces): ``Section.invertTraceSelection`` and
        the ``FieldWidgetTrace`` wrapper -- flips the trace selection on the
        current section (a convenience; not undoable, like every selection op).
      - object list (objects): ``invert_object_rows`` -- the pure row-selection
        logic behind ``ObjectTableWidget.invertSelection``.

  * Hide unselected OBJECTS, volume-wide: ``FieldWidgetObject.hideUnselectedObjects``
    hides every non-selected object across ALL sections via the existing
    series-wide ``Series.hideObjects`` machinery, and ``unhideAllObjects``
    restores. The crux is exercised end-to-end on a real multi-section series
    (``shapes1.jser``, 4 objects on all 5 sections): the complement is hidden on
    every section and a single undo restores every section.

The section-only "hide unselected traces" that an earlier revision added was
removed: it would have collided (same label, different scope) with the
volume-wide object hide, which is what the feature actually needs.

``Section`` cannot be constructed without real series files, so the pure
section tests drive ``Section.__new__`` instances carrying only the attributes
the methods touch. The volume-wide tests load a real series from the shipped
``.jser`` and drive the real ``FieldWidgetObject`` method against it.
"""
import os
import types
import shutil

from PyReconstruct.modules.datatypes.trace import Trace
from PyReconstruct.modules.datatypes.contour import Contour
from PyReconstruct.modules.datatypes.section import Section
from PyReconstruct.modules.datatypes.default_settings import default_settings

from PyReconstruct.modules.gui.table.object import invert_object_rows
from PyReconstruct.modules.gui.main import field_widget_2_trace as fwt
from PyReconstruct.modules.gui.main import field_widget_3_object as fwo
from PyReconstruct.modules.gui.main.context_menu_list import (
    get_context_menu_list_trace,
    get_context_menu_list_obj,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHAPES1 = os.path.join(
    REPO_ROOT, "PyReconstruct", "assets", "checker", "files", "shapes1.jser"
)


# --------------------------------------------------------------------------- #
# helpers -- section-level (no Qt)
# --------------------------------------------------------------------------- #
def mk(name, hidden=False):
    """Build a Trace with explicit points (bypassing the GUI add path)."""
    t = Trace(name, (255, 0, 0), True)
    t.points = [(0, 0), (1, 0), (1, 1)]
    t.hidden = hidden
    return t


class _SeriesStub:
    """The minimal Series surface the section methods touch."""

    def __init__(self, locked_names=()):
        self.locked_names = set(locked_names)
        self.log = []

    def getAttr(self, name, attr):
        assert attr == "locked"
        return name in self.locked_names

    def addLog(self, *args):
        self.log.append(args)


def bare_section(traces, locked_names=()):
    s = Section.__new__(Section)
    s.n = 0
    s.series = _SeriesStub(locked_names)
    s.contours = {}
    for t in traces:
        if t.name not in s.contours:
            s.contours[t.name] = Contour(t.name)
        s.contours[t.name].append(t)
    s.selected_traces = []
    s.selected_ztraces = []
    s.selected_flags = []
    s.temp_hide = []
    s.traces_group_hide = []
    s.modified_contours = set()
    s.added_traces = []
    s.removed_traces = []
    return s


# --------------------------------------------------------------------------- #
# Section.invertTraceSelection (current-section trace invert; field convenience)
# --------------------------------------------------------------------------- #
def test_invert_flips_selected_and_unselected():
    a, b, c, d = mk("a"), mk("b"), mk("c"), mk("d")
    s = bare_section([a, b, c, d])
    s.selected_traces = [a, c]

    s.invertTraceSelection()

    assert set(s.selected_traces) == {b, d}


def test_invert_empty_selection_selects_all_visible():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])

    s.invertTraceSelection()

    assert set(s.selected_traces) == {a, b}


def test_invert_full_selection_deselects_all():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])
    s.selected_traces = [a, b]

    s.invertTraceSelection()

    assert s.selected_traces == []


def test_invert_twice_restores_original_selection():
    a, b, c = mk("a"), mk("b"), mk("c")
    s = bare_section([a, b, c])
    s.selected_traces = [b]

    s.invertTraceSelection()
    s.invertTraceSelection()

    assert set(s.selected_traces) == {b}


def test_invert_skips_hidden_traces_by_default():
    a, b, h = mk("a"), mk("b"), mk("h", hidden=True)
    s = bare_section([a, b, h])
    s.selected_traces = [a]

    s.invertTraceSelection()

    # h is invisible in the field, so it must not become selected
    assert set(s.selected_traces) == {b}


def test_invert_includes_hidden_traces_in_show_all_mode():
    a, b, h = mk("a"), mk("b"), mk("h", hidden=True)
    g = mk("g")
    s = bare_section([a, b, h, g])
    s.traces_group_hide = [g]  # hidden through group visibility
    s.selected_traces = [a]

    s.invertTraceSelection(include_hidden=True)

    # show-all mode displays hidden and group-hidden traces, so both count
    assert set(s.selected_traces) == {b, h, g}


def test_invert_skips_group_hidden_traces_by_default():
    a, b, g = mk("a"), mk("b"), mk("g")
    s = bare_section([a, b, g])
    s.traces_group_hide = [g]
    s.selected_traces = [a]

    s.invertTraceSelection()

    assert set(s.selected_traces) == {b}


def test_invert_never_selects_locked_objects():
    a, b, locked = mk("a"), mk("b"), mk("locked")
    s = bare_section([a, b, locked], locked_names={"locked"})
    s.selected_traces = [a]

    s.invertTraceSelection()

    # addSelectedTrace refuses locked objects, same as every other select path
    assert set(s.selected_traces) == {b}


def test_invert_leaves_ztrace_and_flag_selection_untouched():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])
    s.selected_traces = [a]
    s.selected_ztraces = ["zpoint"]
    s.selected_flags = ["flag"]

    s.invertTraceSelection()

    assert s.selected_ztraces == ["zpoint"]
    assert s.selected_flags == ["flag"]


# --------------------------------------------------------------------------- #
# FieldWidgetTrace.invertTraceSelection wrapper (duck-typed stubs, no Qt loop)
# --------------------------------------------------------------------------- #
def test_field_invert_is_disabled_while_trace_layer_hidden():
    a = mk("a")
    s = bare_section([a])
    stub = types.SimpleNamespace(
        hide_trace_layer=True,
        show_all_traces=False,
        section=s,
        generateView=lambda *a_, **k: None,
    )

    fwt.FieldWidgetTrace.invertTraceSelection(stub)

    assert s.selected_traces == []  # would have selected "a" otherwise


def test_field_invert_selects_complement_and_regenerates_view():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])
    s.selected_traces = [a]
    views = []
    stub = types.SimpleNamespace(
        hide_trace_layer=False,
        show_all_traces=False,
        section=s,
        generateView=lambda *a_, **k: views.append(k),
    )

    fwt.FieldWidgetTrace.invertTraceSelection(stub)

    assert s.selected_traces == [b]
    assert views  # the field redraws


def test_field_invert_passes_show_all_mode_through():
    a, h = mk("a"), mk("h", hidden=True)
    s = bare_section([a, h])
    s.selected_traces = [a]
    stub = types.SimpleNamespace(
        hide_trace_layer=False,
        show_all_traces=True,
        section=s,
        generateView=lambda *a_, **k: None,
    )

    fwt.FieldWidgetTrace.invertTraceSelection(stub)

    assert s.selected_traces == [h]


# --------------------------------------------------------------------------- #
# invert_object_rows -- pure logic behind ObjectTableWidget.invertSelection
# --------------------------------------------------------------------------- #
def test_object_invert_returns_the_unselected_rows():
    rows = ["a", "b", "c", "d"]
    assert invert_object_rows(rows, {"a", "c"}, set()) == [1, 3]


def test_object_invert_empty_selection_selects_every_row():
    rows = ["a", "b", "c"]
    assert invert_object_rows(rows, set(), set()) == [0, 1, 2]


def test_object_invert_all_selected_selects_nothing():
    rows = ["a", "b"]
    assert invert_object_rows(rows, {"a", "b"}, set()) == []


def test_object_invert_never_selects_locked_rows():
    rows = ["a", "b", "c", "d"]
    # b unselected but locked -> excluded; d selected+locked -> stays out anyway
    assert invert_object_rows(rows, {"c", "d"}, {"b", "d"}) == [0]


def test_object_invert_double_invert_returns_to_start_without_locks():
    rows = ["a", "b", "c", "d"]
    selected = {"b"}
    first = set(rows[i] for i in invert_object_rows(rows, selected, set()))
    second = set(rows[i] for i in invert_object_rows(rows, first, set()))
    assert second == selected


# --------------------------------------------------------------------------- #
# FieldWidgetObject.hideUnselectedObjects / unhideAllObjects (recording stubs)
# --------------------------------------------------------------------------- #
class _FakeSeries:
    """Records hideObjects calls; enough surface for the object field methods."""

    def __init__(self, objects, locked=()):
        self.data = {"objects": {n: object() for n in objects}}
        self.locked = set(locked)
        self.hide_calls = []

    def getAttr(self, name, attr):
        assert attr == "locked"
        return name in self.locked

    def hideObjects(self, names, hide, series_states=None, log_event=True):
        self.hide_calls.append((sorted(names), hide))


def _obj_field_stub(series, selected_names, series_states="STATES"):
    """A stub FieldWidgetObject good enough for object_function + the methods.

    hasFocus() returns None so the decorator resolves the object names from the
    field's selected traces (the field entry point). The object-list entry
    point -- getSelected() -- is exercised end-to-end by the offscreen driver.
    """
    events = []
    stub = types.SimpleNamespace(
        series=series,
        series_states=series_states,
        section=types.SimpleNamespace(
            selected_traces=[types.SimpleNamespace(name=n) for n in selected_names]
        ),
        table_manager=types.SimpleNamespace(
            hasFocus=lambda: None,
            updateObjects=lambda names: events.append(("updateObjects", sorted(names))),
        ),
        mainwindow=types.SimpleNamespace(
            saveAllData=lambda: events.append("saveAllData"),
            seriesModified=lambda *a: events.append("seriesModified"),
        ),
        reload=lambda: events.append("reload"),
    )
    return stub, events


def test_hide_unselected_objects_hides_complement_excluding_locked():
    series = _FakeSeries(["a", "b", "c", "d"], locked={"d"})
    stub, events = _obj_field_stub(series, ["a"])

    fwo.FieldWidgetObject.hideUnselectedObjects(stub)

    # keep a; d is locked -> left visible; b + c hidden volume-wide
    assert series.hide_calls == [(["b", "c"], True)]
    assert "reload" in events
    assert ("updateObjects", ["b", "c"]) in events


def test_hide_unselected_objects_empty_selection_is_a_noop():
    series = _FakeSeries(["a", "b"])
    stub, events = _obj_field_stub(series, [])  # nothing selected

    fwo.FieldWidgetObject.hideUnselectedObjects(stub)

    # the decorator bails before the body -> series never blanked
    assert series.hide_calls == []
    assert "reload" not in events


def test_hide_unselected_objects_everything_selected_is_a_noop():
    series = _FakeSeries(["a", "b"])
    stub, events = _obj_field_stub(series, ["a", "b"])

    fwo.FieldWidgetObject.hideUnselectedObjects(stub)

    assert series.hide_calls == []       # complement empty -> nothing hidden
    assert "reload" not in events


def test_hide_unselected_objects_when_only_locked_remain_is_a_noop():
    series = _FakeSeries(["a", "b", "c"], locked={"b", "c"})
    stub, events = _obj_field_stub(series, ["a"])

    fwo.FieldWidgetObject.hideUnselectedObjects(stub)

    # the only unselected objects are locked -> nothing to hide
    assert series.hide_calls == []
    assert "reload" not in events


def test_unhide_all_objects_unhides_every_object():
    series = _FakeSeries(["a", "b", "c"])
    stub, events = _obj_field_stub(series, [])  # selection irrelevant

    fwo.FieldWidgetObject.unhideAllObjects(stub)

    assert series.hide_calls == [(["a", "b", "c"], False)]
    assert "reload" in events


def test_unhide_all_objects_on_empty_series_does_nothing():
    series = _FakeSeries([])
    stub, events = _obj_field_stub(series, [])

    fwo.FieldWidgetObject.unhideAllObjects(stub)

    assert series.hide_calls == []
    assert "reload" not in events


# --------------------------------------------------------------------------- #
# CRUX: volume-wide hide + undo on a REAL multi-section series
# --------------------------------------------------------------------------- #
from PyReconstruct.modules.datatypes import Series
from PyReconstruct.modules.backend.func.state_manager import SeriesStates


def _open_shapes(tmp_path):
    dst = os.path.join(str(tmp_path), "shapes1.jser")
    shutil.copy(SHAPES1, dst)
    return Series.openJser(dst)


def _hidden_by_section(series, name):
    """{section number: are ALL of this object's traces hidden there}."""
    res = {}
    for snum in sorted(series.sections):
        sec = series.loadSection(snum)
        if name in sec.contours:
            res[snum] = all(t.hidden for t in sec.contours[name])
    return res


def _real_field_stub(series, states, selected_names):
    return types.SimpleNamespace(
        series=series,
        series_states=states,
        section=types.SimpleNamespace(
            selected_traces=[types.SimpleNamespace(name=n) for n in selected_names]
        ),
        table_manager=types.SimpleNamespace(
            hasFocus=lambda: None,
            updateObjects=lambda names: None,
        ),
        mainwindow=types.SimpleNamespace(
            saveAllData=lambda: None,
            seriesModified=lambda *a: None,
        ),
        reload=lambda: None,
    )


def test_fixture_objects_really_span_multiple_sections(tmp_path):
    # guards the crux: if the fixture ever became single-section this whole
    # proof would be vacuous.
    series = _open_shapes(tmp_path)
    assert len(series.sections) >= 3
    for name in series.data["objects"]:
        present = _hidden_by_section(series, name)
        assert len(present) >= 3, f"{name} only on sections {list(present)}"


def test_hide_unselected_objects_persists_across_every_section(tmp_path):
    series = _open_shapes(tmp_path)
    all_names = set(series.data["objects"].keys())
    keep = "star"
    assert keep in all_names

    states = SeriesStates(series)
    stub = _real_field_stub(series, states, [keep])

    fwo.FieldWidgetObject.hideUnselectedObjects(stub)

    for name in all_names:
        hidden = _hidden_by_section(series, name)
        if name == keep:
            assert all(v is False for v in hidden.values()), \
                f"kept object {name} was hidden: {hidden}"
        else:
            assert hidden and all(v is True for v in hidden.values()), \
                f"{name} not hidden on every section: {hidden}"


def test_single_undo_restores_hidden_on_every_section(tmp_path):
    series = _open_shapes(tmp_path)
    states = SeriesStates(series)
    stub = _real_field_stub(series, states, ["star"])

    fwo.FieldWidgetObject.hideUnselectedObjects(stub)
    # sanity: something really was hidden across the volume
    assert any(
        all(v is True for v in _hidden_by_section(series, n).values())
        for n in series.data["objects"] if n != "star"
    )

    states.undoState()  # the Ctrl+Z path for a series-wide action

    for name in series.data["objects"]:
        hidden = _hidden_by_section(series, name)
        assert all(v is False for v in hidden.values()), \
            f"{name} still hidden on some section after undo: {hidden}"


def test_redo_reapplies_the_volume_wide_hide(tmp_path):
    series = _open_shapes(tmp_path)
    states = SeriesStates(series)
    stub = _real_field_stub(series, states, ["star"])

    fwo.FieldWidgetObject.hideUnselectedObjects(stub)
    states.undoState()
    states.undoState(redo=True)

    # after redo everything but star is hidden again, on every section
    for name in series.data["objects"]:
        hidden = _hidden_by_section(series, name)
        expect = name != "star"
        assert all(v is expect for v in hidden.values()), \
            f"{name} redo state wrong: {hidden}"


# --------------------------------------------------------------------------- #
# wiring: menus and dropped shortcut
# --------------------------------------------------------------------------- #
class _ObjMenuStub:
    def __init__(self):
        self.series = types.SimpleNamespace(
            user_columns={}, alignments=set(), groups_visibility={}
        )

    def __getattr__(self, name):
        return lambda *a, **k: None


def _act_names(menu):
    """Flatten a menu-list structure into its action names, in order."""
    names = []
    for entry in menu:
        if isinstance(entry, tuple):
            names.append(entry[0])
        elif isinstance(entry, dict):
            names.extend(_act_names(entry["opts"]))
    return names


def test_trace_menu_no_longer_offers_hide_unselected():
    class _Stub:
        series = object()

        def __getattr__(self, name):
            return lambda *a, **k: None

    names = _act_names(get_context_menu_list_trace(_Stub(), is_in_field=True))
    assert "hideunselected_act" not in names   # the section-level version is gone
    assert "hidetraces_act" in names           # ordinary Hide stays


def test_object_menu_offers_hide_unselected_and_show_all_next_to_hide():
    names = _act_names(get_context_menu_list_obj(_ObjMenuStub()))
    assert "hideunselectedobj_act" in names
    assert "showallobj_act" in names
    # placed right after the existing object Hide/Unhide pair
    assert names.index("hideunselectedobj_act") == names.index("unhideobj_act") + 1
    assert names.index("showallobj_act") == names.index("hideunselectedobj_act") + 1


def test_dropped_shortcut_removed_and_field_invert_kept():
    # the section-level "hide unselected traces" shortcut is gone...
    assert "hideunselected_act" not in default_settings
    # ...while the field trace-invert convenience keeps its shortcut
    assert default_settings["invertselection_act"] == "Ctrl+Shift+I"


def test_no_shortcut_collisions_remain():
    acts = {k: v for k, v in default_settings.items()
            if k.endswith("_act") and isinstance(v, str)}
    clashes = [k for k, v in acts.items()
               if v == acts["invertselection_act"] and k != "invertselection_act"]
    assert not clashes, f"invertselection_act collides with {clashes}"
