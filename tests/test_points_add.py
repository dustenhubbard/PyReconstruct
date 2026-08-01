"""Regression tests for Points.__add__'s isinstance check.

The check read ``isinstance(other_points, tuple or list)``. Python evaluates
``tuple or list`` to ``tuple`` before isinstance runs, so a list argument fell
through to the else branch and was spliced in with ``+=``: a single point
passed as ``[x, y]`` corrupted the coordinate list with two bare scalars
instead of being appended as one point. Latent today -- nothing in the tree
applies ``+`` to a Points -- but a trap for the next caller. The check now
reads ``isinstance(other_points, (tuple, list))``.

Note the trap in testing this: ``tuple or list`` still accepts a tuple, so a
tuple-only test passes against the bug. The list case is the regression test.
"""
from PyReconstruct.modules.datatypes.points import Points


def test_add_list_point_appends_as_one_point():
    # Failed before the fix: [2, 2] was spliced to ...(1, 1), 2, 2
    p = Points([(0, 0), (1, 1)], closed=False)
    p + [2, 2]
    assert p.points == [(0, 0), (1, 1), [2, 2]]


def test_add_list_point_does_not_splice_scalars():
    # The exact corruption the bug produced: bare scalars in the point list.
    p = Points([(0, 0), (1, 1)], closed=False)
    p + [2, 2]
    assert 2 not in p.points


def test_add_tuple_point_appends_as_one_point():
    # Passed before and after the fix (tuple satisfied the broken check too);
    # kept so the tuple branch has coverage of its own.
    p = Points([(0, 0), (1, 1)], closed=False)
    p + (2, 2)
    assert p.points == [(0, 0), (1, 1), (2, 2)]
