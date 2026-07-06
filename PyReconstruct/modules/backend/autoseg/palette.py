"""Curated color palette for autoseg-imported traces.

Autoseg import turns each segmentation label id into a trace/object. The color
those traces get needs to stand out against a grayscale EM image, and it needs
to be *stable*: the same label id spans many sections, so every section must
paint it the same color or a single object ends up multicolored.

Design (mirrors how neuroglancer keeps segment colors readable on gray):

* Colors are drawn from a small curated whitelist rather than an arbitrary RGB
  cube. Every entry is high-saturation and high-value, so it sits well off the
  achromatic ("gray") axis and away from near-black tones. That is exactly the
  region of color space a grayscale background cannot camouflage.

* The label id is mapped to a palette entry *deterministically* by hashing the
  id (with an adjustable seed) and indexing into the palette. Determinism is not
  just nice-to-have here: import runs per-section, so a random pick would give
  the same label a different color on each section. Hashing guarantees one label
  id -> one color everywhere, reproducibly across sessions.

* The seed is a global "re-roll" knob (neuroglancer's color-seed idea): bump it
  and the whole id->color assignment shifts, which lets a user break up an
  unlucky case where two touching labels landed on similar colors.

The palette below is the shipped default and is meant to be easy to edit in one
place. It can also be overridden per computer/series via the
``autoseg_color_palette`` and ``autoseg_color_seed`` options (see
``modules/datatypes/default_settings.py``); an empty override falls back to this
default.
"""

# 12 vivid, well-separated hues. Each is high-value and clearly chromatic
# (never a shade of gray and never near-black), so it reads against grayscale
# EM. Values are (R, G, B) integers in 0-255 -- the format Trace expects.
# (Curated from the Trubetskoy "20 distinct colors" set, keeping only the
# vivid, non-gray, non-pale members.)
DEFAULT_AUTOSEG_PALETTE = [
    (230,  25,  75),   # red
    (245, 130,  49),   # orange
    (255, 225,  25),   # yellow
    (188, 246,  12),   # lime
    ( 60, 180,  75),   # green
    (  0, 158, 155),   # teal
    ( 70, 240, 240),   # cyan
    ( 67,  99, 216),   # blue
    (145,  30, 180),   # purple
    (240,  50, 230),   # magenta
    (245, 100, 155),   # rose
    (170, 110, 250),   # violet
]


def _mix(value: int, seed: int) -> int:
    """Deterministically scramble an integer (splitmix64/Murmur3 finalizer).

    Good avalanche so consecutive label ids (1, 2, 3, ...) land on different
    palette entries. Uses only integer arithmetic, so it is independent of
    PYTHONHASHSEED and identical across processes and sessions.
    """
    mask = 0xFFFFFFFFFFFFFFFF
    h = (int(value) ^ int(seed)) & mask
    h = ((h ^ (h >> 33)) * 0xFF51AFD7ED558CCD) & mask
    h = ((h ^ (h >> 33)) * 0xC4CEB9FE1A85EC53) & mask
    h = h ^ (h >> 33)
    return h


def palette_color(label_id, palette=None, seed: int = 0) -> tuple:
    """Return a stable (R, G, B) color for a segmentation label id.

        Params:
            label_id: the segmentation label id (int-like)
            palette: list of (R, G, B) entries; falls back to the shipped
                default when None or empty
            seed (int): re-roll seed; the same id + seed always yields the same
                color, and changing the seed reshuffles the whole assignment
        Returns:
            (tuple): an (R, G, B) integer triple, 0-255, taken from the palette
    """
    if not palette:
        palette = DEFAULT_AUTOSEG_PALETTE
    index = _mix(int(label_id), seed) % len(palette)
    return tuple(int(c) for c in palette[index])
