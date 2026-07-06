"""Tests for invert-selection and hide-unselected (show-only-selected).

Motivation: proofreading a dense auto-seg ROI — isolate one or a few objects
and push the rest out of the way, without losing Ctrl+Z.

Covered here:

  * ``Section.invertTraceSelection`` — complement semantics; hidden,
    group-hidden and locked traces; empty and full selections; ztrace/flag
    selections untouched.
  * ``Section.hideUnselectedTraces`` — hides exactly the complement, keeps
    the working set selected, skips already-hidden traces, and never hides
    everything on an empty selection.
  * A real undo round-trip through ``SectionStates`` (the same machinery
    ``FieldWidget.saveState()`` / ``undoState()`` drives for Ctrl+Z), so the
    undo behavior is exercised, not assumed.
  * The ``FieldWidgetTrace`` wrappers driven on duck-typed stubs (no Qt event
    loop or MainWindow needed): the hidden-trace-layer guard, saveState
    recording via the trace_function/field_interaction decorators, and the
    empty-selection no-op.
  * Wiring: the new actions have registered, non-colliding default shortcuts
    and appear in the trace context menu.

``Section`` cannot be constructed without real series files (its __init__
reads them from disk), so bare ``Section.__new__`` instances carry only the
attributes the methods under test touch.
"""
import types

from PyReconstruct.modules.datatypes.trace import Trace
from PyReconstruct.modules.datatypes.contour import Contour
from PyReconstruct.modules.datatypes.section import Section
from PyReconstruct.modules.datatypes.default_settings import default_settings
from PyReconstruct.modules.backend.func.state_manager import SectionStates


# --------------------------------------------------------------------------- #
# helpers
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
# Section.invertTraceSelection
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
# Section.hideUnselectedTraces
# --------------------------------------------------------------------------- #
def test_hide_unselected_hides_exactly_the_complement():
    a, b, c, d = mk("a"), mk("b"), mk("c"), mk("d")
    s = bare_section([a, b, c, d])
    s.selected_traces = [a, c]

    modified = s.hideUnselectedTraces()

    assert modified is True
    assert [t.hidden for t in (a, b, c, d)] == [False, True, False, True]
    # the working set stays selected
    assert set(s.selected_traces) == {a, c}
    # only the newly hidden contours are marked modified / logged
    assert s.modified_contours == {"b", "d"}
    assert len(s.series.log) == 2


def test_hide_unselected_with_empty_selection_never_hides_everything():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])

    modified = s.hideUnselectedTraces()

    assert modified is False
    assert not a.hidden and not b.hidden
    assert s.modified_contours == set()


def test_hide_unselected_with_everything_selected_is_a_noop():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])
    s.selected_traces = [a, b]

    modified = s.hideUnselectedTraces()

    assert modified is False
    assert not a.hidden and not b.hidden
    assert set(s.selected_traces) == {a, b}


def test_hide_unselected_skips_already_hidden_traces():
    a, b, h = mk("a"), mk("b"), mk("h", hidden=True)
    s = bare_section([a, b, h])
    s.selected_traces = [a]

    modified = s.hideUnselectedTraces()

    assert modified is True
    assert b.hidden and h.hidden
    # h was already hidden: not re-marked, not re-logged
    assert s.modified_contours == {"b"}
    assert len(s.series.log) == 1


def test_hide_unselected_accepts_explicit_traces():
    # the trace-list path: the kept traces come from the table selection,
    # not from the field selection
    a, b, c = mk("a"), mk("b"), mk("c")
    s = bare_section([a, b, c])
    s.selected_traces = [c]  # field selection differs from the table's

    modified = s.hideUnselectedTraces(traces=[a])

    assert modified is True
    assert [t.hidden for t in (a, b, c)] == [False, True, True]
    # c became hidden, so it must not stay selected (hidden-but-selected
    # traces are the bug class later operations trip over)
    assert s.selected_traces == []


# --------------------------------------------------------------------------- #
# Undo: real SectionStates round-trip (the Ctrl+Z machinery)
# --------------------------------------------------------------------------- #
def _undoable_section(tmp_path, traces):
    s = bare_section(traces)
    s.tforms = {}
    s.tforms_values_copy = []
    s.flags = []
    series = s.series
    series.hidden_dir = str(tmp_path)
    series.sections = {0: "series.0"}
    series.ztraces = {}
    series.modified_ztraces = set()
    return s, series


def test_undo_restores_hidden_flags_after_hide_unselected(tmp_path):
    a, b, pre_hidden = mk("a"), mk("b"), mk("c", hidden=True)
    s, series = _undoable_section(tmp_path, [a, b, pre_hidden])
    s.selected_traces = [a]

    states = SectionStates(s, series)  # pristine snapshot, as on section load
    before = {name: [t.hidden for t in contour]
              for name, contour in s.contours.items()}

    assert s.hideUnselectedTraces() is True
    states.addState(s, series)  # what FieldWidget.saveState() does

    hidden_now = {t.name: t.hidden for t in s.tracesAsList()}
    assert hidden_now == {"a": False, "b": True, "c": True}

    states.undoState(s, series)  # what FieldWidget.undoState() does

    after = {name: [t.hidden for t in contour]
             for name, contour in s.contours.items()}
    # b is visible again; the pre-hidden trace stays hidden
    assert after == before


def test_redo_reapplies_hide_unselected(tmp_path):
    a, b = mk("a"), mk("b")
    s, series = _undoable_section(tmp_path, [a, b])
    s.selected_traces = [a]

    states = SectionStates(s, series)
    s.hideUnselectedTraces()
    states.addState(s, series)
    states.undoState(s, series)
    assert {t.name: t.hidden for t in s.tracesAsList()} == {"a": False, "b": False}

    states.redoState(s, series)
    assert {t.name: t.hidden for t in s.tracesAsList()} == {"a": False, "b": True}


# --------------------------------------------------------------------------- #
# FieldWidgetTrace wrappers (duck-typed stubs, no Qt event loop)
# --------------------------------------------------------------------------- #
from PyReconstruct.modules.gui.main import field_widget_2_trace as fwt


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


def _field_stub(section, selected):
    """A stub FieldWidget good enough for trace_function/field_interaction."""
    section.selected_traces = list(selected)
    events = []
    stub = types.SimpleNamespace(
        section=section,
        series=section.series,
        hide_trace_layer=False,
        table_manager=types.SimpleNamespace(hasFocus=lambda: None),
        mainwindow=types.SimpleNamespace(
            saveAllData=lambda: events.append("saveAllData")
        ),
        saveState=lambda: events.append("saveState"),
        generateView=lambda *a_, **k: events.append("generateView"),
    )
    return stub, events


def test_field_hide_unselected_records_an_undo_state():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])
    stub, events = _field_stub(s, [a])

    fwt.FieldWidgetTrace.hideUnselectedTraces(stub)

    assert b.hidden and not a.hidden
    # the decorators recorded the undo state and redrew, same as Hide (Ctrl+H)
    assert "saveState" in events
    assert "generateView" in events


def test_field_hide_unselected_with_empty_selection_is_a_silent_noop():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])
    stub, events = _field_stub(s, [])

    fwt.FieldWidgetTrace.hideUnselectedTraces(stub)

    assert not a.hidden and not b.hidden
    assert "saveState" not in events  # no phantom undo state


def test_field_hide_unselected_is_disabled_while_trace_layer_hidden():
    a, b = mk("a"), mk("b")
    s = bare_section([a, b])
    stub, events = _field_stub(s, [a])
    stub.hide_trace_layer = True

    fwt.FieldWidgetTrace.hideUnselectedTraces(stub)

    assert not b.hidden
    assert "saveState" not in events


# --------------------------------------------------------------------------- #
# wiring: shortcuts and context menu
# --------------------------------------------------------------------------- #
from PyReconstruct.modules.gui.main.context_menu_list import (
    get_context_menu_list_trace,
)


def test_new_actions_have_registered_default_shortcuts():
    assert default_settings["invertselection_act"] == "Ctrl+Shift+I"
    assert default_settings["hideunselected_act"] == "Shift+H"


def test_new_shortcuts_do_not_collide_with_existing_ones():
    acts = {k: v for k, v in default_settings.items()
            if k.endswith("_act") and isinstance(v, str)}
    for key in ("invertselection_act", "hideunselected_act"):
        clashes = [k for k, v in acts.items() if v == acts[key] and k != key]
        assert not clashes, f"{key} ({acts[key]}) collides with {clashes}"


def test_trace_context_menu_offers_hide_unselected_next_to_hide():
    class _Stub:
        series = object()

        def __getattr__(self, name):
            return lambda *a, **k: None

    menu = get_context_menu_list_trace(_Stub(), is_in_field=True)
    names = [entry[0] for entry in menu if isinstance(entry, tuple)]

    assert "hideunselected_act" in names
    assert names.index("hideunselected_act") == names.index("hidetraces_act") + 1
