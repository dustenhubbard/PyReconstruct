"""Regression test for ``modules_available`` crashing on a native-library failure.

``modules_available`` probes each module with ``__import__`` inside a ``try``
that caught ``ModuleNotFoundError`` only. That is the wrong exception for a
module which is a wrapper around a native library: ``import cairosvg`` runs
``cairocffi``'s ``dlopen`` at import time and raises ``OSError:
no library called "cairo-2" was found`` on a machine with the wheel installed
and no system Cairo. The ``OSError`` escaped the guard, out of
``MainWindow.exportSectionPNG`` (``main_window.py``, ``File > Export > PNG``)
and into ``customExcepthook`` as a crash report.

Declaring ``cairosvg`` is what made that reachable: the ``launch/*`` scripts run
``pip install -r requirements.txt`` on every startup, so every user now has the
Python package, while nothing ships native Cairo on macOS or Windows. Before the
declaration the same machine had no ``cairosvg`` at all, got ``ModuleNotFoundError``,
and saw the handled install prompt.

The remedies are different in kind, so the message has to be too: a missing
*package* is fixed by the pip install ``modules_available`` offers, a missing
*native library* is not, and offering the install for it sends the user down a
path that cannot work.

CI installs ``libcairo2``, so the real ``cairosvg`` import succeeds there and
cannot exercise this branch. These tests inject the failure with a stub module
instead, which also keeps them platform-independent.
"""

import sys

import pytest

from PyReconstruct.modules.backend.imports import mod_imports


@pytest.fixture
def captured(monkeypatch):
    """Route both dialogs into a dict instead of onto a screen."""
    seen = {"notes": [], "confirms": []}

    monkeypatch.setattr(mod_imports, "note", lambda msg: seen["notes"].append(msg))

    def fake_confirm(msg, *a, **k):
        seen["confirms"].append(msg)
        return False  # decline the install; the accept path shells out to pip

    monkeypatch.setattr(mod_imports, "notifyConfirm", fake_confirm)
    return seen


def _install_stub(monkeypatch, name, exc):
    """Make ``__import__(name)`` raise ``exc``.

    A real ``sys.modules`` entry cannot express "raises on import", so this
    patches the finder the only way that works from a test: a meta path hook
    whose loader raises. ``modules_available`` calls the builtin ``__import__``,
    so the exception has to come out of the import machinery itself rather than
    out of a monkeypatched name.
    """

    class _Loader:
        @staticmethod
        def create_module(spec):
            raise exc

        @staticmethod
        def exec_module(module):  # pragma: no cover - create_module raises first
            raise exc

    class _Finder:
        @staticmethod
        def find_spec(fullname, path=None, target=None):
            if fullname != name:
                return None
            from importlib.machinery import ModuleSpec

            return ModuleSpec(fullname, _Loader())

    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_Finder()] + list(sys.meta_path))


def test_native_library_oserror_does_not_propagate(monkeypatch, captured):
    """The whole point: an OSError from the probe is reported, not raised.

    Without the widened ``except`` this test does not fail an assertion -- it
    errors with the OSError, exactly as ``exportSectionPNG`` did.
    """
    _install_stub(monkeypatch, "cairosvg", OSError('no library called "cairo-2" was found'))

    assert mod_imports.modules_available(["svgwrite", "cairosvg"], notify=False) is False


def test_native_library_message_names_the_real_remedy(monkeypatch, captured):
    """The OSError path must name the system library, and must not offer pip."""
    _install_stub(monkeypatch, "cairosvg", OSError('no library called "cairo-2" was found'))

    assert mod_imports.modules_available("cairosvg", notify=True) is False

    assert not captured["confirms"], (
        "a pip install was offered for a missing *native* library, which "
        "reinstalling the Python package cannot fix"
    )
    assert len(captured["notes"]) == 1
    message = captured["notes"][0]
    assert "libcairo2" in message
    assert "brew install cairo" in message
    assert "libcairo-2.dll" in message
    assert 'no library called "cairo-2" was found' in message
    # The pip prompt's wording must not leak into this branch.
    assert "install them into your current environment" not in message


def test_missing_package_still_offers_the_pip_install(monkeypatch, captured):
    """The ModuleNotFoundError path is untouched: that remedy does work."""
    _install_stub(
        monkeypatch, "svgwrite", ModuleNotFoundError("No module named 'svgwrite'")
    )

    assert mod_imports.modules_available("svgwrite", notify=True) is False

    assert not captured["notes"], "the native-library notice fired for a missing package"
    assert len(captured["confirms"]) == 1
    assert "svgwrite" in captured["confirms"][0]
    assert "install them into your current environment" in captured["confirms"][0]


def test_both_failures_get_their_own_message(monkeypatch, captured):
    """A mixed batch reports each failure with the remedy that fits it."""
    _install_stub(
        monkeypatch, "svgwrite", ModuleNotFoundError("No module named 'svgwrite'")
    )
    _install_stub(monkeypatch, "cairosvg", OSError('no library called "cairo-2" was found'))

    assert mod_imports.modules_available(["svgwrite", "cairosvg"], notify=True) is False

    assert len(captured["notes"]) == 1
    assert len(captured["confirms"]) == 1
    # The pip prompt lists only what pip can actually install.
    assert "cairosvg" not in captured["confirms"][0]
    assert "svgwrite" in captured["confirms"][0]


def test_importable_modules_still_return_true(captured):
    """The happy path is unchanged -- no dialog, True."""
    assert mod_imports.modules_available(["json", "pathlib"], notify=True) is True
    assert not captured["notes"] and not captured["confirms"]
