"""What the import's overlap test asks of an OPEN trace pair, before and after.

``Trace.getOverlapRatio`` answers differently for a pair where BOTH traces are
open (the dispatch is ``not self.closed and not other.closed``):

  * before: intersection-over-union of the two rasterized regions bounded by each
    polyline AND its own closing chord. This is what the import dialog's tooltip
    used to describe as "the Jaccard index ... the intersection of the two traces
    divided by their union". For a near-straight open trace that region is
    degenerate, so the ratio is 0 however close the two curves lie.
  * after: the fraction of each curve lying within ``d`` of the other, minimised
    over the two directions, where

        d = clamp(OPEN_TRACE_MATCH_FRACTION * min(arc length),
                  OPEN_TRACE_MATCH_MIN_PIXELS * mag,
                  OPEN_TRACE_MATCH_MAX_PIXELS * mag)

    A distance test, and no longer a Jaccard index of anything -- which is why
    ``dialog/import_series.py`` and ``dialog/malformed_contours.py`` no longer say
    it is one.

Three production call sites ask an overlap question during a merge, and at all
three **True is the destructive answer and False is the conservative one**:

  1. ``Contour.importTraces``, both ``overlaps(threshold)`` calls (the optimistic
     prefix loop and the remainder scan). True means ``addDuplicate``: the tags are
     merged, ``keep_above`` picks one survivor, and the other person's tracing is
     dropped from the contour and from both conflict pools -- so no
     ``import-conflict`` flag is raised and no log entry is written. False means
     both tracings land in the conflict pools and survive, flagged for a human.
     **This is the mainline path**: it runs on every import, at the dialog's own
     threshold, which defaults to 0.95 and cannot be set below 0.9 (the slider maps
     0-100 onto [0.9, 1.0] in ``dialog/import_series.py``).
  2. ``Section.tracesWithoutCounterpart`` (``threshold=0``) -- a donor trace that
     overlaps nothing is an orphan, and an orphan makes the history shortcut back
     off. A donor trace that overlaps something loses that protection. Live by
     default: "check series histories" is on.
  3. ``Section.importTraces``'s ``keep_below`` loop (``threshold=0``) -- an
     unfavoured conflict trace that overlaps a favoured one is deleted (recorded).
     Not live by default: ``keep_below`` defaults to "".

The destructive direction is therefore old-False -> new-True. **The bounds on d
are what keep it out of reach at the mainline path**: two curves further apart
than the tolerance under which this codebase already calls two points identical
(``POINTS_MATCH_TOLERANCE``, 4.89 px here) score 0, not 1. Without the ceiling the
tolerance is 2% of arc length, which is 137 px on the 95th-percentile trace in the
reporting user's series, and any pair inside that scores exactly 1.0 -- collapsed
at every threshold the dialog can produce, 1.0 included. Both directions are
measured below rather than assumed.

**What the bounds do not fix, and it is deliberate that this file says so.** At
``threshold=0`` the predicate is ``r > 0``, and two open traces that cross or
touch score a small positive ratio at any positive tolerance. Shrinking d shrinks
the ratio and cannot zero it. Section 4 pins that, and the one ratchet in this
file that does not pass is the one that asks for it.

Every "before" number here comes from ``areaRatio``, which runs the same points
through the closed branch of this tree. That branch is byte-identical to
``origin/main``'s ``getOverlapRatio`` -- the only change is the dispatch added
above it -- and the values were cross-checked against a real ``origin/main``
c85d701c checkout (0.0 for every near-straight pair; 0.133492 and 0.005009 for the
wiggly pair at separations 0.06 and 0.1; 0.152686 / 0.0 / 1.0 / 0.007042 for the
four closed controls).

Scale, from the real series these numbers are quoted against (mag 0.00204508
um/px): 3,974 open traces, median arc length 0.2517 series units = 123 image px,
median 4 points, 695 of them with exactly 2 points -- and ``Section.__init__``
forces every 2-point trace open. 78% are shorter than 250 px, which is where the
fraction stops binding and the 5 px ceiling takes over.
"""
import numpy as np
import pytest

from PyReconstruct.modules.datatypes.contour import Contour
from PyReconstruct.modules.datatypes.log import LogSet, LogSetPair
from PyReconstruct.modules.datatypes.section import (
    Section,
    tracesWithoutCounterpart,
)
from PyReconstruct.modules.datatypes.trace import Trace


MAG = 0.00204508      # um/px, the series these numbers are quoted for
IMPORT_DEFAULT = 0.95  # dialog/import_series.py: slider 50 over [0.9, 1.0]
IMPORT_FLOOR = 0.9     # the lowest value the import slider can produce
IMPORT_RANGE = (IMPORT_FLOOR, 0.92, IMPORT_DEFAULT, 0.99, 0.999, 1.0)

SQ = [(0, 0), (1, 0), (1, 1), (0, 1)]


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #
def mkOpen(points, name="membrane", tag=None):
    t = Trace(name, (0, 200, 0), closed=False)
    t.points = [(float(x), float(y)) for x, y in points]
    if tag:
        t.addTag(tag)
    return t


def mkClosed(points, name="blob"):
    t = Trace(name, (200, 0, 0), closed=True)
    t.points = [(float(x), float(y)) for x, y in points]
    return t


def areaRatio(a, b):
    """The ratio ``origin/main`` measures for this OPEN pair.

    Runs the identical points through the closed branch, which is what
    ``origin/main`` runs unconditionally. See the module docstring for the
    cross-check against a real c85d701c checkout.
    """
    ca, cb = a.copy(), b.copy()
    ca.closed = cb.closed = True
    return float(ca.getOverlapRatio(cb))


def mainOverlaps(a, b, threshold):
    """``a.overlaps(b, threshold)`` as ``origin/main`` answers it."""
    if a.closed != b.closed:
        return False
    if a.pointsMatch(b):
        return True
    return Trace.ratioIsOverlap(areaRatio(a, b), threshold)


def arcLength(points):
    p = np.asarray(points, dtype=float)
    return float(np.hypot(np.diff(p[:, 0]), np.diff(p[:, 1])).sum())


def tolerance(a, b, mag=MAG):
    """d, the bounded tolerance the two curves are compared against."""
    return Trace.openCurveTolerance(
        mag, arcLength(a.points), arcLength(b.points)
    )


def px(series_units):
    return series_units / MAG


def units(image_px):
    return image_px * MAG


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
LONG = 2.0        # series units: a long open trace (978 image px)
TYPICAL = 0.25171  # the median real open trace (123 image px)
BIG = 14.0        # the 95th percentile real open trace (6846 image px)


def straight(length, y, n):
    return [(x, y) for x in np.linspace(0.0, length, n)]


def wiggly(y0, freq, n=61, length=2.0, amp=0.10, wig=0.008):
    xs = np.linspace(0.0, length, n)
    ys = y0 + amp * np.sin(np.pi * xs / length) + wig * np.sin(freq * xs)
    return list(zip(xs, ys))


def smoothCurve(n=201, length=2.0, amp=0.15):
    xs = np.linspace(0.0, length, n)
    return list(zip(xs, amp * np.sin(np.pi * xs / length)))


def withDetour(points, frac, deviation):
    """The same curve retraced with one localized detour.

    Two people tracing one membrane disagree locally: one of them goes around a
    vesicle, or clicks through a blurred stretch differently. ``frac`` is how much
    of the length the disagreement covers, ``deviation`` its peak size.
    """
    p = np.asarray(points, dtype=float).copy()
    n = len(p)
    lo, hi = int(n * (0.5 - frac / 2)), int(n * (0.5 + frac / 2))
    w = hi - lo
    p[lo:hi, 1] += deviation * np.sin(np.pi * np.arange(w) / w)
    return [tuple(q) for q in p]


# --------------------------------------------------------------------------- #
# harness: Section.__init__ reads a section file, so -- as
# tests/test_import_silent_loss.py already does -- the real method bodies run on a
# Section.__new__ instance carrying only the collaborators importTraces touches.
# --------------------------------------------------------------------------- #
class _Series:
    def __init__(self):
        self.user = "tester"      # a stand-in object, never a real Series: see
        self.logs = []            # the QSettings rule about series.user
        self.object_groups = None

    def addLog(self, obj_name, snum, event):
        self.logs.append((obj_name, snum, event))

    def getAttr(self, *args, **kwargs):
        return None


def mkSection(contours, snum=2, mag=MAG):
    sec = Section.__new__(Section)
    sec.n = snum
    sec.mag = mag
    sec.contours = dict(contours)
    sec.flags = []
    sec.modified_contours = set()
    sec.series = _Series()
    sec.save = lambda *a, **k: None
    return sec


def mkHistories(self_events, other_events, shared=1):
    def fmt(obj_name, section, event):
        snum = "-" if section is None else str(section)
        return f"26-01-01, 0900, u, {obj_name}, {snum}, {event}"

    prefix = [fmt("seed", 1, f"Modify trace(s) {i}") for i in range(shared)]
    ls0 = LogSet.fromList(prefix + [fmt(*e) for e in self_events])
    ls1 = LogSet.fromList(prefix + [fmt(*e) for e in other_events])
    pair = LogSetPair(ls0, ls1)
    assert pair.last_shared_index == shared - 1
    assert not pair.complete_match
    return pair


def flagNames(section):
    return [f.name for f in section.flags]


def runContourImport(mine, theirs, threshold, cname="membrane", mag=MAG):
    """Drive Contour.importTraces, the mainline import path.

        Returns:
            (tuple): the surviving traces, and the two conflict pools
    """
    ours = Contour(cname, list(mine))
    other = Contour(cname, list(theirs))
    pool_s, pool_o = ours.importTraces(other, threshold, keep_above="self", mag=mag)
    return [t for t in ours], pool_s, pool_o


def runSectionImport(mine, theirs, threshold, cname="membrane", **kwargs):
    """Drive Section.importTraces end to end (no histories, no keep_below)."""
    sec = mkSection({cname: Contour(cname, list(mine))})
    other = mkSection({cname: Contour(cname, list(theirs))})
    sec.importTraces(other, threshold=threshold, flag_conflicts=True, **kwargs)
    return sec, [t for t in sec.contours.get(cname, [])]


def runHistoryShortcut(keeper_traces, donor_traces, cname="membrane"):
    """Drive the (True, False) history branch, whose gate is threshold=0.

    ``modified_since_diverge == (True, False)`` makes ``take_other`` False, so the
    keeper is self's contour and the donor is other's. With no removal recorded on
    self's side, ``deliberate`` is False, so the shortcut is declined if and only
    if the donor holds at least one orphan.
    """
    sec = mkSection({cname: Contour(cname, list(keeper_traces))})
    other = mkSection({cname: Contour(cname, list(donor_traces))})
    histories = mkHistories(
        self_events=[(cname, 2, "Modify trace(s)")],
        other_events=[("something_else", 1, "Modify trace(s)")],
    )
    assert histories.getModifiedSinceDiverge(cname, 2) == (True, False), (
        "premise: only self's log mentions this contour after the divergence"
    )
    sec.importTraces(other, threshold=IMPORT_DEFAULT, histories=histories,
                     flag_conflicts=True)
    surviving = [t for t in sec.contours.get(cname, [])]
    return sec, [t for t in surviving if any(t is d for d in donor_traces)]


def runKeepBelow(favoured, unfavoured, cname="membrane"):
    """Drive the keep_below='self' policy loop, the other threshold=0 gate."""
    sec = mkSection({cname: Contour(cname, list(favoured))})
    other = mkSection({cname: Contour(cname, list(unfavoured))})
    sec.importTraces(other, threshold=IMPORT_DEFAULT, keep_below="self",
                     flag_conflicts=True)
    surviving = [t for t in sec.contours.get(cname, [])]
    return sec, [t for t in surviving if any(t is u for u in unfavoured)]


# =========================================================================== #
# 1. what each metric measures
# =========================================================================== #
@pytest.mark.parametrize("sep", [0.0001, 0.001, 0.005, 0.01, 0.02, 0.039, 0.06])
def test_premise_area_metric_is_blind_to_near_straight_pairs(sep):
    """origin/main's ratio for two parallel straight open traces is 0 at EVERY
    separation, including zero.

    This is why the change exists, and also why the "before" behaviour cannot be
    described as a tolerance: there is no separation at which the area metric
    begins to see a near-straight pair.
    """
    a = mkOpen(straight(LONG, 0.0, 3))
    b = mkOpen(straight(LONG, sep, 4))   # 4 points, so pointsMatch cannot fire
    assert areaRatio(a, b) == 0.0
    assert mainOverlaps(a, b, IMPORT_DEFAULT) is False
    assert mainOverlaps(a, b, 0) is False


def test_premise_mains_only_other_route_is_pointsMatch():
    """With equal point counts main can still reach True, through pointsMatch,
    whose tolerance is 0.01 series units = 4.89 image px."""
    a = mkOpen(straight(LONG, 0.0, 3))
    assert mainOverlaps(a, mkOpen(straight(LONG, 0.0099, 3)), IMPORT_DEFAULT) is True
    assert mainOverlaps(a, mkOpen(straight(LONG, 0.0101, 3)), IMPORT_DEFAULT) is False
    assert Trace.POINTS_MATCH_TOLERANCE == 1e-2
    assert px(Trace.POINTS_MATCH_TOLERANCE) == pytest.approx(4.89, abs=0.01)


@pytest.mark.parametrize("sep_px,want", [
    (0.05, 1.0), (0.49, 1.0), (2.44, 1.0), (3.91, 1.0), (4.94, 1.0),
    (5.04, 0.0), (9.78, 0.0), (19.07, 0.0),
])
def test_new_metric_is_a_distance_test_bounded_at_five_pixels(sep_px, want):
    """The tolerance, measured on a 978 px trace: the flip is at 5 image px.

    2% of this trace's arc length would be 19.6 px, so the ceiling is what decides
    here and the flip sits at ``OPEN_TRACE_MATCH_MAX_PIXELS`` exactly, not at the
    fraction. Compare the median-size pair below, where the fraction is smaller
    than the ceiling and the fraction decides.
    """
    a = mkOpen(straight(LONG, 0.0, 3))
    b = mkOpen(straight(LONG, units(sep_px), 4))
    assert px(tolerance(a, b)) == pytest.approx(5.0, abs=1e-6)
    assert a.getOverlapRatio(b, MAG) == pytest.approx(want)


def test_the_tolerance_at_the_real_arc_length_percentiles():
    """d in image pixels at the measured percentiles of her 3,974 open traces.

    The fraction alone is in the middle column. It is right in the middle of the
    range and wrong at both ends, which is what the two bounds are for.

        arc length      2% of it     d
        29 px (min dup)   0.58 px     1.00 px   <- the floor binds
        123 px (median)   2.46 px     2.46 px      the fraction binds
        213 px (75th)     4.25 px     4.25 px      the fraction binds
        250 px            5.00 px     5.00 px   <- the crossover
        6846 px (95th)  136.92 px     5.00 px   <- the ceiling binds
    """
    for arc_px, frac_px, want_px in (
            (29.0, 0.58, 1.00),
            (123.08, 2.46, 2.46),
            (212.67, 4.25, 4.25),
            (250.0, 5.00, 5.00),
            (6846.0, 136.92, 5.00),
    ):
        arc = units(arc_px)
        assert px(Trace.OPEN_TRACE_MATCH_FRACTION * arc) == pytest.approx(
            frac_px, abs=0.01)
        assert px(Trace.openCurveTolerance(MAG, arc, arc)) == pytest.approx(
            want_px, abs=0.01)


def test_the_bounds_are_in_image_pixels_so_they_follow_the_magnification():
    """Same geometry, coarser images: the bounds move with mag, the fraction does not.

    This is the whole reason the bounds are expressed in pixels and threaded from
    the section rather than written as absolute series units.
    """
    a, b = mkOpen(straight(LONG, 0.0, 3)), mkOpen(straight(LONG, 0.0, 4))
    fraction = Trace.OPEN_TRACE_MATCH_FRACTION * LONG
    for mag in (MAG / 4, MAG, MAG * 3):
        d = tolerance(a, b, mag)
        assert d == pytest.approx(Trace.OPEN_TRACE_MATCH_MAX_PIXELS * mag)
        assert px(d) * (MAG / mag) == pytest.approx(5.0), "always 5 of its own pixels"

    ## and the crossover is visible: on images coarse enough, 2% of this trace's
    ## length is the smaller of the two and the fraction takes back over
    coarse = fraction / Trace.OPEN_TRACE_MATCH_MAX_PIXELS * 1.1
    assert tolerance(a, b, coarse) == pytest.approx(fraction)


def test_an_open_pair_cannot_be_measured_without_a_magnification():
    """No silent fallback: a call site that forgets is refused.

    The fallback that used to exist -- the unbounded fraction -- is the behaviour
    every "should" test in this file is about, so a forgotten argument must not
    quietly select it.
    """
    a, b = mkOpen(straight(LONG, 0.0, 3)), mkOpen(straight(LONG, 0.02, 4))
    with pytest.raises(ValueError, match="mag"):
        a.getOverlapRatio(b)
    with pytest.raises(ValueError, match="mag"):
        a.overlaps(b, IMPORT_DEFAULT)
    ## and closed pairs are unaffected, which is why it is not a required argument
    assert mkClosed(SQ).getOverlapRatio(mkClosed(SQ)) == pytest.approx(1.0)


# =========================================================================== #
# 2. THE MAINLINE PATH: Contour.importTraces at the dialog's own threshold
# =========================================================================== #
@pytest.mark.parametrize("label,mine,theirs,area_before", [
    ("straight, 9.8 px apart, unequal point counts",
     straight(LONG, 0.0, 3), straight(LONG, 0.02, 4), 0.0),
    ("two wiggly structures 9.8 px apart",
     wiggly(0.0, 9.0), wiggly(0.02, 13.0), 0.5089),
    ("6846 px traces 132 px apart",
     straight(BIG, 0.0, 3), straight(BIG, 0.27, 4), 0.0),
])
def test_distinct_structures_survive_an_import(label, mine, theirs, area_before):
    """The cases the ceiling rescues, at the threshold the import actually uses.

    None of these three pairs is a duplicate: each is two separate structures
    running near each other, further apart than the tolerance under which this
    codebase calls two points identical. ``origin/main`` also sent them to the
    conflict path -- but for the wrong reason, since the area metric sees nothing
    at all here -- and with an unbounded 2% tolerance the curve metric measured
    every one of them at exactly 1.0 and collapsed it silently.

    Both tracings must end up in the contour and in both conflict pools, so a
    human is asked.
    """
    a, b = mkOpen(mine, tag="drawn_by_A"), mkOpen(theirs, tag="drawn_by_B")

    assert areaRatio(a, b) == pytest.approx(area_before, abs=5e-4), label
    assert mainOverlaps(a, b, IMPORT_DEFAULT) is False, (
        f"{label}: origin/main sends this pair to the conflict path too"
    )
    for threshold in IMPORT_RANGE:
        assert a.overlaps(b, threshold, MAG) is False, (
            f"{label}: collapsed at threshold {threshold}"
        )

    survivors, pool_s, pool_o = runContourImport([a], [b], IMPORT_DEFAULT)
    assert len(survivors) == 2, f"{label}: an import collapsed two structures"
    assert pool_s == [a] and pool_o == [b], (
        f"{label}: and both are in the conflict pools, so both get flagged"
    )
    assert a.tags == {"drawn_by_A"} and b.tags == {"drawn_by_B"}, (
        "no tag merge happened, because no duplicate was declared"
    )


def test_distinct_structures_are_flagged_through_section_import():
    """End to end through Section.importTraces: both survive and a human is told."""
    mine = mkOpen(straight(LONG, 0.0, 3), tag="drawn_by_A")
    theirs = mkOpen(straight(LONG, 0.02, 4), tag="drawn_by_B")

    assert mainOverlaps(mine, theirs, IMPORT_DEFAULT) is False

    sec, survivors = runSectionImport([mine], [theirs], IMPORT_DEFAULT)

    assert len(survivors) == 2
    assert flagNames(sec).count("import-conflict_membrane") == 2, (
        "a reviewer can find both tracings"
    )


@pytest.mark.parametrize("label,mine,theirs,area_before,curve_after", [
    ("two wiggly structures 2.4 px apart",
     wiggly(0.0, 9.0), wiggly(0.005, 13.0), 0.7782, 0.7253),
    ("median-size traces 2.0 px apart",
     straight(TYPICAL, 0.0, 2), straight(TYPICAL, 0.004, 3), 0.0, 1.0),
])
def test_pairs_within_a_couple_of_pixels_still_collapse(label, mine, theirs,
                                                       area_before, curve_after):
    """And the honest half: two curves about 2 px apart are treated as one annotation.

    The second of these is collapsed at every threshold including 1.0, and that is
    not an accident of the bounds -- it is what the bounds were set to allow. A 2 px
    disagreement at this magnification is inside the distance ``pointsMatch`` has
    always accepted as the same point, and the metric-independent ground truth used
    to judge the reporting user's series draws its own line between "one
    annotation" and "two structures" at the same 2 px.

    Kept as a parametrised pair rather than folded into the positive cases because
    the first one does NOT collapse: 2.4 px apart over a wiggly pair leaves only
    73% of each curve within tolerance. The line is not at a fixed separation; it
    is at a fixed fraction of each curve lying within a bounded distance.
    """
    a, b = mkOpen(mine), mkOpen(theirs)
    assert areaRatio(a, b) == pytest.approx(area_before, abs=5e-4), label
    assert a.getOverlapRatio(b, MAG) == pytest.approx(curve_after, abs=5e-4), label
    assert a.overlaps(b, IMPORT_DEFAULT, MAG) is (curve_after > IMPORT_DEFAULT)


def test_threshold_one_no_longer_means_the_points_match():
    """The import tooltip's old contract, and why its wording had to change.

    ``dialog/import_series.py``'s tip_overlap used to say: "Setting the overlap
    threshold to 1.0 will instruct PyReconstruct to consider traces duplicates only
    if their points match perfectly", and that "the overlap fraction is also known
    as the Jaccard index". Neither holds for an open pair: a pair lying everywhere
    within tolerance scores exactly 1.0 with no two points in common. The tooltip
    now says what the number means instead. The closed pair the old wording was
    written for still behaves exactly as it described.
    """
    a = mkOpen(straight(TYPICAL, 0.0, 2))
    b = mkOpen(straight(TYPICAL, 0.004, 3))
    assert a.pointsMatch(b) is False, "the points do not match, by any tolerance"
    assert len(a.points) != len(b.points)
    assert a.getOverlapRatio(b, MAG) == 1.0
    assert a.overlaps(b, 1.0, MAG) is True, "yet threshold=1.0 calls them duplicates"

    sq = mkClosed(SQ)
    off = mkClosed([(0.02, 0), (1.02, 0), (1.02, 1), (0.02, 1)])
    assert off.overlaps(sq, 1.0) is False


@pytest.mark.parametrize("label,a_pts,b_pts,curve_ratio", [
    ("collinear segments, overlapping halves",
     [(0, 0), (1, 0)], [(0.5, 0), (1.5, 0)], 0.5115),
    ("collinear, one inside the other",
     [(0, 0), (2, 0)], [(0.5, 0), (1.5, 0)], 0.5102),
    ("vertical collinear pair, offset",
     [(0, 0), (0, 1)], [(0, 0.2), (0, 1.2)], 0.8092),
])
def test_degenerate_open_pairs_are_measured_not_exempted(label, a_pts, b_pts,
                                                         curve_ratio):
    """Pairs with no area at all used to score 0 and now score 0.51-0.81.

    Fork PR #167's "a pair with no area is not a duplicate at any threshold" does
    not carry over to open pairs, and it is not restored: a two-point open trace is
    a short straight profile in this data, not pixel dust, and 695 of her 3,974
    open traces are exactly that. The reasoning is written out in
    tests/test_open_trace_duplicates.py. Pinned here because these are the pairs a
    "the ratio was 0 anyway" argument does not cover, and because they flip for any
    caller passing a threshold below about 0.5.
    """
    a, b = mkOpen(a_pts), mkOpen(b_pts)
    assert areaRatio(a, b) == 0.0
    assert a.getOverlapRatio(b, MAG) == pytest.approx(curve_ratio, abs=5e-4)
    assert mainOverlaps(a, b, 0.5) is False
    assert a.overlaps(b, 0.5, MAG) is True, f"{label}: flips at threshold 0.5"
    assert a.overlaps(b, IMPORT_DEFAULT, MAG) is False, "but not at the import range"
    assert a.overlaps(b, IMPORT_FLOOR, MAG) is False, "nor at the lowest setting"


# =========================================================================== #
# 3. the other direction at the import threshold: a duplicate that no longer
#    collapses. Reachable -- and it preserves rather than destroys.
# =========================================================================== #
@pytest.mark.parametrize("frac,deviation_in_d,area_before,curve_after", [
    (0.03, 6.0, 0.9891, 0.9443),
    (0.06, 6.0, 0.9784, 0.9253),
    (0.10, 1.5, 0.9904, 0.9472),
    (0.10, 3.0, 0.9828, 0.9186),
])
def test_false_split_a_real_duplicate_stops_collapsing(frac, deviation_in_d,
                                                       area_before, curve_after):
    """One structure, traced twice, with one localized disagreement.

    The second tracing follows the first except over ``frac`` of its length, where
    it deviates by ``deviation_in_d * d``. A detour that small barely changes the
    enclosed area, so main measured above 0.95 and collapsed the pair; the curve
    metric measures the fraction of the curve that is off by more than d and lands
    below 0.95, so both tracings now survive and are flagged for a human.

    A reviewer now has to resolve a pair the import used to merge -- more work,
    but no lost work. This is the benign direction.
    """
    base = smoothCurve()
    a = mkOpen(base)
    d = Trace.openCurveTolerance(MAG, arcLength(base), arcLength(base))
    b = mkOpen(withDetour(base, frac, deviation_in_d * d))

    assert areaRatio(a, b) == pytest.approx(area_before, abs=5e-4)
    assert mainOverlaps(a, b, IMPORT_DEFAULT) is True, "main collapsed this pair"
    assert a.getOverlapRatio(b, MAG) == pytest.approx(curve_after, abs=5e-4)
    assert a.overlaps(b, IMPORT_DEFAULT, MAG) is False

    sec, survivors = runSectionImport([a], [b], IMPORT_DEFAULT)
    assert len(survivors) == 2, "both tracings survive"
    assert flagNames(sec).count("import-conflict_membrane") == 2, (
        "and a human is asked to choose, which is the conservative outcome"
    )


def test_the_benign_direction_never_destroys_at_any_call_site():
    """Structural, not geometric: False is the keep branch everywhere.

      Contour.importTraces: False -> the trace goes to a conflict pool and stays
        in the contour.
      tracesWithoutCounterpart: False -> the donor trace is an orphan -> the
        history shortcut is declined and both sides are kept, or (in the
        deliberate-removal branch) the removal that was going to happen anyway is
        recorded. More orphans never means fewer survivors.
      keep_below loop: False -> the unfavoured trace is not removed and is flagged
        import-conflict instead.
    """
    keeper = mkOpen(wiggly(0.0, 9.0))
    far = mkOpen([(x + 50, y + 50) for x, y in wiggly(0.0, 9.0)])
    assert mainOverlaps(keeper, far, 0) is False
    assert keeper.overlaps(far, 0, MAG) is False

    survivors, pool_s, pool_o = runContourImport([keeper], [far], IMPORT_DEFAULT)
    assert len(survivors) == 2 and pool_s and pool_o

    sec, kept = runHistoryShortcut([keeper], [far])
    assert kept == [far]
    assert "import-conflict_membrane" in flagNames(sec)

    sec2, kept2 = runKeepBelow([keeper], [far])
    assert kept2 == [far]
    assert not any(n.startswith("import-removed_") for n in flagNames(sec2))


@pytest.mark.parametrize("ratio,new_says", [
    (2, True), (100, True), (1000, True), (1500, True), (3000, False), (10000, False),
])
def test_false_split_of_a_fragment_needs_a_1000x_length_ratio(ratio, new_says):
    """The only case where a plausible duplicate stops being seen AT ALL.

    A fragment retraced on top of a much longer trace. ``_openCurveRatio``
    resamples at d/4 but caps the count at ``_OPEN_CURVE_MAX_SAMPLES`` = 1024, so
    past a length ratio near 1,500 the long trace's samples step over the fragment
    and the ratio collapses to 0 where main measured a small positive area
    overlap. Below that ratio both metrics see it. Bounding d does not move this
    boundary: the fragment is short enough that d sits at its floor either way.
    """
    L = 10.0
    xs = np.linspace(0.0, L, 400)
    long_ = mkOpen(np.column_stack([xs, 0.3 * np.sin(xs)]))
    frag = mkOpen([(x, 0.3 * np.sin(x))
                   for x in np.linspace(L / 2, L / 2 + L / ratio, 5)])

    assert areaRatio(long_, frag) > 0, "main always saw this as a counterpart"
    assert long_.overlaps(frag, 0, MAG) is new_says
    assert Trace._OPEN_CURVE_MAX_SAMPLES == 1024


# =========================================================================== #
# 4. the two threshold=0 call sites
#
#    Two different questions, and the bounds answer only the first:
#      * pairs that are merely SEPARATED  -> fixed, they score 0
#      * pairs that CROSS or TOUCH        -> not fixed, and cannot be by a bound
# =========================================================================== #
@pytest.mark.parametrize("sep_px,want_counterpart", [
    (6, True), (10, True), (20, False), (51, False), (100, False), (1118, False),
])
def test_separated_open_pairs_stay_independent_at_threshold_zero(sep_px,
                                                                want_counterpart):
    """The separated case, and the one the bounds do fix.

    Two distinct wiggly structures ``sep_px`` image pixels apart. Beyond the
    tolerance nothing of either curve is within d of the other, the ratio is 0, and
    the donor trace stays an orphan -- which is what makes the history shortcut
    decline and keep both sides. These traces are 978 px long, so an unbounded 2%
    tolerance is 19.6 px and everything up to that distance was a counterpart.

    51 px is the closest approach between distinct members of her ``SF1_Wh``
    fiducial marks and 1,118 px their median separation, but see
    test_crossing_and_touching_pairs_are_still_counterparts: those particular
    contours are not fixed by this, because their members intersect.
    """
    keeper = mkOpen(wiggly(0.0, 9.0))
    donor = mkOpen(wiggly(units(sep_px), 13.0))
    assert keeper.overlaps(donor, 0, MAG) is want_counterpart

    sec, kept = runHistoryShortcut([keeper], [donor])
    if want_counterpart:
        assert kept == [], "absorbed: no orphan left to decline the shortcut"
    else:
        assert kept == [donor], "an independent trace survives the shortcut"
        assert "import-conflict_membrane" in flagNames(sec)


def test_the_ceiling_rescues_a_nearly_touching_pair_at_threshold_zero():
    """An L whose arms miss by 14.7 px: a counterpart under the 2% tolerance, not now.

    Both traces are about 978 px long, so the unbounded fraction gives d = 19.6 px
    and the 14.7 px gap sits inside it (it measured 0.0050). At the 5 px ceiling the
    gap is outside and the ratio is 0.
    """
    a, b = mkOpen([(0, 0), (2, 0)]), mkOpen([(1, 0.03), (1, 2)])
    assert px(0.03) == pytest.approx(14.67, abs=0.01)
    assert areaRatio(a, b) == 0.0, "main measures no area overlap either"
    assert a.getOverlapRatio(b, MAG) == 0.0
    assert a.overlaps(b, 0, MAG) is False

    _, kept = runHistoryShortcut([a], [b])
    assert kept == [b]


@pytest.mark.parametrize("label,pts_a,pts_b,want_ratio", [
    # each pair is two DIFFERENT structures, and each is a 2-point pair, which
    # Section.__init__ forces open
    ("X crossing at right angles", [(0, 0), (1, 1)], [(0, 1), (1, 0)], 0.0162),
    ("T junction, touching", [(0, 0), (2, 0)], [(1, 0), (1, 2)], 0.0064),
    ("L, 4.9 px apart", [(0, 0), (2, 0)], [(1, 0.01), (1, 2)], 0.0013),
    ("collinear, end to end", [(0, 0), (1, 0)], [(1.001, 0), (2, 0)], 0.0102),
])
def test_crossing_and_touching_pairs_are_still_counterparts(label, pts_a, pts_b,
                                                           want_ratio):
    """What no bound can fix, pinned as the limit it is.

    ``threshold=0`` reduces ``ratioIsOverlap`` to ``r > 0``, and a pair of curves
    that actually meet has a nonzero fraction of each within any positive
    tolerance: about d over the shorter arc length. Bounding d shrinks these ratios
    (the T junction went from 0.0249 to 0.0064) and cannot zero them.

    Measured on the reporting user's series: 487 of 979 donor open traces stop being
    orphans, unchanged whether the ceiling is 2 px or unbounded, and the contours
    responsible are her ``SF1_Wh`` and ``grid`` fiducial marks, whose members
    intersect -- median closest approach 0.67 px, even though their mean deviation
    is 1,118 px, and it is the closest approach that a tolerance tests. That is why
    test_separated_open_pairs_stay_independent_at_threshold_zero passing does not
    settle the question, and why the ratchet below still does not pass.
    """
    a, b = mkOpen(pts_a), mkOpen(pts_b)
    assert areaRatio(a, b) == 0.0, f"{label}: main measures no area overlap"
    assert mainOverlaps(a, b, 0) is False, f"{label}: main: not a counterpart"
    assert a.getOverlapRatio(b, MAG) == pytest.approx(want_ratio, abs=5e-4)
    assert a.overlaps(b, 0, MAG) is True, f"{label}: counterpart"
    assert a.overlaps(b, IMPORT_FLOOR, MAG) is False, (
        f"{label}: and it takes threshold=0 to accept it -- nothing the import "
        f"dialog can ask for comes near"
    )


def test_regression_history_shortcut_destroys_a_crossing_donor_trace():
    """The keeper holds a horizontal segment; the donor holds a vertical one
    crossing it -- a different structure. The history says only the keeper side
    changed.

      origin/main: the donor trace overlaps nothing -> orphan -> the shortcut is
        declined, both sides are kept and an import-conflict flag is raised.
      now: it "overlaps" (r = 0.0064) -> not an orphan -> the shortcut is taken,
        the donor contour is discarded, no flag, no log.

    This pins the LOSS. Inverting it is a deliberate act; its ratchet is
    ``test_crossing_donor_trace_should_survive_the_history_shortcut``.
    """
    keeper = mkOpen([(0, 0), (2, 0)], tag="drawn_by_A")
    donor = mkOpen([(1, 0), (1, 2)], tag="drawn_by_B")

    assert mainOverlaps(keeper, donor, 0) is False
    assert keeper.overlaps(donor, 0, MAG) is True

    sec, kept = runHistoryShortcut([keeper], [donor])

    assert kept == [], "the donor trace is gone"
    assert flagNames(sec) == [], "with no flag"
    assert sec.series.logs == [], "and no log entry"


@pytest.mark.xfail(strict=True, reason=(
    "The safe behaviour, which bounding the tolerance does NOT buy -- measured, "
    "not assumed. A coverage-at-a-tolerance metric gives a crossing pair a ratio "
    "of about d over the shorter arc length, positive for every positive d, and "
    "threshold=0 accepts anything positive. The bounds fix the SEPARATED pairs "
    "(test_separated_open_pairs_stay_independent_at_threshold_zero) and cannot fix "
    "this one: on the reporting user's series the donor traces that stop being "
    "orphans number 487 at a 5 px ceiling and 485 at a 2 px ceiling. Remove this "
    "marker when the merge path stops asking threshold=0 of the curve metric, "
    "which is a decision about what 'overlaps at all' should mean for a curve "
    "rather than about the tolerance."
))
def test_crossing_donor_trace_should_survive_the_history_shortcut():
    keeper = mkOpen([(0, 0), (2, 0)])
    donor = mkOpen([(1, 0), (1, 2)])
    _, kept = runHistoryShortcut([keeper], [donor])
    assert kept, "a trace drawn by a colleague was destroyed by the import"


def test_regression_keep_below_deletes_a_crossing_unfavoured_trace():
    """The second threshold=0 site. Same flip -- but this loss IS recorded."""
    favoured = mkOpen([(0, 0), (2, 0)])
    unfavoured = mkOpen([(1, 0), (1, 2)])

    assert mainOverlaps(favoured, unfavoured, 0) is False
    assert favoured.overlaps(unfavoured, 0, MAG) is True

    sec, kept = runKeepBelow([favoured], [unfavoured])

    assert kept == [], "the unfavoured trace is deleted"
    assert any(n.startswith("import-removed_") for n in flagNames(sec)), (
        "this site records what it destroys, unlike the history shortcut"
    )
    assert sec.series.logs


def test_keep_below_does_not_run_by_default():
    """Premise for calling that site dormant: the dialog's default is "".

    ``Section.importTraces``'s keep_below parameter defaults to "" and the loop is
    guarded by ``keep_below in ("self", "other")``, so nothing is deleted there
    unless a user asks for it. The history shortcut above has no such escape: it is
    on by default.
    """
    favoured = mkOpen([(0, 0), (2, 0)])
    unfavoured = mkOpen([(1, 0), (1, 2)])
    sec = mkSection({"membrane": Contour("membrane", [favoured])})
    other = mkSection({"membrane": Contour("membrane", [unfavoured])})
    sec.importTraces(other, threshold=IMPORT_DEFAULT, flag_conflicts=True)
    assert any(t is unfavoured for t in sec.contours["membrane"])
    assert not any(n.startswith("import-removed_") for n in flagNames(sec))


def test_orphan_protection_is_per_contour_not_per_trace():
    """The blast radius of one absorbed trace is the whole donor contour.

    ``tracesWithoutCounterpart`` gates the shortcut for the contour, not for the
    individual trace, so a contour whose LAST orphan is absorbed loses every donor
    trace at once. Two crossing donor traces here: on main both are orphans and
    both survive with a flag each; now neither is, and both are gone.
    """
    keepers = [mkOpen([(0, 0), (2, 0)]), mkOpen([(0, 3), (2, 3)])]
    donors = [mkOpen([(1, 0), (1, 2)]), mkOpen([(1, 3), (1, 5)])]

    donor_c, keeper_c = Contour("membrane", donors), Contour("membrane", keepers)
    for d in donors:
        assert any(mainOverlaps(d, k, 0) for k in keepers) is False, (
            "premise: on main every donor trace here is an orphan"
        )
    assert tracesWithoutCounterpart(donor_c, keeper_c, MAG) == [], (
        "not one of them is an orphan any more"
    )

    sec, kept = runHistoryShortcut(keepers, donors)
    assert kept == [], "both donor traces went, from one metric change"
    assert flagNames(sec) == []


def test_a_single_surviving_orphan_still_protects_the_contour():
    """The contrast, and the reason the loss needs a whole contour to line up: one
    donor trace that overlaps nothing is enough to decline the shortcut and save
    the absorbed ones with it."""
    keeper = mkOpen([(0, 0), (2, 0)])
    crossing = mkOpen([(1, 0), (1, 2)])       # absorbed
    far = mkOpen([(50, 50), (52, 50)])        # nowhere near anything

    assert tracesWithoutCounterpart(
        Contour("membrane", [crossing, far]), Contour("membrane", [keeper]), MAG
    ) == [far]
    sec, kept = runHistoryShortcut([keeper], [crossing, far])
    assert len(kept) == 2, "the orphan carried the crossing trace to safety"
    assert "import-conflict_membrane" in flagNames(sec)


def test_threshold_zero_also_fixes_a_silent_loss_on_main():
    """Contradiction worth recording: at threshold=0 the change is not one-way.

    Two distinct wiggly structures 48.9 image px apart. Their closing-chord
    regions still intersect, so main measures 0.005 > 0, calls them counterparts,
    and the history shortcut destroys the donor trace with no flag. The curve
    metric measures 0 -- nowhere within d -- so the trace is an orphan and
    survives.
    """
    keeper = mkOpen(wiggly(0.0, 9.0))
    donor = mkOpen(wiggly(0.1, 13.0))
    assert px(0.1) == pytest.approx(48.90, abs=0.01)

    assert areaRatio(keeper, donor) == pytest.approx(0.005, abs=5e-4)
    assert mainOverlaps(keeper, donor, 0) is True
    assert keeper.getOverlapRatio(donor, MAG) == 0.0
    assert keeper.overlaps(donor, 0, MAG) is False

    sec, kept = runHistoryShortcut([keeper], [donor])
    assert kept == [donor], "the trace main would have destroyed is kept"
    assert "import-conflict_membrane" in flagNames(sec)


# =========================================================================== #
# 5. the magnification actually reaches all three call sites
#
#    The tolerance is only bounded if the mag arrives. These record which value
#    each site passes, so a future edit that drops the argument fails here rather
#    than silently widening the tolerance back out.
# =========================================================================== #
def _recordMags(monkeypatch):
    seen = []
    real = Trace.getOverlapRatio

    def spy(self, other, mag=None):
        if not self.closed and not other.closed:
            seen.append(mag)
        return real(self, other, mag)

    monkeypatch.setattr(Trace, "getOverlapRatio", spy)
    return seen


def test_contour_import_receives_the_sections_own_mag(monkeypatch):
    """Section.importTraces passes self.mag, not other.mag.

    Self's is the correct one: the loop above the call has already brought the
    other series' traces onto this section's magnification with Trace.magScale, so
    both sides' coordinates are in these units by the time the comparison happens.
    """
    seen = _recordMags(monkeypatch)
    a = mkOpen(straight(LONG, 0.0, 3))
    b = mkOpen(straight(LONG, 0.02, 4))
    sec = mkSection({"membrane": Contour("membrane", [a])}, mag=MAG)
    other = mkSection({"membrane": Contour("membrane", [b])}, mag=MAG)
    sec.importTraces(other, threshold=IMPORT_DEFAULT, flag_conflicts=True)
    assert seen and set(seen) == {MAG}


def test_traces_without_counterpart_receives_the_sections_mag(monkeypatch):
    seen = _recordMags(monkeypatch)
    runHistoryShortcut([mkOpen(wiggly(0.0, 9.0))],
                       [mkOpen(wiggly(units(20), 13.0))])
    assert seen and set(seen) == {MAG}


def test_keep_below_loop_receives_the_sections_mag(monkeypatch):
    seen = _recordMags(monkeypatch)
    runKeepBelow([mkOpen([(0, 0), (2, 0)])], [mkOpen([(1, 0), (1, 2)])])
    assert seen and set(seen) == {MAG}


def test_traces_without_counterpart_without_a_mag_refuses_rather_than_guesses():
    """The default is not a working default for open traces, on purpose."""
    donor = Contour("membrane", [mkOpen(straight(LONG, 0.02, 4))])
    keeper = Contour("membrane", [mkOpen(straight(LONG, 0.0, 3))])
    with pytest.raises(ValueError, match="mag"):
        tracesWithoutCounterpart(donor, keeper)


# =========================================================================== #
# 6. closed pairs are untouched -- confirmed, not assumed
# =========================================================================== #
@pytest.mark.parametrize("label,other,ratio", [
    ("quarter overlap", [(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)], 0.152686),
    ("disjoint", [(2, 2), (3, 2), (3, 3), (2, 3)], 0.0),
    ("identical", SQ, 1.0),
    ("touching along an edge", [(1, 0), (2, 0), (2, 1), (1, 1)], 0.007042),
])
def test_closed_pairs_measure_exactly_what_main_measured(label, other, ratio):
    """Values read off a real origin/main c85d701c checkout."""
    a, b = mkClosed(SQ), mkClosed(other)
    assert a.getOverlapRatio(b) == pytest.approx(ratio, abs=1e-6)
    assert a.overlaps(b, threshold=0) is (ratio > 0)
    assert a.overlaps(b, IMPORT_DEFAULT) is (ratio > IMPORT_DEFAULT)
    ## a mag, if one is passed, is ignored rather than consulted
    assert a.getOverlapRatio(b, MAG) == pytest.approx(ratio, abs=1e-6)


def test_closed_pairs_never_reach_the_curve_metric(monkeypatch):
    """Structural proof that no closed pair can change: the dispatch is
    ``not self.closed and not other.closed``, so making _openCurveRatio explode
    leaves every closed and every mixed pair working."""
    def boom(*a, **k):
        raise AssertionError("_openCurveRatio must not be reached")

    monkeypatch.setattr(Trace, "_openCurveRatio", staticmethod(boom))

    a = mkClosed(SQ)
    for other in ([(0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5)], SQ,
                  [(2, 2), (3, 2), (3, 3), (2, 3)]):
        a.getOverlapRatio(mkClosed(other))
    assert mkOpen(SQ).getOverlapRatio(mkClosed(SQ)) == pytest.approx(1.0)
    assert mkOpen(SQ).overlaps(mkClosed(SQ), threshold=0) is False
