"""Tests for the autoseg trace-color palette.

Verifies that autoseg import assigns colors from a curated, grayscale-visible
whitelist, deterministically mapped from each label id.
"""

import pytest

from PyReconstruct.modules.backend.autoseg.palette import (
    DEFAULT_AUTOSEG_PALETTE,
    palette_color,
)

# Thresholds separating a usable overlay color from the grayscale background.
# chroma = max(RGB) - min(RGB): distance from the achromatic ("gray") axis.
# value  = max(RGB): overall brightness (guards against near-black tones).
MIN_CHROMA = 60
MIN_VALUE = 120

# Sampling range for id -> color assertions.
SAMPLE_IDS = range(1, 5000)


def _chroma(color):
    return max(color) - min(color)


def _value(color):
    return max(color)


# --- palette content -------------------------------------------------------


def test_palette_is_nonempty_and_reasonable_size():
    assert 8 <= len(DEFAULT_AUTOSEG_PALETTE) <= 24


def test_palette_entries_are_rgb_int_triples_in_range():
    for color in DEFAULT_AUTOSEG_PALETTE:
        assert len(color) == 3
        for channel in color:
            assert isinstance(channel, int)
            assert 0 <= channel <= 255


def test_palette_has_no_near_gray_or_dark_colors():
    """Every whitelist color must sit off the gray axis and not be too dark."""
    for color in DEFAULT_AUTOSEG_PALETTE:
        assert _chroma(color) >= MIN_CHROMA, f"{color} is too close to gray"
        assert _value(color) >= MIN_VALUE, f"{color} is too dark"


def test_palette_entries_are_distinct():
    assert len(set(DEFAULT_AUTOSEG_PALETTE)) == len(DEFAULT_AUTOSEG_PALETTE)


# --- deterministic id -> color mapping -------------------------------------


def test_mapping_is_deterministic():
    """Same id (and seed) always yields the same color."""
    for label_id in SAMPLE_IDS:
        assert palette_color(label_id) == palette_color(label_id)


def test_mapping_matches_known_reference_values():
    """Pin the exact id -> color mapping so the hash cannot drift silently."""
    expected = {
        0: (230, 25, 75),
        1: (145, 30, 180),
        2: (188, 246, 12),
        3: (255, 225, 25),
        5: (245, 130, 49),
        42: (230, 25, 75),
        100: (70, 240, 240),
        1000: (240, 50, 230),
    }
    for label_id, color in expected.items():
        assert palette_color(label_id) == color


def test_every_produced_color_is_from_the_whitelist():
    whitelist = set(DEFAULT_AUTOSEG_PALETTE)
    for seed in (0, 1, 7, 12345):
        for label_id in SAMPLE_IDS:
            assert palette_color(label_id, seed=seed) in whitelist


def test_produced_colors_are_never_near_gray():
    for label_id in SAMPLE_IDS:
        color = palette_color(label_id)
        assert _chroma(color) >= MIN_CHROMA
        assert _value(color) >= MIN_VALUE


def test_mapping_covers_whole_palette():
    """A good hash should reach every palette entry over enough ids."""
    seen = {palette_color(label_id) for label_id in SAMPLE_IDS}
    assert seen == set(DEFAULT_AUTOSEG_PALETTE)


def test_consecutive_ids_are_scattered():
    """Consecutive label ids should not all collapse to one color."""
    colors = [palette_color(label_id) for label_id in range(1, 13)]
    assert len(set(colors)) >= len(DEFAULT_AUTOSEG_PALETTE) // 2


# --- seed behavior ---------------------------------------------------------


def test_seed_reshuffles_assignment():
    """Changing the seed changes at least some id -> color assignments."""
    differ = any(
        palette_color(label_id, seed=0) != palette_color(label_id, seed=1)
        for label_id in SAMPLE_IDS
    )
    assert differ


def test_seed_is_still_deterministic():
    for label_id in SAMPLE_IDS:
        assert palette_color(label_id, seed=99) == palette_color(label_id, seed=99)


# --- override / fallback ---------------------------------------------------


def test_empty_or_none_palette_falls_back_to_default():
    """An empty override (the shipped option default) uses the built-in palette."""
    assert palette_color(3, palette=None) == palette_color(3)
    assert palette_color(3, palette=[]) == palette_color(3)


def test_custom_palette_is_respected():
    custom = [(1, 2, 3), (4, 5, 6)]
    for label_id in SAMPLE_IDS:
        assert palette_color(label_id, palette=custom) in custom


def test_return_type_is_int_tuple():
    color = palette_color(7)
    assert isinstance(color, tuple)
    assert all(isinstance(channel, int) for channel in color)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
