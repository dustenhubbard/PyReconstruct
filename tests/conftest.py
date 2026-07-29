"""Minimal pytest configuration for the invert-selection / isolate tests.

This is deliberately the smallest harness that makes the accompanying test
module runnable, because this branch is the first thing in the upstream tree to
carry tests at all.

Its one job is to default the Qt platform to ``offscreen``. The modules under
test (``field_widget_2_trace``, ``field_widget_3_object``) import PySide6
widgets at module scope, so collection alone pulls Qt in; without a platform
plugin that can run headless, importing them on a machine with no display is
not reliable. It is a *setdefault*, so an explicit ``QT_QPA_PLATFORM`` in the
environment still wins.

Note what is deliberately NOT here. The tests in this branch never construct a
real widget and never reach a modal dialog: they drive the methods against
duck-typed stubs and against a real ``Series`` loaded from the shipped
``shapes1.jser``. That is why there are no widget fixtures and no dialog
stand-in -- nothing here can block on a modal, so nothing needs to neutralise
one. Tests that build real widgets do need that machinery, and it should arrive
with them rather than being speculatively added now.
"""

import os

# Must run before any test module imports PySide6, which conftest collection
# guarantees: pytest imports this file before it imports any test module.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
