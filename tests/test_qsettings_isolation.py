"""Prove the suite cannot write the real application settings.

Three separate routes reached `QSettings("KHLab", "PyReconstruct")` from the
suite in one night and edited the developer's own preferences. The redirect and
the guard live in `tests/qsettings_isolation.py`; these are the tests that hold
them in place.

Two things are checked that are easy to conflate:

  - *isolation*: every route resolves inside the session's throwaway root, so a
    write cannot land on the real store. One test per known route, plus a sweep
    that fails if any imported module still holds the real class.
  - *the guard*: `RealSettingsGuard` actually notices a change. Tested against
    files in `tmp_path` rather than the real store, for the obvious reason, and
    including a genuine `QSettings` write through the real Qt machinery so the
    detection path is the real one and not a hand-written file.

The last test is the counterweight: production still resolves to the real
location. An isolation mechanism that also redirected the shipped app would be a
much worse bug than the one it fixes, and it has to be checked from outside the
suite's own process, since inside it the redirect is installed by design.
"""

import os
import plistlib
import subprocess
import sys
import textwrap

import pytest

import qsettings_isolation as qi


pytestmark = pytest.mark.skipif(
    not qi.installed, reason="PySide6 is not installed, so there is nothing to isolate"
)


def _under_root(path):
    return os.path.abspath(path).startswith(os.path.abspath(qi.isolation_root))


def _require_isolated():
    """Hard precondition for any test below that performs a write.

    These tests deliberately exercise the routes that caused the incidents,
    including the `series.user` setter. That is only safe while the redirect
    holds, so every writing test asserts the redirect *first* and fails without
    writing anything if it does not.
    """
    qi.verify_isolated()
    assert _under_root(qi.resolved_path()), qi.resolved_path()


# --- isolation ----------------------------------------------------------------


def test_the_qsettings_name_is_the_isolated_subclass():
    """`PySide6.QtCore.QSettings` is the substitute, not the real class."""
    import PySide6.QtCore as qtcore

    assert qtcore.QSettings is not qi._real_qsettings
    assert issubclass(qtcore.QSettings, qi._real_qsettings)


@pytest.mark.parametrize(
    "application",
    [
        "PyReconstruct",              # the global scope
        "PyReconstruct-someseries",   # a per-series scope
        "PyReconstruct-",             # a series whose code is empty; this file
                                      # exists on disk in the real Preferences
                                      # directory, so the route is real
    ],
)
def test_every_scope_resolves_inside_the_isolation_root(application):
    """Both scopes `QSettingsStore` addresses are redirected, not just the global one.

    A partial redirect is worse than none, because the half that still works
    looks like proof.
    """
    import PySide6.QtCore as qtcore

    settings = qtcore.QSettings("KHLab", application)
    assert settings.format() == qi._real_qsettings.Format.IniFormat
    assert _under_root(settings.fileName()), settings.fileName()


def test_direct_two_argument_construction_writes_into_the_root():
    """The plain `QSettings("KHLab", "PyReconstruct")` form, as written in
    `file_dialog.py`, `whats_new.py`, `main_window.py` and `mouse_palette.py`.
    """
    _require_isolated()
    import PySide6.QtCore as qtcore

    settings = qtcore.QSettings("KHLab", "PyReconstruct")
    settings.setValue("isolation_probe_direct", "landed")
    settings.sync()
    with open(settings.fileName()) as f:
        assert "isolation_probe_direct" in f.read()


def test_the_settings_store_seam_is_isolated():
    """Route with by far the widest reach: `Series.getOption`/`setOption` go
    through `QSettingsStore`, which builds its own `QSettings` from a deferred
    import. 132 `setOption` and 215 `getOption` call sites resolve here.
    """
    _require_isolated()
    from PyReconstruct.modules.backend.settings_store import QSettingsStore

    store = QSettingsStore()
    store.set_value(None, "isolation_probe_global", "g")
    store.set_value("probecode", "isolation_probe_series", "s")

    assert _under_root(store._settings(None).fileName())
    assert _under_root(store._settings("probecode").fileName())
    assert store.value(None, "isolation_probe_global", str) == "g"
    assert store.value("probecode", "isolation_probe_series", str) == "s"


def test_the_default_store_helpers_are_isolated():
    """`constants.getdatetime` reads the global "utc" option through
    `default_settings_store()`, a module-level cache separate from the one in
    `datatypes/series.py`. Both have to be isolated, and neither is reached by
    injecting a store into a `Series`.
    """
    _require_isolated()
    from PyReconstruct.modules.backend.settings_store import default_settings_store
    from PyReconstruct.modules.datatypes.series import _default_settings_store

    for store in (default_settings_store(), _default_settings_store()):
        assert _under_root(store._settings(None).fileName())


def test_the_series_user_setter_is_isolated():
    """Incident 2, as a regression test.

    `Series.user`'s setter is `setOption("username", value)`, which addresses the
    machine-wide scope, and a test that assigned it overwrote the developer's
    stored username. Assigning it here is safe only because
    `_require_isolated()` has already established that the write cannot reach the
    real store; the assertion order is the point.
    """
    _require_isolated()
    from PyReconstruct.modules.datatypes import Series
    from PyReconstruct.modules.backend.settings_store import QSettingsStore

    # No file I/O: only the setter path matters, and it needs just the internal
    # options dict (`username` is not in it, so it falls through to the store)
    # and a code for the per-series branch it does not take.
    series = Series.__new__(Series)
    series.options = {}
    series.code = "isolationprobe"
    series._settings_store = QSettingsStore()
    assert "username" in Series.qsettings_defaults, (
        "username is expected to be a global-scope option; if it moved to the "
        "per-series scope this test is checking the wrong thing"
    )

    series.user = "isolation-probe-user"

    assert QSettingsStore().value(None, "username", str) == "isolation-probe-user"
    assert _under_root(QSettingsStore()._settings(None).fileName())


def test_the_recently_opened_series_route_is_isolated():
    """Incident 3, at the option layer.

    `MainWindow.openSeries` calls `addToRecentSeries`, which is
    `setOption("recently_opened_series", ...)` on the global scope, so every
    `main_window` fixture build used to prepend a `tmp_path` to the developer's
    real recents list. `last_folder` travels the same way.
    """
    _require_isolated()
    from PyReconstruct.modules.backend.settings_store import QSettingsStore

    store = QSettingsStore()
    store.set_value(None, "recently_opened_series", '["/tmp/probe.jser"]')
    store.set_value(None, "last_folder", "/tmp/probe")
    assert _under_root(store._settings(None).fileName())
    assert store.value(None, "last_folder", str) == "/tmp/probe"


def test_no_imported_module_still_holds_the_real_qsettings_class():
    """The sweep that makes this durable rather than a list of known routes.

    `from PySide6.QtCore import QSettings` copies the class into the importing
    module, so patching `PySide6.QtCore` alone is not enough for a module that
    already imported it. Star imports are the trap: `main_window.py` gets the
    name through `from .main_imports import *`, so it holds a reference of its
    own. If a module ever ends up holding the real class again, that module is a
    live route to the developer's settings and this fails with its name.
    """
    holders = []
    for name, module in list(sys.modules.items()):
        if module is None:
            continue
        try:
            bound = getattr(module, "QSettings", None)
        except Exception:  # pragma: no cover - defensive
            continue
        if bound is qi._real_qsettings:
            holders.append(name)
    assert not holders, (
        "these imported modules hold the real QSettings class and can reach the "
        f"developer's settings: {sorted(holders)}"
    )


def test_the_production_call_sites_resolve_to_the_isolated_class():
    """Import every module that constructs a `QSettings` and check what it holds.

    Enumerated from `git grep QSettings(` rather than discovered, so a new call
    site in a new module does not quietly get left out of the check: the sweep
    above is what covers that case, and this is what pins the known ones.
    """
    import importlib

    modules = (
        "PyReconstruct.modules.gui.dialog.file_dialog",
        "PyReconstruct.modules.gui.dialog.whats_new",
        "PyReconstruct.modules.gui.palette.mouse_palette",
        "PyReconstruct.modules.gui.main.main_imports",
        "PyReconstruct.modules.gui.main.main_window",
    )
    for name in modules:
        module = importlib.import_module(name)
        bound = getattr(module, "QSettings", None)
        assert bound is not None, f"{name} no longer binds QSettings"
        assert bound is not qi._real_qsettings, name
        assert _under_root(bound("KHLab", "PyReconstruct").fileName()), name


def test_whats_new_module_constants_still_name_the_real_domain():
    """The redirect changes the *location*, not the organization/application names.

    Worth pinning: swapping the names to a test-only pair was the other candidate
    mechanism, and it would have made every settings key the app reads at runtime
    invisible to these tests while looking like it worked.
    """
    from PyReconstruct.modules.gui.dialog import whats_new

    assert (whats_new.ORG, whats_new.APP) == ("KHLab", "PyReconstruct")


# --- the guard ----------------------------------------------------------------


def _guard_on(tmp_path):
    directory = tmp_path / "prefs"
    directory.mkdir()
    return qi.RealSettingsGuard(str(directory), "com.example.Watched"), directory


def test_guard_is_quiet_when_nothing_changes(tmp_path):
    guard, directory = _guard_on(tmp_path)
    (directory / "com.example.Watched.plist").write_bytes(
        plistlib.dumps({"username": "real", "theme": "dark"})
    )
    (directory / "unrelated.plist").write_bytes(plistlib.dumps({"other": 1}))
    guard.snapshot()
    assert guard.diff() == []


def test_guard_reports_a_modified_file_and_names_the_keys(tmp_path):
    guard, directory = _guard_on(tmp_path)
    watched = directory / "com.example.Watched.plist"
    watched.write_bytes(plistlib.dumps({"username": "real", "theme": "dark"}))
    guard.snapshot()

    watched.write_bytes(plistlib.dumps({"username": "real", "last_folder": "/tmp/x"}))
    problems = guard.diff()

    assert len(problems) == 1
    assert "modified" in problems[0]
    assert "last_folder" in problems[0]      # added
    assert "theme" in problems[0]            # removed


def test_guard_reports_a_value_change_with_the_same_keys(tmp_path):
    """The `series.user` shape: one key, overwritten. No key set change at all."""
    guard, directory = _guard_on(tmp_path)
    watched = directory / "com.example.Watched.plist"
    watched.write_bytes(plistlib.dumps({"username": "real"}))
    guard.snapshot()

    watched.write_bytes(plistlib.dumps({"username": "clobbered"}))
    problems = guard.diff()

    assert len(problems) == 1
    assert "same key set, changed values" in problems[0]


def test_guard_reports_a_newly_created_domain(tmp_path):
    """A per-series domain is created on first write, so an appearing file is a
    failure and not just a changed one.
    """
    guard, directory = _guard_on(tmp_path)
    guard.snapshot()
    (directory / "com.example.Watched-someseries.plist").write_bytes(
        plistlib.dumps({"autobackup": False})
    )
    problems = guard.diff()
    assert len(problems) == 1
    assert "created" in problems[0]
    assert "autobackup" in problems[0]


def test_guard_reports_a_deleted_file(tmp_path):
    guard, directory = _guard_on(tmp_path)
    watched = directory / "com.example.Watched.plist"
    watched.write_bytes(plistlib.dumps({"username": "real"}))
    guard.snapshot()
    watched.unlink()
    assert any("deleted" in p for p in guard.diff())


def test_guard_ignores_files_outside_the_domain_family(tmp_path):
    guard, directory = _guard_on(tmp_path)
    guard.snapshot()
    (directory / "com.apple.something.plist").write_bytes(plistlib.dumps({"a": 1}))
    assert guard.diff() == []


def test_guard_matches_the_domain_case_insensitively(tmp_path):
    """macOS treats `com.KHLab.PyReconstruct` and `com.khlab.PyReconstruct` as
    one store, so the watcher has to as well or half the family is unwatched.
    """
    guard, directory = _guard_on(tmp_path)
    guard.snapshot()
    (directory / "COM.EXAMPLE.watched-x.plist").write_bytes(plistlib.dumps({"a": 1}))
    assert any("created" in p for p in guard.diff())


def test_guard_catches_a_real_qsettings_write(tmp_path):
    """End to end, through Qt rather than a hand-written file.

    The rogue write is a real `QSettings` write to a real settings file that the
    guard is watching. Pointed at `tmp_path` instead of the developer's
    Preferences directory, because demonstrating the guard by committing a test
    that writes the real store would be the fourth incident.
    """
    import PySide6.QtCore as qtcore

    directory = tmp_path / "rogue"
    directory.mkdir()
    real = qi._real_qsettings
    real.setPath(real.Format.IniFormat, real.Scope.UserScope, str(directory))
    try:
        settings = real(
            real.Format.IniFormat, real.Scope.UserScope, "Watched", "Domain"
        )
        target = os.path.dirname(settings.fileName())
        guard = qi.RealSettingsGuard(target, "Domain")
        guard.snapshot()

        settings.setValue("username", "clobbered-by-a-test")
        settings.sync()

        problems = guard.diff()
        assert problems, f"guard missed a real write to {settings.fileName()}"
        assert "username" in problems[0]
    finally:
        # restore the session's isolation root, or every later test in this
        # session would resolve into tmp_path and the guard would be armed on it
        real.setPath(
            real.Format.IniFormat, real.Scope.UserScope, qi.isolation_root
        )
        assert _under_root(qi.resolved_path())
    del qtcore


def test_the_session_guard_is_armed_on_the_real_store():
    """The session-scoped guard watches the real domain family, not a copy.

    Cheap, and it is the assertion that would have caught the guard being
    pointed at the isolation root by accident, which would make it always pass.
    """
    assert qi.guard is not None
    assert not _under_root(qi.guard.directory)
    assert qi.guard.prefix.lower().endswith("pyreconstruct")
    assert qi.guard.baseline is not None


# --- production is untouched --------------------------------------------------


def test_production_still_resolves_to_the_real_settings_location():
    """A real user's settings must still be the real ones.

    Has to run outside this process: in here the redirect is installed on
    purpose, so the check would be measuring the fixture. The subprocess loads
    no `conftest.py`, constructs the app's own domain, and only *reads*
    `fileName()`/`format()`, which touch nothing.
    """
    script = textwrap.dedent(
        """
        import os, sys
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings

        s = QSettings("KHLab", "PyReconstruct")
        # read-only: fileName() and format() do not write
        print("FORMAT", s.format().name)
        print("PATH", s.fileName())
        print("NATIVE", QSettings.Format.NativeFormat.name)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    out = dict(
        line.split(" ", 1) for line in result.stdout.strip().splitlines()
    )
    assert out["FORMAT"] == out["NATIVE"], (
        "production should use the platform's native settings backend, got "
        f"format {out['FORMAT']}"
    )
    assert not _under_root(out["PATH"]), (
        "the isolation root leaked into a process that does not load the suite's "
        f"conftest: {out['PATH']}"
    )
    # and it is the app's own domain, wherever the platform puts it
    assert "PyReconstruct" in out["PATH"]


def test_isolation_needs_the_suite_conftest_to_be_active():
    """The redirect is test-only: importing the app does not install it.

    The companion to the test above. Imports a module that builds a `QSettings`
    and checks it did not somehow acquire the isolated class, which is what
    would happen if the mechanism had been put in the package rather than in
    `tests/`.
    """
    script = textwrap.dedent(
        """
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyReconstruct.modules.gui.dialog import file_dialog
        print("CLASSNAME", file_dialog.QSettings.__name__)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "CLASSNAME QSettings" in result.stdout, result.stdout
    assert "Isolated" not in result.stdout
