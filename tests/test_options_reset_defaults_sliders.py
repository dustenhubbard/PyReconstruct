"""Reset Defaults in ``Series > Options`` must move the sliders too.

``AllOptionsDialog.resetDefaults`` clears the tabs and calls
``createWidgets(use_defaults=True)``. Every option in that method threads the
flag through to ``series.getOption(name, use_defaults)``, which returns the
shipped default instead of the stored value. Three did not: the 3D XY
resolution slider (``3D_xy_res``), the scale bar size slider
(``scale_bar_width``) and the CPU usage slider (``cpu_max``). They read the
stored value unconditionally, so pressing Reset Defaults rebuilt the dialog
with those three sliders sitting exactly where the user had left them.

These tests drive the real dialog against a real series and read the slider
values back through the widgets themselves, so the assertion is on what the
user sees rather than on the argument list.

Also here because it is the same surface: ``determine_cpus`` multiplies by
``os.cpu_count()``, which Python documents as possibly returning ``None``. The
CPU slider's readout calls it while the dialog is being built, so a ``None``
would raise on open rather than at conversion time.
"""
import os
import shutil

import pytest

from PyReconstruct.modules.datatypes.series import Series
from PyReconstruct.modules.datatypes.default_settings import default_settings
from PyReconstruct.modules.backend.settings_store import DictSettingsStore
from PyReconstruct.modules.gui.dialog.all_options import AllOptionsDialog

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "PyReconstruct",
    "assets", "checker", "files", "shapes1.jser",
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication(["test"])


def _series(tmp_path):
    """A real series backed by an in-memory settings store (no QSettings I/O)."""
    if not os.path.exists(FIXTURE):
        pytest.skip("fixture shapes1.jser not found")
    fp = str(tmp_path / "s.jser")
    shutil.copyfile(FIXTURE, fp)
    series = Series.openJser(fp)
    series.setSettingsStore(DictSettingsStore())
    return series


def _slider_value(dlg, widget_name, index):
    """Read a slider's actual position out of the built widget."""
    w = dlg.all_widgets[widget_name]
    assert w.accept(close=False)      # populates responses from the real widgets
    return w.responses[index]


def _identity(value):
    return value


def _scale_bar_position(value):
    """The dialog maps the stored 20-100 scale bar width onto the 0-100 groove.

    The truncation here is the dialog's own: 25 lands on position 6, not 6.25.
    That rounding predates this change and is left alone.
    """
    return int((value - 20) / 80 * 100)


# (option key, widget name, response index, a value that is not the default,
#  stored value -> slider position)
SLIDERS = [
    ("3D_xy_res", "smoothing_3D", 0, 73, _identity),
    ("cpu_max", "computation", 0, 90, _identity),
    ("scale_bar_width", "scale_bar", 1, 60, _scale_bar_position),
]


@pytest.mark.parametrize("option,widget,index,changed,position", SLIDERS)
def test_slider_opens_on_the_stored_value(qapp, tmp_path, option, widget, index, changed, position):
    """Precondition for the reset test: the slider tracks the stored value."""
    series = _series(tmp_path)
    series.setOption(option, changed)

    dlg = AllOptionsDialog(None, series)
    try:
        shown = _slider_value(dlg, widget, index)
    finally:
        dlg.deleteLater()

    assert shown == position(changed)


@pytest.mark.parametrize("option,widget,index,changed,position", SLIDERS)
def test_reset_defaults_moves_the_slider(qapp, tmp_path, option, widget, index, changed, position):
    """Move a slider, press Reset Defaults, and the slider must show the default."""
    series = _series(tmp_path)
    default = default_settings[option]
    assert position(changed) != position(default), "the test value must differ from the default"
    series.setOption(option, changed)

    dlg = AllOptionsDialog(None, series)
    try:
        dlg.resetDefaults()
        shown = _slider_value(dlg, widget, index)
    finally:
        dlg.deleteLater()

    assert shown == position(default)

    # Reset Defaults only repopulates the dialog; nothing is stored until OK
    assert series.getOption(option) == changed


def test_determine_cpus_survives_cpu_count_none(monkeypatch):
    """os.cpu_count() may return None; determine_cpus must still return >= 1."""
    from PyReconstruct.modules.backend.func import utils

    monkeypatch.setattr(utils.os, "cpu_count", lambda: None)
    assert utils.determine_cpus(50) == 1
    assert utils.determine_cpus(100) == 1


def test_options_dialog_opens_when_cpu_count_is_none(qapp, tmp_path, monkeypatch):
    """The CPU section is built at dialog-open time, so a None cpu count must
    not stop Series > Options from opening."""
    from PyReconstruct.modules.backend.func import utils

    monkeypatch.setattr(utils.os, "cpu_count", lambda: None)
    series = _series(tmp_path)
    dlg = AllOptionsDialog(None, series)
    try:
        assert "computation" in dlg.all_widgets
    finally:
        dlg.deleteLater()
