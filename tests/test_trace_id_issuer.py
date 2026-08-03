"""The trace-id issuer, the base62 codec, and the frozen `tid-v1` derivation.

These tests are the pin on a decision that cannot be taken back. The derivation
in `datatypes/trace_id.py` is declared frozen: if it moves, every trace that
already carries a derived id acquires a different identity, in every series, with
no way to tell that it happened. So the golden values below are not
housekeeping.

**Updating a golden id in this file is a deliberate act.** It is correct only
when the version string moves with it (`tid-v1` -> `tid-v2`) and the old
derivation stays in the code for the ids already issued under it. A green suite
after editing a golden and leaving the version alone means the pin has been
disabled, not satisfied.

Nothing here touches a `.jser`, a `QSettings` domain, or Qt. The whole module is
the Qt-free core.
"""
import json

import pytest

from PyReconstruct.modules.datatypes.flag import possible_chars
from PyReconstruct.modules.datatypes.trace_id import (
    DERIVATION_MAX_SALT,
    TRACE_ID_ALPHABET,
    TRACE_ID_BITS,
    TRACE_ID_LENGTH,
    TRACE_ID_VERSION,
    TraceIDIssuer,
    decodeTraceID,
    deriveTraceID,
    encodeTraceID,
)

## The 8-field stored row shape, as `Trace.getList(include_name=False)` writes
## it: [x, y, color, closed, negative, hidden, fill_mode, tags]. Eight and not
## nine deliberately -- the rows that round-trip a section file are the
## name-less ones (`Section.getDict` passes include_name=False), and the
## derivation takes the contour name as a separate input rather than from the
## row.
ROW8 = [
    [1.25, 3.0, 5.0],
    [2.5, 4.0, 6.0],
    [255, 0, 0],
    True,
    False,
    False,
    ["none", "none"],
    ["a", "b"],
]


# --- the alphabet, and the drift it is allowed to have from Flag's ------------


def test_alphabet_is_the_same_character_set_flags_use():
    """The trace alphabet is a frozen copy of `flag.possible_chars`.

    A copy, not an import, because the derivation must not move when another
    module reorders a constant. This test is the price of that copy: it fails if
    either side changes, so the duplication is reported rather than silent.
    """
    assert TRACE_ID_ALPHABET == "".join(possible_chars)
    assert len(TRACE_ID_ALPHABET) == 62
    assert len(set(TRACE_ID_ALPHABET)) == 62


def test_width_is_the_narrowest_that_holds_the_chosen_bit_count():
    """11 base62 characters, because 62**11 > 2**64 > 62**10.

    The width decision is 64 random bits. Ten characters would not hold them and
    twelve would waste one, so the arithmetic that picked eleven is pinned here
    rather than left in a docstring.
    """
    assert TRACE_ID_BITS == 64
    assert 62 ** TRACE_ID_LENGTH > 2 ** TRACE_ID_BITS
    assert 62 ** (TRACE_ID_LENGTH - 1) < 2 ** TRACE_ID_BITS


# --- the codec ---------------------------------------------------------------


def test_encoding_is_least_significant_digit_first_like_flags():
    """GOLDEN. The digit order is part of the frozen encoding.

    `Flag.deriveID` emits least-significant-first, and matching it means a trace
    id and a flag id are read the same way. Reversing this would silently
    re-identify every derived trace.
    """
    assert encodeTraceID(0) == "A" * TRACE_ID_LENGTH
    assert encodeTraceID(1) == "B" + "A" * (TRACE_ID_LENGTH - 1)
    assert encodeTraceID(61) == "9" + "A" * (TRACE_ID_LENGTH - 1)
    assert encodeTraceID(62) == "AB" + "A" * (TRACE_ID_LENGTH - 2)


def test_encoding_is_fixed_width_and_round_trips():
    for n in (0, 1, 61, 62, 3843, 2 ** 32, 2 ** 63, 2 ** 64 - 1):
        encoded = encodeTraceID(n)
        assert len(encoded) == TRACE_ID_LENGTH
        assert decodeTraceID(encoded) == n


def test_the_largest_representable_bit_pattern_round_trips():
    """GOLDEN. The top of the 64-bit range, spelled out."""
    assert encodeTraceID(2 ** TRACE_ID_BITS - 1) == "PiRKGBkRq8V"
    assert decodeTraceID("PiRKGBkRq8V") == 2 ** TRACE_ID_BITS - 1


def test_a_negative_or_oversized_value_is_refused():
    with pytest.raises(ValueError):
        encodeTraceID(-1)
    with pytest.raises(ValueError):
        encodeTraceID(62 ** TRACE_ID_LENGTH)


def test_a_malformed_id_is_refused_loudly():
    """A wrong length or a character outside the alphabet raises.

    `adopt` leans on this: an id arriving from a file is checked before it is
    entered in the index, so a garbled one is a loud failure rather than a
    permanent bad entry.
    """
    with pytest.raises(ValueError):
        decodeTraceID("tooshort")
    with pytest.raises(ValueError):
        decodeTraceID("A" * (TRACE_ID_LENGTH + 1))
    with pytest.raises(ValueError):
        decodeTraceID("A" * (TRACE_ID_LENGTH - 1) + "-")


# --- the frozen derivation ---------------------------------------------------


def test_derivation_is_frozen():
    """GOLDEN, and the most load-bearing assertion in this file.

    Read the module header before changing this value.
    """
    assert TRACE_ID_VERSION == "tid-v1"
    assert deriveTraceID(12, "dendrite01", ROW8) == "yGjaA0DdBeJ"


def test_derivation_agrees_across_calls_with_no_save_in_between():
    """The whole point of deriving: two reads of one file agree.

    A random id assigned by a migration is stable only once the file is saved
    and only within that copy -- `Flag.deriveID`'s recorded failure. A derived
    one needs no save.
    """
    first = deriveTraceID(7, "axon", ROW8)
    second = deriveTraceID(7, "axon", ROW8)
    assert first == second


def test_derivation_separates_sections_and_contours():
    a = deriveTraceID(7, "axon", ROW8)
    assert deriveTraceID(8, "axon", ROW8) != a
    assert deriveTraceID(7, "axon2", ROW8) != a


def test_the_version_string_is_inside_the_hashed_payload():
    """A future tid-v2 cannot collide with a tid-v1 id from identical content.

    Checked structurally rather than by faking a version: the payload the
    derivation hashes is reconstructed here from the documented recipe and must
    contain the version, and hashing the same recipe with a different version
    must give a different id.
    """
    payload = json.dumps(
        [TRACE_ID_VERSION, 7, "axon", ROW8],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str,
    )
    assert TRACE_ID_VERSION in payload

    import hashlib

    def derive_with_version(version):
        text = json.dumps(
            [version, 7, "axon", ROW8],
            sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str,
        )
        digest = hashlib.blake2b(
            f"0\x00{text}".encode("utf-8"), digest_size=TRACE_ID_BITS // 8
        ).digest()
        return encodeTraceID(int.from_bytes(digest, "big"))

    assert derive_with_version(TRACE_ID_VERSION) == deriveTraceID(7, "axon", ROW8)
    assert derive_with_version("tid-v2") != deriveTraceID(7, "axon", ROW8)


def test_two_identical_rows_in_one_contour_get_two_ids():
    """Salting, and it resolves a real case rather than a theoretical one.

    Two traces on one section can share a contour, a colour and a point list.
    They are still two traces and still need two ids.
    """
    first = deriveTraceID(3, "glia", ROW8)
    second = deriveTraceID(3, "glia", ROW8, taken={first})
    assert first != second
    third = deriveTraceID(3, "glia", ROW8, taken={first, second})
    assert third not in (first, second)


def test_an_exhausted_salt_range_raises_rather_than_going_random():
    """The deliberate deviation from the flag precedent.

    `Flag.deriveID` falls back to `generateID()` -- a random id -- when salting
    is exhausted. A random id produced by a migration is precisely the failure
    that docstring records, so this raises instead. Forced by shrinking the salt
    range to zero, which is the only way to reach the branch.
    """
    import PyReconstruct.modules.datatypes.trace_id as trace_id_module

    original = trace_id_module.DERIVATION_MAX_SALT
    try:
        trace_id_module.DERIVATION_MAX_SALT = 0
        with pytest.raises(RuntimeError):
            deriveTraceID(1, "axon", ROW8)
    finally:
        trace_id_module.DERIVATION_MAX_SALT = original
    assert trace_id_module.DERIVATION_MAX_SALT == DERIVATION_MAX_SALT


def test_a_derived_id_moves_when_the_content_moves():
    """Why a derived id is a birth certificate and not a content address.

    This is the property that disqualifies derivation as an ongoing identity: a
    reshaped trace hashes differently, so "the same trace, edited" would look
    like "a different trace". The store therefore derives once and never again.
    Asserted so the reason is in the suite and not only in a docstring.
    """
    before = deriveTraceID(4, "axon", ROW8)
    reshaped = [list(ROW8[0]) + [7.0], list(ROW8[1]) + [8.0]] + list(ROW8[2:])
    assert deriveTraceID(4, "axon", reshaped) != before


# --- deterministic migration over a whole section ----------------------------


def test_migration_walks_contour_names_in_canonical_sorted_order():
    """Sorted iteration is pinned on the MECHANISM, and here is why.

    The requirement is that two opens of one file agree without a save. Checking
    that by comparing outcomes under two dict orders does not discriminate, and
    the first version of this test did not: the payload carries the contour name,
    so a salt is only ever consumed by rows that share one contour, and rows
    within a contour are always visited by index. Cross-contour order therefore
    changes the result *only* when two different contours derive the same 64-bit
    id -- a 2**-64 event nobody can construct in a test. Verified by mutation:
    replacing `sorted(contours, key=str)` with `contours` left an
    outcome-comparison version of this test green.

    So the iteration order is asserted directly. It is still worth having:
    `sorted(..., key=str)` is the order `Section.getDict` writes, and on the one
    path where order does decide an id it decides it the same way in every
    process.
    """
    import PyReconstruct.modules.datatypes.trace_id as trace_id_module

    seen = []
    real_derive = trace_id_module.deriveTraceID

    def spy(section_number, contour_name, row, taken=()):
        seen.append(contour_name)
        return real_derive(section_number, contour_name, row, taken)

    contours = {"glia": [ROW8], "axon": [ROW8, ROW8], "dendrite": [ROW8]}
    trace_id_module.deriveTraceID = spy
    try:
        issuer = TraceIDIssuer()
        result = issuer.deriveForSection(9, contours)
    finally:
        trace_id_module.deriveTraceID = real_derive

    assert seen == ["axon", "axon", "dendrite", "glia"]
    assert seen == sorted(seen, key=str)
    assert len(set(result.values())) == len(result)


def test_migration_agrees_across_two_independent_runs():
    contours = {"axon": [ROW8, ROW8], "dendrite": [ROW8], "glia": [ROW8]}
    assert (TraceIDIssuer().deriveForSection(9, contours)
            == TraceIDIssuer().deriveForSection(9, contours))


def test_migration_takes_the_series_index_not_the_sections():
    """`taken` is the series', so two sections cannot mint the same id.

    Flags enforce uniqueness per section; traces do not, because a merge crosses
    sections. Two sections whose contours are identical must still produce
    disjoint id sets when they share one issuer.
    """
    contours = {"axon": [ROW8]}
    issuer = TraceIDIssuer()
    first = issuer.deriveForSection(1, contours)
    second = issuer.deriveForSection(1, contours)
    assert set(first.values()).isdisjoint(second.values())
    assert len(issuer.taken) == 2


# --- the issuer --------------------------------------------------------------


def test_issue_returns_distinct_ids_and_records_them():
    issuer = TraceIDIssuer()
    ids = {issuer.issue() for _ in range(200)}
    assert len(ids) == 200
    assert ids <= issuer.taken


def test_issue_refuses_and_reissues_rather_than_handing_out_a_duplicate():
    """Refuse-and-reissue at issue time, forced with a repeating bit source.

    A real 64-bit source does not repeat, so the loop is unobservable in
    production. Driving it with a source that hands out 5, 5, 5, 6 proves the
    refusal is real and not decorative.
    """
    draws = iter([5, 5, 5, 6])
    issuer = TraceIDIssuer(bits_source=lambda: next(draws))
    first = issuer.issue()
    second = issuer.issue()
    assert first == encodeTraceID(5)
    assert second == encodeTraceID(6)


def test_issue_will_not_hand_out_an_id_already_adopted_from_a_file():
    existing = encodeTraceID(99)
    issuer = TraceIDIssuer(taken=[existing], bits_source=iter([99, 100]).__next__)
    assert issuer.issue() == encodeTraceID(100)


def test_a_hopeless_bit_source_raises_instead_of_looping_forever():
    issuer = TraceIDIssuer(bits_source=lambda: 1)
    assert issuer.issue() == encodeTraceID(1)
    with pytest.raises(RuntimeError):
        issuer.issue()


# --- load and merge: detect and report, never adopt silently -----------------


def test_adopt_registers_an_unseen_id():
    issuer = TraceIDIssuer()
    assert issuer.adopt(encodeTraceID(42), "axon") is True
    assert encodeTraceID(42) in issuer.taken
    assert issuer.collisions == ()


def test_adopt_reports_a_clash_by_name_and_refuses_it():
    """The third property of the acceptance bar: reported to the user by name.

    Never silently reissued -- that is the recorded flag failure -- and never
    silently adopted, which is how a merge loses an edit.
    """
    issuer = TraceIDIssuer()
    clashing = encodeTraceID(42)
    assert issuer.adopt(clashing, "axon") is True
    assert issuer.adopt(clashing, "dendrite01") is False
    assert issuer.collisions == ((clashing, "dendrite01"),)


def test_adopt_refuses_a_malformed_id_before_indexing_it():
    issuer = TraceIDIssuer()
    with pytest.raises(ValueError):
        issuer.adopt("nope", "axon")
    assert issuer.taken == frozenset()


# --- on a real series --------------------------------------------------------


def _stored_contours(series):
    """Every section's stored contour rows, as `Section.getDict` writes them.

    Yields (section number, {contour name: [8-field row, ...]}). One Section is
    held at a time, as the application holds them.
    """
    for snum in sorted(series.sections):
        section = series.loadSection(snum)
        yield snum, section.getDict()["contours"]


def test_deriving_over_a_real_series_gives_one_id_per_trace(real_series):
    """The migration, run over every trace of the checked-in series.

    Two independent issuers over the same stored rows must agree exactly --
    which is the property that makes a derived id safe to hand a file that has
    never been saved by this build -- and no id may repeat across the whole
    series, because uniqueness here is series-global rather than per section.
    """
    stored = list(_stored_contours(real_series))
    n_traces = sum(len(rows) for _, contours in stored for rows in contours.values())
    assert n_traces > 0, "the fixture series has no traces to derive ids for"

    first_issuer = TraceIDIssuer()
    second_issuer = TraceIDIssuer()
    first, second = {}, {}
    for snum, contours in stored:
        first[snum] = first_issuer.deriveForSection(snum, contours)
        second[snum] = second_issuer.deriveForSection(snum, contours)

    assert first == second
    assert len(first_issuer.taken) == n_traces
