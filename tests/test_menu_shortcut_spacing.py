"""Menu shortcut keybinds get breathing room from their labels.

Qt right-justifies a shortcut against its menu item's right edge, but the
native macOS style sizes CT_MenuItem so tightly that the widest label runs to
within ~5 px of the shortcut column (measured by pixel-scanning a QMenu.grab()
of the real File menu items: label ink ended at x=153, shortcut ink began at
x=158, while the item's own left padding was ~19 px). PyReconstruct's menubar
is in-window -- setNativeMenuBar(False) -- so every menu is Qt-drawn and the
fix belongs in the style layer.

``MenuShortcutSpacingStyle`` (a QProxyStyle installed once in run.py) widens
CT_MenuItem by one line-height of the menu font for items that carry a
shortcut, which pushes the right-aligned shortcut column further right while
leaving ALL painting to the native style. A stylesheet was rejected with
evidence: any ``QMenu::item`` rule swaps the item's layout to the CSS box
model, which visibly strips the native left padding (label ink moved from
x=18.5 to x=0.5 in the same grab harness).

These tests prove the mechanism on a per-widget style (equivalent sizing path,
no mutation of the suite-wide QApplication style): the width grows by exactly
one line-height, the *rendered* pixel gap between label ink and shortcut ink
grows accordingly, and menus without shortcuts are untouched.
"""

import pytest

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu


ITEMS = [
    # (text, shortcut) -- real File menu rows; "Restart PyReconstruct" is the
    # widest labelled+shortcut row and therefore the cramped one
    ("Open series...", "Ctrl+O"),
    ("Save", "Ctrl+S"),
    ("Restart PyReconstruct", "Ctrl+R"),
    ("Quit", "Ctrl+Q"),
    ("Change username...", ""),
]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(["test"])
    # A standalone QMenu counts as a "context menu", and on macOS Qt neither
    # shows nor SIZES FOR shortcuts in context menus by default. The app's
    # menus hang off a (non-native) QMenuBar, where shortcuts do appear, so
    # flip the attribute to reproduce the menubar-dropdown layout, and restore
    # it afterwards.
    before = app.testAttribute(Qt.AA_DontShowShortcutsInContextMenus)
    app.setAttribute(Qt.AA_DontShowShortcutsInContextMenus, False)
    yield app
    app.setAttribute(Qt.AA_DontShowShortcutsInContextMenus, before)


def _menu(qapp, spaced: bool, items=ITEMS) -> QMenu:
    menu = QMenu()
    if spaced:
        from PyReconstruct.modules.gui.utils import MenuShortcutSpacingStyle

        # per-widget install: same sizeFromContents path QMenu uses, without
        # touching the QApplication style other tests share
        style = MenuShortcutSpacingStyle()
        style.setParent(menu)
        menu.setStyle(style)
    for text, kbd in items:
        action = QAction(text, menu)
        if kbd:
            action.setShortcut(kbd)
        menu.addAction(action)
    menu.resize(menu.sizeHint())
    return menu


def _ink_columns(menu: QMenu, action: QAction):
    """x-positions (logical px, relative to the item rect) of every column of
    the rendered item that contains non-background pixels."""
    image = menu.grab().toImage()
    scale = image.devicePixelRatio()
    rect = menu.actionGeometry(action)
    x0, y0 = int(rect.x() * scale), int(rect.y() * scale)
    w, h = int(rect.width() * scale), int(rect.height() * scale)

    # background = the item's most common color
    from collections import Counter

    counts = Counter(
        image.pixel(x, y) for y in range(y0, y0 + h) for x in range(x0, x0 + w)
    )
    background = counts.most_common(1)[0][0]

    def contrasts(pixel):
        return (
            abs(((pixel >> 16) & 0xFF) - ((background >> 16) & 0xFF))
            + abs(((pixel >> 8) & 0xFF) - ((background >> 8) & 0xFF))
            + abs((pixel & 0xFF) - (background & 0xFF))
        ) > 90

    return [
        (x - x0) / scale
        for x in range(x0, x0 + w)
        if any(contrasts(image.pixel(x, y)) for y in range(y0, y0 + h))
    ]


def _label_shortcut_gap(menu: QMenu, action: QAction) -> float:
    """The widest run of background between two runs of ink -- i.e. the gap
    between where the label ends and the shortcut begins."""
    columns = _ink_columns(menu, action)
    assert columns, "no rendered ink found in the item -- did shortcuts render?"
    return max(
        (b - a for a, b in zip(columns, columns[1:])), default=0.0
    )


def _widest_action(menu: QMenu) -> QAction:
    return next(a for a in menu.actions() if a.text() == "Restart PyReconstruct")


# --------------------------------------------------------------------------- #
# sizing: deterministic, style-arithmetic level
# --------------------------------------------------------------------------- #
def test_shortcut_rows_gain_exactly_one_line_height_of_width(qapp):
    plain = _menu(qapp, spaced=False)
    spaced = _menu(qapp, spaced=True)
    extra = spaced.fontMetrics().height()
    assert spaced.sizeHint().width() == plain.sizeHint().width() + extra


def test_menus_without_shortcuts_are_untouched(qapp):
    items = [("Randomize project...", ""), ("De-randomize project...", "")]
    plain = _menu(qapp, spaced=False, items=items)
    spaced = _menu(qapp, spaced=True, items=items)
    assert spaced.sizeHint().width() == plain.sizeHint().width()
    assert spaced.sizeHint().height() == plain.sizeHint().height()


# --------------------------------------------------------------------------- #
# rendering: the gap the user actually sees, measured off a grab
# --------------------------------------------------------------------------- #
def test_rendered_gap_between_label_and_shortcut_grows_by_the_extra(qapp):
    """Pixel evidence, not eyeballing: in the widest row, the largest
    background run between label ink and shortcut ink must grow by about the
    line-height (small tolerance for glyph side-bearings)."""
    plain = _menu(qapp, spaced=False)
    spaced = _menu(qapp, spaced=True)
    extra = spaced.fontMetrics().height()

    gap_before = _label_shortcut_gap(plain, _widest_action(plain))
    gap_after = _label_shortcut_gap(spaced, _widest_action(spaced))

    assert gap_after >= gap_before + 0.75 * extra, (
        f"gap only went {gap_before:.1f}px -> {gap_after:.1f}px "
        f"(extra={extra}px): the widened item did not push the shortcut over"
    )


def test_shortcut_column_stays_right_justified(qapp):
    """The widening must land between label and shortcut, not to the right of
    the shortcut: the last ink of the row keeps the same distance from the
    item's right edge as in the unspaced menu."""
    plain = _menu(qapp, spaced=False)
    spaced = _menu(qapp, spaced=True)

    def right_margin(menu):
        action = _widest_action(menu)
        return menu.actionGeometry(action).width() - _ink_columns(menu, action)[-1]

    assert abs(right_margin(spaced) - right_margin(plain)) <= 2.0


# --------------------------------------------------------------------------- #
# wiring: the app installs the style once, at QApplication creation
# --------------------------------------------------------------------------- #
def test_run_py_installs_the_spacing_style():
    """run.py is never imported by the suite (it launches the app), so the
    wiring is pinned at source level: the style is set right after the
    QApplication is created, where it survives setTheme's stylesheet swaps."""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "PyReconstruct" / "run.py"
    ).read_text(encoding="utf-8")
    created = source.index("app = QApplication(sys.argv)")
    assert "app.setStyle(MenuShortcutSpacingStyle())" in source[created:]
