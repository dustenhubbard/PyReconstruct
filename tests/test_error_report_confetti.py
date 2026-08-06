"""The confetti burst on "Copy report to clipboard".

What this file can check and what it cannot are worth separating up front,
because the feature is an animation and most of what a reader would want checked
is visual.

CHECKED HERE: that a burst happens on a copy that worked and does not happen on
one that did not; that the particles are real child widgets, countable while
they fly; that every one of them is gone once the animation ends; that repeating
the click neither crashes nor accumulates widgets; and that the "Copied ✓" label
this change shares a handler with still behaves exactly as it did.

NOT CHECKED HERE, and not by anything else: what it looks like. Colour, the
shape of the arc, the easing curve, whether 12 dots over ~700ms reads as "small"
or as "too much" -- none of that is asserted, because none of it has a correct
value the suite could hold it to. It is a judgement about feel, and it is made
by looking at it. The tests below would pass on a burst that was the wrong
colour, went the wrong way, or lasted five seconds; they exist to stop the
mechanical failures around it (a leak, a crash, a burst on a failed copy, a
broken label), not to say the animation is good.

The particle lifetime tests drive the event loop with `qtbot.wait`. That is not
a sleep for timing's sake: a `QPropertyAnimation` advances on the event loop and
`deleteLater` is delivered by it, so without a real wait the burst never runs
and nothing is ever collected. The waits allow generously more than
`DURATION_RANGE`'s ceiling.
"""

import pytest

from PySide6.QtCore import Qt

from PyReconstruct.modules.gui.utils import errors
from PyReconstruct.modules.gui.utils.confetti import (
    ConfettiParticle,
    DURATION_RANGE,
    PARTICLE_COUNT,
    burst_confetti,
)

pytestmark = pytest.mark.gui


# Comfortably past the longest particle, with room for the deferred delete.
SETTLE_MS = DURATION_RANGE[1] + 400


def _dialog(qtbot):
    dialog = errors.ErrorReportDialog("<b>Something failed.</b>", "the report text")
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(30)
    return dialog


def _particles(dialog):
    """Every particle currently alive under the dialog.

    `findChildren` walks the C++ object tree, so a particle that has been
    `deleteLater`-ed and collected is absent here; one merely scheduled for
    deletion is still present. That distinction is the point of the waits.
    """
    return dialog.findChildren(ConfettiParticle)


class _NoClipboard:
    """Stands in for `QApplication` on a platform that has no clipboard.

    Patched over the name in `errors`, rather than over `QApplication.clipboard`
    itself: the real class is a C++ type whose attributes are not reliably
    settable, and `_copyReport` reaches the clipboard only through this name.
    """

    @staticmethod
    def clipboard():
        return None


def test_a_successful_copy_spawns_particles(qtbot):
    """The whole point: a copy that worked is celebrated."""
    dialog = _dialog(qtbot)
    assert _particles(dialog) == []

    dialog._copyReport()

    assert len(_particles(dialog)) == PARTICLE_COUNT


def test_the_particles_belong_to_the_window_not_to_the_button(qtbot):
    """A child widget is clipped to its parent, so the button cannot be it.

    Parented to the button, the burst would be invisible outside a rectangle a
    few pixels tall -- the animation would run and show nothing. This is the
    kind of mistake that looks fine in the source and produces no feature.
    """
    dialog = _dialog(qtbot)
    dialog._copyReport()

    particles = _particles(dialog)
    assert particles
    assert all(p.parent() is dialog for p in particles)
    assert not dialog._copy_btn.findChildren(ConfettiParticle)


def test_no_burst_when_there_is_no_clipboard(qtbot, monkeypatch):
    """Nothing was copied, so there is nothing to celebrate."""
    dialog = _dialog(qtbot)
    monkeypatch.setattr(errors, "QApplication", _NoClipboard)

    dialog._copyReport()

    assert _particles(dialog) == []


def test_the_copied_label_is_unchanged_on_both_paths(qtbot, monkeypatch):
    """The regression risk of touching this handler at all.

    The label was set on both the clipboard and the no-clipboard path before
    this change, and it still is. Pinned because the natural way to write the
    "only celebrate a real copy" guard is an early `return` on a null clipboard,
    which would silently take the label with it.
    """
    dialog = _dialog(qtbot)
    assert dialog._copy_btn.text() == "Copy report to clipboard"
    dialog._copyReport()
    assert dialog._copy_btn.text() == "Copied ✓"

    other = _dialog(qtbot)
    monkeypatch.setattr(errors, "QApplication", _NoClipboard)
    other._copyReport()
    assert other._copy_btn.text() == "Copied ✓"


def test_every_particle_is_deleted_once_its_animation_finishes(qtbot):
    """No leaked widgets. The burst owns its own cleanup."""
    dialog = _dialog(qtbot)
    dialog._copyReport()
    assert _particles(dialog)

    qtbot.wait(SETTLE_MS)

    assert _particles(dialog) == []


def test_repeated_clicks_neither_crash_nor_accumulate(qtbot):
    """Ten copies in a row, then nothing left behind.

    The clicks are real mouse clicks through the button rather than direct
    calls, so the wiring from `clicked` to the burst is covered once here.
    """
    dialog = _dialog(qtbot)

    for _ in range(10):
        qtbot.mouseClick(dialog._copy_btn, Qt.LeftButton)
        qtbot.wait(20)

    assert dialog._copy_btn.text() == "Copied ✓"
    # Mid-flight there are many; the ceiling is what a single click makes times
    # the clicks that can still be in the air, and the floor is that clicking
    # again does not stop the previous burst from ever being collected.
    qtbot.wait(SETTLE_MS)
    assert _particles(dialog) == []


def test_an_unparented_anchor_bursts_onto_itself(qtbot):
    """`burst_confetti` is exported, so it has to hold up away from the dialog.

    An un-parented, never-shown widget is its own window in Qt's model, so the
    burst is legal and lands on the anchor. Worth pinning because the coordinate
    mapping is the part that has already bitten once: `mapTo`'s argument must be
    an ancestor, the degenerate "ancestor is the widget itself" case is the one
    a caller hits first, and getting the direction wrong is a segfault in
    PySide6 6.5.2 rather than an exception a caller could survive.
    """
    from PySide6.QtWidgets import QPushButton

    orphan = QPushButton("nowhere")
    qtbot.addWidget(orphan)

    particles = burst_confetti(orphan, count=3)

    assert len(particles) == 3
    assert all(p.parent() is orphan for p in particles)


def test_a_seeded_burst_is_reproducible(qtbot):
    """The randomness is injectable, so a burst can be repeated exactly.

    Not a property the feature needs, but the seam is what makes the geometry
    debuggable at all: without it, a burst that goes wrong on one machine cannot
    be reproduced on another.
    """
    import random

    dialog = _dialog(qtbot)
    first = burst_confetti(dialog._copy_btn, count=4, rng=random.Random(7))
    second = burst_confetti(dialog._copy_btn, count=4, rng=random.Random(7))

    assert [p.size() for p in first] == [p.size() for p in second]
    assert [p.pos() for p in first] == [p.pos() for p in second]
