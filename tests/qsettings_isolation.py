"""Point the whole suite's `QSettings` at a throwaway location, and guard the
real one.

Why this module exists. Running the suite used to edit the developer's own
application preferences, through three separate routes in one night:

1. A fixture called `QSettings.clear()` and rewrote `allKeys()`. On macOS
   `NativeFormat` is `NSUserDefaults`, and `allKeys()` on an app domain also
   returns the *global* domain, so the rewrite copied 67 system defaults
   (`Apple*`, `com/apple/trackpad/*`) into the app's own plist.
2. A test assigned `series.user`. That setter is `setOption("username", value)`,
   which writes the machine-wide scope, and it overwrote the stored username.
3. `MainWindow.openSeries` calls `addToRecentSeries`, so every `main_window`
   fixture build prepended a pytest `tmp_path` to `recently_opened_series`, and
   left `last_folder` pointing at a directory that no longer exists.

Snapshot-and-restore fixtures fix the routes they enumerate and nothing else.
This is a redirect instead: it applies to the whole session, no test opts in,
and a route added tomorrow is covered without anyone remembering it exists.

## The two obvious mechanisms do not work on macOS. Measured, not assumed.

With `PySide6==6.5.2` on macOS 27, for `QSettings("KHLab", "PyReconstruct")`:

- `QStandardPaths.setTestModeEnabled(True)` moves `AppConfigLocation` to
  `~/.qttest/Library/Preferences`, and `QSettings` ignores it completely:
  `fileName()` still returns `~/Library/Preferences/com.khlab.PyReconstruct.plist`.
  `NativeFormat` goes through `CFPreferences`, which does not consult
  `QStandardPaths`.
- `QSettings.setDefaultFormat(IniFormat)` plus
  `QSettings.setPath(IniFormat, UserScope, tmp)` does change `defaultFormat()`,
  and the two-argument organization/application constructor still comes back
  `NativeFormat` with the same real path. `setPath` is documented as having no
  effect on `NativeFormat`, and on this platform that constructor stays native.

What does work, measured the same way: the four-argument
`QSettings(IniFormat, UserScope, org, app)` constructor honors `setPath`, giving
`<tmp>/KHLab/PyReconstruct.ini` with `format()` reporting `IniFormat`. So the
redirect is a `QSettings` subclass that rewrites any construction into that
form, installed over the name `QSettings` itself.

## Where the substitution is installed

`PySide6.QtCore.QSettings` is rebound, which covers every deferred import
(`QSettingsStore._settings` imports inside the method) and every module imported
after this one. Modules that already bound the name at import time are swept out
of `sys.modules` and rebound individually, which is what catches
`gui/main/main_window.py`: it gets `QSettings` through
`from .main_imports import *`, so the name lives in its namespace, not in
`main_imports`' alone.

Installation happens at *import* time rather than in a fixture. A fixture runs
after collection, and collection imports every test module; import-time keeps
the window closed. `tests/conftest.py` imports this module immediately after it
defaults `QT_QPA_PLATFORM`, for the same ordering reason that line has.

## The guard

Redirecting is only half of it. Incident four will arrive by a route this
module does not anticipate: a test that reaches the real class through a
reference it captured earlier, a `monkeypatch` teardown that restores the real
name, a subprocess. So `RealSettingsGuard` fingerprints the real settings
files on disk at session start and re-checks at session end, and fails the run
if anything changed or appeared. It watches the whole domain family, not one
file, so a new per-series domain (`PyReconstruct-<code>`) is caught too.
"""

import atexit
import hashlib
import os
import plistlib
import shutil
import sys
import tempfile

import pytest

# The real domain this whole module exists to protect. Both scopes that
# `QSettingsStore` addresses live under it: the global one is exactly `APP`, and
# a per-series one is `f"{APP}-{code}"`.
ORG = "KHLab"
APP = "PyReconstruct"

# Populated by `_install()`; None means Qt was not importable and there is
# nothing to isolate (see the ImportError branch).
isolation_root = None
guard = None

_real_qsettings = None
_isolated_qsettings = None
_rebound_modules = ()


# --- fingerprinting the real store -------------------------------------------


def _digest(path):
    """sha256 of a file's bytes, or None if it does not exist."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


def _keys(path):
    """Best-effort key set of a settings file, for a useful failure message.

    Only used to describe a change that has already been detected by digest, so
    an unparseable file is not an error: the digest is the assertion, this is
    the explanation. `plistlib` covers macOS `NativeFormat`; the `.conf`/`.ini`
    backends are parsed loosely enough that a section header does not matter.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return set()
    try:
        parsed = plistlib.loads(raw)
    except Exception:
        pass
    else:
        return set(parsed) if isinstance(parsed, dict) else set()
    found = set()
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith((";", "#", "[")) or "=" not in line:
            continue
        found.add(line.split("=", 1)[0].strip())
    return found


class RealSettingsGuard:
    """Fail the session if the real settings files changed during it.

    Watches a directory for every file whose name starts with `prefix`, which
    is the whole domain family rather than a single file: on macOS that is
    `com.khlab.PyReconstruct.plist` plus every `...-<series code>.plist`. A file
    appearing is as much a failure as a file changing, because a per-series
    domain is created on first write and the suite opens series it invented.

    Deliberately not `QSettings`-based. Reading the real store through the real
    class to check on it would reintroduce exactly the reference this module is
    trying to keep out of the suite, and a file digest is a stronger claim than
    an enumerated key list anyway: it catches a key nobody thought to list.

        Params:
            directory (str): where the real settings files live.
            prefix (str): the filename prefix identifying the domain family.
    """

    def __init__(self, directory, prefix):
        self.directory = directory
        self.prefix = prefix
        self.baseline = None
        # captured alongside the baseline digests, while the baseline bytes are
        # still the bytes on disk, so a failure can name the offending keys
        self.baseline_keys = {}

    def _matches(self):
        """Absolute paths of every watched file currently on disk."""
        try:
            names = os.listdir(self.directory)
        except OSError:
            return []
        # macOS treats the domain case-insensitively (`com.KHLab.PyReconstruct`
        # and `com.khlab.PyReconstruct` are one store), so match that way.
        low = self.prefix.lower()
        return sorted(
            os.path.join(self.directory, name)
            for name in names
            if name.lower().startswith(low)
        )

    def fingerprint(self):
        """A {path: sha256} map of the watched files."""
        return {path: _digest(path) for path in self._matches()}

    def snapshot(self):
        """Record the current fingerprint and key sets as the baseline."""
        self.baseline = self.fingerprint()
        self.baseline_keys = {path: _keys(path) for path in self._matches()}
        return self.baseline

    def diff(self):
        """Human-readable descriptions of every change since `snapshot()`.

        Empty list means the real store is untouched.
        """
        if self.baseline is None:  # pragma: no cover - guarded by the caller
            raise RuntimeError("snapshot() must be called before diff()")
        now = self.fingerprint()
        problems = []
        for path in sorted(set(self.baseline) | set(now)):
            before = self.baseline.get(path)
            after = now.get(path)
            if before == after:
                continue
            if before is None:
                problems.append(
                    f"created: {path} (keys: {sorted(_keys(path)) or 'none'})"
                )
            elif after is None:
                problems.append(f"deleted: {path}")
            else:
                was = self.baseline_keys.get(path, set())
                now_keys = _keys(path)
                detail = []
                if now_keys - was:
                    detail.append(f"keys added: {sorted(now_keys - was)}")
                if was - now_keys:
                    detail.append(f"keys removed: {sorted(was - now_keys)}")
                if not detail:
                    detail.append("same key set, changed values")
                problems.append(f"modified: {path} ({'; '.join(detail)})")
        return problems


# --- the redirect -------------------------------------------------------------


def _build_isolated_class(qsettings, root):
    """Return a `QSettings` subclass that can only address `root`.

    Every construction is rewritten to the four-argument
    `(IniFormat, UserScope, org, app)` form, which is the only one measured to
    honor `setPath` on macOS. The organization and application names are kept as
    the caller passed them, so a per-series scope stays a distinct file and the
    isolated tree mirrors the real one; only the location changes.
    """
    ini = qsettings.Format.IniFormat
    user_scope = qsettings.Scope.UserScope

    class IsolatedQSettings(qsettings):
        """A `QSettings` that cannot reach the real user settings."""

        #: where every instance of this class stores its values
        isolation_root = root

        def __init__(self, *args, **kwargs):
            from PySide6.QtCore import QObject

            parent = kwargs.get("parent") or next(
                (a for a in args if isinstance(a, QObject)), None
            )
            strings = [a for a in args if isinstance(a, str)]
            formats = [a for a in args if isinstance(a, qsettings.Format)]

            if len(formats) == 1 and len(strings) == 1 and args[0] is strings[0]:
                # QSettings(fileName, format): an explicit file, not a domain.
                # Nothing in this repository uses it; redirect the basename into
                # the isolation root rather than trust a path from a test.
                target = os.path.join(root, "explicit", os.path.basename(strings[0]))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                super().__init__(target, ini)
            else:
                organization = strings[0] if strings else ORG
                application = strings[1] if len(strings) > 1 else ""
                super().__init__(ini, user_scope, organization, application)

            if parent is not None:
                self.setParent(parent)

    return IsolatedQSettings


def _rebind(module_names_holding, replacement):
    """Rebind an already-imported `QSettings` name in every module that has one.

    `from PySide6.QtCore import QSettings` copies the class into the importing
    module's namespace, so patching `PySide6.QtCore` alone leaves those bindings
    pointing at the real class. Star imports count: `main_window.py` gets the
    name via `from .main_imports import *`, so it holds its own reference.
    """
    rebound = []
    for name, module in list(sys.modules.items()):
        if module is None:
            continue
        try:
            current = getattr(module, "QSettings", None)
        except Exception:  # pragma: no cover - defensive, module __getattr__
            continue
        if current is module_names_holding:
            try:
                setattr(module, "QSettings", replacement)
            except Exception:  # pragma: no cover - immutable module
                continue
            rebound.append(name)
    return tuple(rebound)


def _install():
    """Redirect `QSettings` and arm the guard. Called once, at import time.

    Returns False when Qt is not importable, which is a supported state: with no
    `PySide6` there is no `QSettings` route to isolate, and the Qt-free core
    tests still run.
    """
    global isolation_root, guard, _real_qsettings, _isolated_qsettings
    global _rebound_modules

    try:
        import PySide6.QtCore as qtcore
    except ImportError:
        return False

    _real_qsettings = qtcore.QSettings

    # Resolve the real locations *before* patching, so the guard watches where
    # the app actually stores things on this platform rather than a guess.
    real_file = _real_qsettings(ORG, APP).fileName()
    directory = os.path.dirname(real_file)
    prefix = os.path.splitext(os.path.basename(real_file))[0]
    guard = RealSettingsGuard(directory, prefix)
    guard.snapshot()

    isolation_root = tempfile.mkdtemp(prefix="pyrecon-qsettings-")
    # One directory per session would otherwise accumulate forever, and the
    # session-end guard message quotes the path, so this has to run after it:
    # atexit is later than any pytest hook.
    atexit.register(shutil.rmtree, isolation_root, ignore_errors=True)

    # setPath is what the four-argument IniFormat constructor honors.
    ini = _real_qsettings.Format.IniFormat
    _real_qsettings.setPath(ini, _real_qsettings.Scope.UserScope, isolation_root)
    _real_qsettings.setPath(ini, _real_qsettings.Scope.SystemScope, isolation_root)
    # Not sufficient on macOS (see the module docstring), but it is what makes
    # the plain two-argument constructor land in the isolation root on the
    # platforms where it is honored, so the redirect holds even if the subclass
    # is somehow bypassed.
    _real_qsettings.setDefaultFormat(ini)

    _isolated_qsettings = _build_isolated_class(_real_qsettings, isolation_root)
    _rebound_modules = _rebind(_real_qsettings, _isolated_qsettings)
    qtcore.QSettings = _isolated_qsettings

    # Refuse to run unisolated. A silent failure here is the whole problem this
    # module was written about, so it is an exception at collection time.
    verify_isolated()
    return True


def resolved_path(organization=ORG, application=APP):
    """Where a `QSettings(organization, application)` built now would store."""
    import PySide6.QtCore as qtcore

    return qtcore.QSettings(organization, application).fileName()


def verify_isolated():
    """Raise unless the live `QSettings` name resolves inside the isolation root.

    Checks the global scope and a per-series scope, since they are separate
    files and a partial redirect is worse than none: it looks safe.
    """
    import PySide6.QtCore as qtcore

    if qtcore.QSettings is not _isolated_qsettings:
        raise RuntimeError(
            "PySide6.QtCore.QSettings is not the isolated subclass any more, so "
            "the suite can reach the real user settings. Something rebound it "
            f"(now {qtcore.QSettings!r})."
        )
    for application in (APP, f"{APP}-isolationselfcheck"):
        path = os.path.abspath(resolved_path(ORG, application))
        if not path.startswith(os.path.abspath(isolation_root)):
            raise RuntimeError(
                f"QSettings({ORG!r}, {application!r}) resolves to {path}, which "
                f"is outside the isolation root {isolation_root}. Refusing to "
                "run: the suite would write the real user settings."
            )


# Import-time, deliberately. See the module docstring.
installed = _install()


# --- the session fixture ------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def isolated_qsettings():
    """Assert the isolation held and the real settings are untouched.

    Autouse and session-scoped, so it is not something a test opts into. Setup
    re-checks the redirect (a `monkeypatch` of `PySide6.QtCore` in some earlier
    test could have restored the real class on teardown); teardown runs the
    guard, which is the half that catches a route this module did not predict.

    Yields the isolation root, for the isolation tests themselves.
    """
    if not installed:
        yield None
        return

    verify_isolated()
    yield isolation_root
    verify_isolated()

    problems = guard.diff()
    assert not problems, (
        "the test session modified the real application settings under\n"
        f"  {guard.directory}/{guard.prefix}*\n"
        "which is the developer's own preference store, not a test fixture.\n\n"
        + "\n".join(f"  - {p}" for p in problems)
        + "\n\nEvery settings route in the suite is supposed to be redirected to\n"
        f"  {isolation_root}\n"
        "so this is either a reference to the real QSettings class captured "
        "before\ntests/qsettings_isolation.py was imported, or a subprocess that "
        "does not\nload tests/conftest.py. See that module's docstring."
    )
