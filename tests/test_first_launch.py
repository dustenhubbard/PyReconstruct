"""First-launch UX tests: silent username resolution.

All hermetic and headless -- the QSettings store is injected, so nothing touches
the real user settings or pops a dialog.
"""
import pytest

from PyReconstruct.modules.gui.main import first_launch as F


# ---- fakes ------------------------------------------------------------------
class FakeSettings:
    """A QSettings-shaped dict so the resolver can be tested without Qt I/O."""

    def __init__(self, data=None):
        self._d = dict(data or {})
        self.writes = []

    def value(self, key, default=None):
        return self._d.get(key, default)

    def setValue(self, key, val):
        self._d[key] = val
        self.writes.append((key, val))


class FakeSeries:
    user = None


# ---- username resolution ----------------------------------------------------
def test_resolve_username_uses_saved_name():
    s = FakeSeries()
    settings = FakeSettings({"username": "alice"})
    assert F.resolve_username(settings, s, default_factory=lambda: "oslogin") == "alice"
    assert s.user == "alice"
    assert settings.writes == []  # saved name reused, not rewritten


def test_resolve_username_falls_back_to_os_login_and_persists():
    s = FakeSeries()
    settings = FakeSettings()  # nothing saved
    assert F.resolve_username(settings, s, default_factory=lambda: "oslogin") == "oslogin"
    assert s.user == "oslogin"
    assert settings.writes == [("username", "oslogin")]


@pytest.mark.parametrize("saved", ["", "   ", None, 123, []])
def test_resolve_username_treats_empty_or_nonstring_as_unset(saved):
    settings = FakeSettings({"username": saved})
    assert F.resolve_username(settings, default_factory=lambda: "oslogin") == "oslogin"
    assert settings.writes == [("username", "oslogin")]


def test_resolve_username_default_of_last_resort():
    settings = FakeSettings()
    assert F.resolve_username(settings, default_factory=lambda: "") == "default"
