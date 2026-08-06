"""A small confetti burst, used as positive feedback for a completed action.

One public function, ``burst_confetti(anchor)``. It spawns a dozen small
coloured dots over the window containing ``anchor``, throws them out and down in
a short arc, fades them out and deletes them. It is decoration: it returns a
list of the widgets it made so a caller (and the suite) can see what it did, and
nothing about the application's behaviour depends on the result.

Three implementation choices are worth stating, because the obvious versions of
each do not work.

**The particles are children of the window, not of the anchor.** A Qt child
widget is clipped to its parent's rectangle, so particles parented to the button
they celebrate would be invisible the moment they left it -- which is the whole
animation. They are parented to ``anchor.window()`` and positioned in that
widget's coordinates instead, and they carry ``WA_TransparentForMouseEvents`` so
that a widget briefly underneath one stays clickable.

**Opacity is a custom property painted by hand, not ``windowOpacity``.**
``QWidget.windowOpacity`` applies to top-level windows only; setting it on a
child widget is accepted and does nothing, so an animation driving it would run
its full duration and fade nothing. ``QGraphicsOpacityEffect`` does work on a
child, but installing a graphics effect per particle is a heavier object graph
than a fade needs. ``ConfettiParticle`` therefore carries its own ``opacity``
Qt property and applies it in ``paintEvent`` via ``QPainter.setOpacity``, which
is a few lines and animates like any other property.

**Nothing keeps a registry of live particles.** Each particle owns its own
animation group (the group is parented to the particle), and the group's
``finished`` deletes the particle, which takes the group with it. So the only
strong reference to either is Qt's parent-child ownership: a finished burst
cleans itself up, and a burst whose window closes mid-flight is destroyed with
the window. A module-level list of in-flight particles would be a second owner
and one more thing to get wrong -- and it is the thing that leaks if a burst is
interrupted.
"""

import random

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    Qt,
)
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


# Deliberately a short, unbranded, high-contrast set rather than the trace
# palette from `colors.py`: this is chrome, and colouring it from the series'
# own colours would read as though it meant something about the data.
CONFETTI_COLORS = (
    "#e6194b", "#3cb44b", "#ffe119", "#4363d8",
    "#f58231", "#911eb4", "#42d4f4", "#f032e6",
)

PARTICLE_COUNT = 12          # "a small animation": enough to read as a burst, not a shower
PARTICLE_SIZE_RANGE = (4, 8)  # pixels, square bounding box
DURATION_RANGE = (600, 900)   # milliseconds, per particle


class ConfettiParticle(QWidget):
    """One dot. Owns its colour and its animatable ``opacity``.

    Public only so that a test can count the things a burst created and confirm
    they are gone again; nothing outside this module constructs one.
    """

    def __init__(self, color, size: int, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._opacity = 1.0
        self.resize(size, size)
        # A particle must never intercept a click meant for what is underneath
        # it -- the burst passes back over the button that started it.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)

    def getOpacity(self) -> float:
        return self._opacity

    def setOpacity(self, value: float):
        self._opacity = float(value)
        self.update()

    # The name the animation below drives, as b"opacity".
    opacity = Property(float, getOpacity, setOpacity)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        # Clamped rather than trusted: an easing curve that overshoots (any of
        # the Back/Elastic family) hands setOpacity values outside 0..1, and
        # QPainter treats those as undefined.
        painter.setOpacity(max(0.0, min(1.0, self._opacity)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect())


def burst_confetti(anchor: QWidget, count: int = PARTICLE_COUNT, rng=None) -> list:
    """Throw ``count`` particles from the centre of ``anchor``.

    Returns the particles, which are already running. ``rng`` takes a seeded
    ``random.Random`` when a caller wants the same burst twice; the default is
    the module-level generator.

    Returns an empty list rather than raising if there is nothing to draw on --
    a widget with no window, which is what an un-parented widget looks like
    before it is shown.
    """
    if rng is None:
        rng = random

    host = anchor.window()
    if host is None:
        return []

    # `anchor.mapTo(host, ...)` and not `host.mapFrom(anchor, ...)`. The two read
    # as inverses and are not: both take an *ancestor* as the argument, so the
    # second one asks Qt to walk up from `host` until it reaches `anchor`, which
    # it never does. That is not an exception -- PySide6 6.5.2 segfaults on it.
    origin = anchor.mapTo(host, anchor.rect().center())

    particles = []
    for _ in range(count):
        size = rng.randint(*PARTICLE_SIZE_RANGE)
        particle = ConfettiParticle(rng.choice(CONFETTI_COLORS), size, host)

        start = QPoint(origin.x() - size // 2, origin.y() - size // 2)

        # Out and up to an apex, then out further and down past the start: the
        # arc a handful of thrown confetti makes. Sideways spread is signed, so
        # the burst goes both ways; vertical is not, because gravity is not.
        spread = rng.randint(18, 55) * rng.choice((-1, 1))
        rise = rng.randint(22, 45)
        fall = rng.randint(30, 60)
        duration = rng.randint(*DURATION_RANGE)

        move = QPropertyAnimation(particle, b"pos")
        move.setDuration(duration)
        move.setStartValue(start)
        move.setKeyValueAt(0.35, QPoint(start.x() + spread // 2, start.y() - rise))
        move.setEndValue(QPoint(start.x() + spread, start.y() + fall))
        move.setEasingCurve(QEasingCurve.OutQuad)

        # Held at full opacity for the first half, so the burst is legible
        # before it starts leaving; all of the fade happens on the way down.
        fade = QPropertyAnimation(particle, b"opacity")
        fade.setDuration(duration)
        fade.setStartValue(1.0)
        fade.setKeyValueAt(0.5, 1.0)
        fade.setEndValue(0.0)

        group = QParallelAnimationGroup(particle)   # parented: see the module docstring
        group.addAnimation(move)
        group.addAnimation(fade)
        group.finished.connect(particle.deleteLater)

        particle.move(start)
        particle.show()
        particle.raise_()
        group.start()

        particles.append(particle)

    return particles
