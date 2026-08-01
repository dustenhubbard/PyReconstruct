"""MainWindow.undo() through the linked-undo prompt, offscreen.

`MainWindow.undo` reaches a three-way branch when both a series-wide undo and a
section-only undo are available and the two are linked: the current section's
undo state is part of the series state. The branch used to ask the user "undo
all sections or only this one?" via a constructed `QMessageBox(self)` instance
whose `exec()` spins a modal event loop. Under `QT_QPA_PLATFORM=offscreen`
nothing dismisses that loop, so the call never returns.

The fix adds a `user_is_present()` guard. When the platform is offscreen,
`undo()` takes the "undo all sections" default without showing a dialog, exactly
as a user pressing "All sections" would. This test confirms that the call
returns and that the series state (not just the section state) was consumed.

`main_window_dialogs` is included because `undo()` calls `saveAllData()` first,
which can reach `saveNotify`, and `seriesUndo()` rebuilds tables that call
`notify`.
"""

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def null_progress(main_window):
    """Suppress the progress dialog for any `enumerateSections` call.

    `SeriesStates.undoState()` and `Series.hideObjects()` call
    `enumerateSections`, which creates a `QtProgressReporter` (a
    `QProgressDialog`). Under offscreen Qt a `QProgressDialog` is not a stall,
    but `QtProgressReporter.__init__` imports `getProgbar`, and patching
    `mw.getProgbar` (what `main_window_dialogs` does) does not intercept that
    import. Using `NullProgressReporter` via `Series.setProgressReporter` is the
    seam the data model exposes for exactly this.
    """
    from PyReconstruct.modules.backend.progress import NullProgressReporter

    main_window.series.setProgressReporter(NullProgressReporter)
    yield main_window
    main_window.series.setProgressReporter(None)


@pytest.mark.gui
def test_undo_linked_prompt_returns_headlessly(
    null_progress, main_window_dialogs
):
    """undo() in the linked-undo branch returns without hanging under offscreen Qt.

    State setup: the current section's undo stack has two states (one from a
    simulated 2D edit, one recorded as part of a series-wide operation) and the
    series-state manager links them. This is the exact configuration
    `canUndo()` reports as `(True, True, True)` -- can_3D, can_2D, linked --
    which is the branch that previously stalled.

    The fix takes "undo all sections" (act3D) as the headless default.
    The assertion checks that the series state was consumed, not the
    section-only state.
    """
    window = null_progress
    field = window.field
    section = field.section
    ss = field.series_states
    series = window.series

    # Initialize the current section's undo baseline.
    ss[section]

    # Push a section-level undo (simulates a 2D edit that has its own undo).
    ss[section].addState(section, series)

    # Open a series state and record the current section as part of it.
    # Together these two steps match what SeriesIterator does for an operation
    # that modified this section: addState() on the series, addState() on the
    # section, then addSectionUndo() to link them.
    ss.addState()
    ss[section].addState(section, series)
    ss.addSectionUndo(section.n)

    can_3D, can_2D, linked = ss.canUndo()
    assert can_3D and can_2D and linked, (
        "precondition not met: canUndo() must return (True, True, True) to "
        "reach the linked-undo branch"
    )

    # Before the fix this never returned (permanent stall under offscreen Qt).
    window.undo()

    # act3D() was taken: the series state moved to the redo stack.
    assert len(ss.undos) == 0, (
        "series state should have been consumed by the 3D undo (act3D)"
    )
    assert len(ss.redos) == 1, (
        "series state should have moved to the redo stack"
    )
