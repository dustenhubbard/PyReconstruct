"""One error window per fault, and never one inside another.

A user on 1.21.0 (Windows) hit an exception raised from the field's
``paintEvent``. The exception hook opened a modal error window; the window's own
event loop delivered the next paint event; that raised again and opened another
window, and so on. Closing one exposed the field, which repainted, which raised.
The report reads "there is a neverending stream of these windows and I can't
close them. I had to go to task manager to close PyRe."

Both halves of that need closing, and they are different guards:

  * the nested form, where a window opens from inside another's ``exec``;
  * the serialized form, where closing a window lets the same fault report
    again from the top.

The tests never enter a real modal loop -- ``exec`` is replaced by a stand-in
that raises the way a paint event delivered inside it would.
"""
import sys

import pytest

from PyReconstruct.modules.gui.utils import errors

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def fresh_report_state(qapp, monkeypatch):
    """Session state, so each test starts from an app that has reported nothing.

    `qapp` because the dialog these tests count is a real `QDialog`: only its
    `exec` is replaced, so it still has to be constructible.

    `raising=False` so that a build without the guards fails these tests on what
    they assert rather than on a missing name.
    """
    monkeypatch.setattr(errors, "_reported_signatures", set(), raising=False)
    monkeypatch.setattr(errors, "_showing_report", False, raising=False)
    # keep the console traceback out of the test output
    monkeypatch.setattr(sys, "__excepthook__", lambda *args: None)


def _raise_through_hook(message="'NoneType' object has no attribute 'getTrace'"):
    """Send an AttributeError through the hook the way an unhandled one arrives."""
    try:
        raise AttributeError(message)
    except AttributeError:
        errors.customExcepthook(*sys.exc_info())


def _count_dialogs(monkeypatch, on_exec=None):
    """Record every report dialog opened; optionally run `on_exec` inside one."""
    opened = []

    def fake_exec(self):
        opened.append(self)
        if on_exec is not None:
            on_exec(len(opened))
        return 0

    monkeypatch.setattr(errors.ErrorReportDialog, "exec", fake_exec)
    return opened


def test_a_paint_error_inside_the_dialog_does_not_open_another(monkeypatch):
    """The nested form: the modal loop delivers the repeat, mid-exec."""
    def raise_again(depth):
        if depth < 6:          # a cap, so a regression fails rather than hangs
            _raise_through_hook()

    opened = _count_dialogs(monkeypatch, on_exec=raise_again)

    _raise_through_hook()

    assert len(opened) == 1


def test_the_same_fault_reports_once_per_session(monkeypatch):
    """The serialized form: the user closes the window and it happens again."""
    opened = _count_dialogs(monkeypatch)

    for _ in range(5):
        _raise_through_hook()

    assert len(opened) == 1


def test_a_different_fault_still_reports(monkeypatch):
    """Deduplication is per fault, not a one-error-per-session cap."""
    opened = _count_dialogs(monkeypatch)

    _raise_through_hook()
    try:
        raise ValueError("a different problem entirely")
    except ValueError:
        errors.customExcepthook(*sys.exc_info())

    assert len(opened) == 2


def test_every_occurrence_still_reaches_the_log(monkeypatch, tmp_path):
    """Suppressing the window must not suppress the record."""
    log = tmp_path / "pyreconstruct.log"
    monkeypatch.setattr(
        "PyReconstruct.modules.backend.func.logging_setup.log_file_path",
        lambda: log,
    )
    _count_dialogs(monkeypatch)

    for _ in range(3):
        _raise_through_hook("marker-for-the-log")

    assert log.read_text(encoding="utf-8").count("marker-for-the-log") >= 3


def test_a_traceback_free_exception_is_always_reported(monkeypatch):
    """No traceback means no signature, and an unrecognisable fault is shown."""
    opened = _count_dialogs(monkeypatch)

    for _ in range(3):
        errors.customExcepthook(ValueError, ValueError("no traceback"), None)

    assert len(opened) == 3
