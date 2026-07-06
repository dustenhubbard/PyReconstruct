"""SPIKE test for issue #72 — restrict the working view to a spatial region.

Exercises the real trace-visibility gate (TraceLayer.trace_visibile_p) and the
traceInRegion helper against a field-coordinate region bbox, using lightweight
fakes for the Section so no GUI, image, or .jser file is required.

The spike restricts the view WITHOUT mutating persistent Trace.hidden, so
clearing the restriction must bring every trace back. These tests pin that
contract, the interaction of the restriction with the existing show_all_traces
override, and the temp_hide precedence.
"""

import pytest

from PyReconstruct.modules.backend.view.trace_layer import (
    TraceLayer,
    traceInRegion,
)
from PyReconstruct.modules.datatypes import Trace, Transform


class FakeSection:
    """Minimal stand-in exposing only what trace_visibile_p reads."""

    def __init__(self):
        self.temp_hide = []
        self.traces_group_hide = []
        self.tform = Transform.identity()


def make_trace(name, x0, y0, x1, y1, hidden=False):
    """A closed rectangular trace spanning (x0,y0)-(x1,y1) in field coords."""
    t = Trace(name, (255, 0, 0))
    t.points = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    t.hidden = hidden
    return t


def make_layer(region=None, show_all=False, section=None):
    """A TraceLayer with just the attributes the visibility gate touches."""
    layer = object.__new__(TraceLayer)  # bypass heavy __init__
    layer.section = section if section is not None else FakeSection()
    layer.show_all_traces = show_all
    layer.region_restriction = region
    return layer


# --- the pure helper --------------------------------------------------------

def test_traceInRegion_overlap_and_disjoint():
    tform = Transform.identity()
    inside = make_trace("inside", 1, 1, 3, 3)
    outside = make_trace("outside", 20, 20, 25, 25)
    region = (0, 0, 10, 10)

    assert traceInRegion(inside, region, tform) is True
    assert traceInRegion(outside, region, tform) is False


def test_traceInRegion_partial_overlap_counts_as_inside():
    tform = Transform.identity()
    straddling = make_trace("straddle", 8, 8, 15, 15)  # crosses the edge
    region = (0, 0, 10, 10)
    assert traceInRegion(straddling, region, tform) is True


# --- the visibility gate ----------------------------------------------------

def test_no_restriction_shows_everything():
    layer = make_layer(region=None)
    far = make_trace("far", 100, 100, 110, 110)
    assert layer.trace_visibile_p(far) is True


def test_restriction_hides_outside_shows_inside():
    layer = make_layer(region=(0, 0, 10, 10))
    inside = make_trace("inside", 1, 1, 3, 3)
    outside = make_trace("outside", 50, 50, 60, 60)

    assert layer.trace_visibile_p(inside) is True
    assert layer.trace_visibile_p(outside) is False


def test_clearing_restriction_brings_back_outside_trace():
    """The 'bring back' contract: clearing the region restores hidden traces
    without any change to Trace.hidden."""
    outside = make_trace("outside", 50, 50, 60, 60)

    layer = make_layer(region=(0, 0, 10, 10))
    assert layer.trace_visibile_p(outside) is False
    assert outside.hidden is False  # persistent state untouched

    layer.region_restriction = None  # what clearRegionRestriction() does
    assert layer.trace_visibile_p(outside) is True
    assert outside.hidden is False


def test_show_all_traces_overrides_region_restriction():
    layer = make_layer(region=(0, 0, 10, 10), show_all=True)
    outside = make_trace("outside", 50, 50, 60, 60)
    assert layer.trace_visibile_p(outside) is True


def test_temp_hide_beats_region_restriction():
    section = FakeSection()
    inside = make_trace("inside", 1, 1, 3, 3)
    section.temp_hide = [inside]
    layer = make_layer(region=(0, 0, 10, 10), section=section)
    # inside the region, but dragging -> still hidden
    assert layer.trace_visibile_p(inside) is False


def test_persistently_hidden_trace_stays_hidden_inside_region():
    layer = make_layer(region=(0, 0, 10, 10))
    hidden_inside = make_trace("h", 1, 1, 3, 3, hidden=True)
    assert layer.trace_visibile_p(hidden_inside) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
