"""One unreadable log row costs only itself, not the whole editors set.

``Series.getEditorsFromHistory`` folds the log's rows into a set of usernames.
``Series.__init__`` calls it exactly when the stored ``editors`` list is empty,
and stores whatever comes back, so what it returns is what the series then
claims about who has worked on it.

It used to wrap the whole read in a bare ``except:``, print "ERROR: corrupt
history" and return an empty set. The parse, though, is row-at-a-time
(``LogSet.fromList`` loops over the rows and calls ``Log.fromStr`` on each), so
a row that arrives whole and will not read says nothing about the rows around
it -- and a union is precisely the shape where dropping the file to save one
row is the wrong trade. The reproduction is one line long: a legacy object name holding ``", "``,
the same pair ``Log.fromStr`` splits on (see
``tests/test_contour_name_collision.py`` for why such names exist and why the
log is not repointed away from them), shifts every field after it and raises on
the section range. Every OTHER user's well-formed row in the same file went with
it.

Now ``fromList`` takes ``skip_corrupt``, ``getFullHistory`` passes it through,
and ``getEditorsFromHistory`` asks for it. What is pinned here:

* the regression itself -- a good row for one user survives a bad row for
  another (``test_one_bad_row_no_longer_costs_another_user_their_entry``);
* both halves of the handler, not just one. The rows above fail in
  ``Log.fromStr`` (``ValueError``); a row that stops partway through with
  nothing after it fails in ``fromList``'s continuation join instead
  (``IndexError``), and is recovered the same way
  (``test_a_truncated_final_row_costs_only_itself``);
* the loss is reported rather than swallowed: the dropped rows are on the
  returned set as ``skipped_rows`` and a count is printed;
* the narrowing is real -- an error that is *not* a parse failure still
  propagates, where the bare ``except:`` would have eaten it;
* blast radius: ``fromList``/``getFullHistory`` still raise by default, so the
  history table, the import comparison and the curation restore -- every other
  caller -- behave exactly as before, and only the two callers of
  ``getEditorsFromHistory`` (``Series.__init__``, ``MainWindow.displayAbout``,
  both of which only ever add names) see the recovered rows;
* and the limit of all of the above. "A bad row costs only itself" holds for a
  row that arrives whole, and only half holds for a row short of six comma
  fields, which ``fromList``'s greedy continuation join first glues to whatever
  follows. The last section of this module is about that join, and it splits
  the behaviour in two because the two halves are not the same kind of problem:

  - the join FAILS to parse. Fixed here. The handler now records only the first
    physical line and resumes at the line after it, so the well-formed rows the
    join swept up are read on their own instead of being discarded with it, and
    ``skipped_rows`` holds one entry per lost file line instead of one entry
    covering several -- except when a line handed back re-joins and *parses*,
    where the lines it absorbs go unrecorded just as they did before. Safe
    without any decision about the format, because the handler is reached only
    on an attempt that has already raised: it cannot change any log that parses
    today. It can, on an already-failing log, turn a loud loss into a silent
    fabrication -- reachable from the writer, bounded, and described in the
    handler comment in ``log.py``.
  - the join SUCCEEDS. NOT fixed, and pinned as a known limitation. A single
    fabricated ``Log`` stands in for both rows, nothing reaches
    ``skipped_rows``, no warning prints, and it fires on the default path too.
    Curing it means deciding what may count as a continuation, and every such
    rule makes an uncompletable short head RAISE where it used to fabricate --
    a change every default caller sees. That is a maintainer's call, so these
    tests write the price down rather than paying it.

  The live shape of the second half, measured with the timestamps the app
  actually writes: a two-field orphan line followed by a row whose obj_name
  reads as a section range -- the ``"-"`` every series-level row writes, or a
  numeric object name, which ``normalizeObjectName`` permits -- puts that
  obj_name in the section slot, the join parses, and
  ``getEditorsFromHistory`` reports the next row's *timestamp* as an editor.
"""

import os
import shutil

import pytest

from PyReconstruct.modules.backend.notifier import NullNotifier
from PyReconstruct.modules.backend.progress import NullProgressReporter
from PyReconstruct.modules.backend.settings_store import DictSettingsStore
from PyReconstruct.modules.datatypes.log import Log, LogSet
from PyReconstruct.modules.datatypes.series import Series

FIXTURE = os.path.join(
    os.path.dirname(__file__), "..", "PyReconstruct", "assets",
    "checker", "files", "shapes1.jser",
)

HEADER = "Date, Time, User, Obj, Sections, Event\n"

# A row that reads, and a row that does not. The bad one is the documented
# real-world shape: the object name holds ", ", so the split yields seven fields
# and the section range is read off the name's own tail.
GOOD = "26-06-29, 12:00, alice, obj_a, 5, Modify trace(s)"
BAD = "26-06-30, 13:00, bob, weird, name, 7, Modify trace(s)"

# The other failing shape, and the only one that reaches the IndexError half of
# the handler: a final row that stops partway through. fromList's continuation
# join (which exists so a row holding a literal newline can be reassembled from
# the physical lines it was split across) keeps pulling log_list[i+1] while the
# row is short of six comma fields, so a short row with nothing after it runs
# the index off the end. Position is what picks the arm: the same text with a
# row after it gets joined to that row and fails in fromStr instead.
TRUNCATED = "26-07-03, 16:00, bob"


@pytest.fixture
def series(tmp_path):
    """A real series, opened from the fixture, with its own hidden dir."""
    if not os.path.exists(FIXTURE):
        pytest.skip("fixture shapes1.jser not found")
    fp = str(tmp_path / "shapes1.jser")
    shutil.copyfile(FIXTURE, fp)
    s = Series.openJser(fp, progress=NullProgressReporter, notifier=NullNotifier())
    s.setSettingsStore(DictSettingsStore())
    yield s
    s.leave_open = False
    s.close()


def write_log(series, *rows):
    """Replace the series' existing_log.csv with the given rows."""
    fp = os.path.join(series.hidden_dir, "existing_log.csv")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(HEADER)
        for row in rows:
            f.write(row + "\n")
    return fp


# --------------------------------------------------------------------------- #
# the shape of the bad row, asserted rather than assumed
# --------------------------------------------------------------------------- #
def test_the_bad_row_really_is_a_parse_failure():
    """The premise the rest of the module rests on.

    ``BAD`` is not arbitrary garbage: it is what ``Log.__str__`` writes for an
    object literally named ``weird, name``, which is why a legacy file can hold
    it. Recorded here so a later change to ``fromStr`` that happens to make this
    row readable turns into a visible failure rather than a silently vacuous
    test.
    """
    assert BAD == str(Log("26-06-30", "13:00", "bob", "weird, name", 7,
                          "Modify trace(s)"))
    with pytest.raises(ValueError):
        Log.fromStr(BAD)
    # ... while the good row reads, and reads as alice's
    assert Log.fromStr(GOOD).user == "alice"


def test_a_truncated_final_row_is_the_index_error_case():
    """The handler names two exception types; this is the second one.

    ``BAD`` above exercises ``ValueError``. Nothing exercised ``IndexError``,
    which is not a hypothetical branch: it is the continuation join in
    ``fromList`` running ``log_list[i+1]`` off the end of the list, which is
    what a row that stops partway through and has no row after it does.

    Asserted rather than assumed, because the two arms are reached by
    *different* code and could not be swapped for one another:
    """
    # through fromStr alone the short row is an unpack failure -- ValueError.
    # The IndexError is not fromStr's at all; it belongs to fromList's join.
    with pytest.raises(ValueError):
        Log.fromStr(TRUNCATED)

    with pytest.raises(IndexError):
        LogSet.fromList([GOOD, TRUNCATED])

    # and it really is *lastness* that selects the arm: give the same text a
    # row to join to and the join succeeds, so the failure lands in fromStr.
    with pytest.raises(ValueError):
        LogSet.fromList([GOOD, TRUNCATED, GOOD])


def test_the_log_writer_itself_can_leave_a_short_last_line(series):
    """The shape is not only hand-forgeable; ``Log.__str__`` writes it.

    Reachability matters here, because a branch that no input can reach is not
    worth a test. It is reached by an object name carrying both hazards this
    parser already names: the ``", "`` ``fromStr`` splits on (see ``BAD``, and
    ``tests/test_contour_name_collision.py`` for why such names exist) and a
    literal newline -- the "return key in name" the continuation join exists
    for. Two of the first and one of the second, and the row's own head already
    has six comma fields, so the join never runs and the head is consumed
    alone. That strands the text after the newline as a physical line of its
    own, and if the row was last in the file there is nothing left to join it
    to.

    So a single real row can hit *both* arms: ValueError on its head, then
    IndexError on its orphaned tail. Both are skipped, alice is kept.
    """
    row = str(Log("26-06-30", "13:00", "bob", "a, b, c\nd", 7, "Modify trace(s)"))
    assert "\n" in row, "the writer emits the name verbatim, newline included"
    head, tail = row.split("\n")
    assert len(head.split(",")) >= 6, "head is self-contained; the join never runs"
    assert len(tail.split(",")) < 6, "tail is a short line with nothing after it"

    write_log(series, GOOD, row)

    assert series.getEditorsFromHistory() == {"alice"}
    assert len(series.getFullHistory(skip_corrupt=True).skipped_rows) == 2


# --------------------------------------------------------------------------- #
# the regression
# --------------------------------------------------------------------------- #
def test_one_bad_row_no_longer_costs_another_user_their_entry(series):
    """alice's row is well formed and hers. bob's failing to parse is not her
    problem, and used to be: the whole set came back empty."""
    write_log(series, GOOD, BAD)

    editors = series.getEditorsFromHistory()

    assert "alice" in editors, "a well-formed row was discarded with the bad one"
    assert editors == {"alice"}, "the unreadable row must not invent an editor"


def test_the_bad_row_can_be_anywhere_in_the_file(series):
    """Order must not decide who survives.

    Before the fix the parse aborted where it stood, so a row's fate depended
    on whether it sat above or below the bad one -- which is not a property
    anyone would choose. Now neither position loses anything but the bad row.
    """
    late = "26-07-01, 14:00, carol, obj_c, 9, Modify trace(s)"
    for rows in ([BAD, GOOD, late], [GOOD, BAD, late], [GOOD, late, BAD]):
        write_log(series, *rows)
        assert series.getEditorsFromHistory() == {"alice", "carol"}


def test_several_bad_rows_cost_only_themselves(series):
    """The recovery is per row, not "tolerate one and give up"."""
    other_bad = "26-07-02, 15:00, dave, another, bad, 3, Modify trace(s)"
    write_log(series, BAD, GOOD, other_bad)

    assert series.getEditorsFromHistory() == {"alice"}


def test_a_truncated_final_row_costs_only_itself(series):
    """The IndexError arm, through the real recovery path.

    A history whose last row stops partway through is the shape that reaches
    ``IndexError`` rather than ``ValueError`` (see
    ``test_a_truncated_final_row_is_the_index_error_case``). It must behave the
    same as any other unreadable row: alice keeps her entry, the truncated row
    is recorded rather than swallowed, and -- the part that matters most --
    ``getEditorsFromHistory`` returns instead of raising. Narrow the handler to
    ``ValueError`` alone and this call raises ``IndexError`` out of
    ``Series.__init__``, which is worse than the pre-fix behavior it replaced:
    that at least opened the series with an empty set.
    """
    write_log(series, GOOD, TRUNCATED)

    assert series.getEditorsFromHistory() == {"alice"}

    ls = series.getFullHistory(skip_corrupt=True)
    assert [l.user for l in ls.all_logs] == ["alice"]
    assert len(ls.skipped_rows) == 1
    assert ls.skipped_rows[0].strip() == TRUNCATED


def test_a_truncated_final_row_does_not_break_opening_the_series(series):
    """The blast radius of the arm, end to end.

    ``Series.__init__`` calls ``getEditorsFromHistory`` whenever the stored
    editors list is empty, and it does not guard the call. So an escaping
    ``IndexError`` is not a wrong answer, it is a series that will not open at
    all. The fixture's empty ``editors`` is asserted so this cannot pass by
    never reaching the code it is about.
    """
    assert series.editors == set()
    write_log(series, GOOD, TRUNCATED)

    reopened = Series(series.filepath, dict(series.sections))
    try:
        assert reopened.editors == {"alice"}
    finally:
        reopened.leave_open = True  # the fixture owns the hidden dir
        reopened.close()


def test_a_clean_log_is_unchanged(series):
    """The ordinary case still reads every row, and this is what makes the
    test above discriminating rather than a tautology."""
    write_log(series, GOOD, "26-07-01, 14:00, carol, obj_c, 9, Modify trace(s)")

    assert series.getEditorsFromHistory() == {"alice", "carol"}


# --------------------------------------------------------------------------- #
# the loss is reported, not swallowed
# --------------------------------------------------------------------------- #
def test_the_dropped_rows_are_recorded_and_counted(series, capsys):
    """Keeping the good rows must not make the bad ones invisible.

    The dropped rows come back on the log set, and the count is printed, so a
    partial history is still something a user can be told about.
    """
    write_log(series, GOOD, BAD)

    ls = series.getFullHistory(skip_corrupt=True)
    assert len(ls.skipped_rows) == 1
    assert "weird, name" in ls.skipped_rows[0]
    assert [l.user for l in ls.all_logs] == ["alice"]

    capsys.readouterr()
    series.getEditorsFromHistory()
    assert "1 unreadable history row" in capsys.readouterr().out


def test_nothing_is_reported_when_nothing_is_dropped(series, capsys):
    write_log(series, GOOD)

    assert series.getFullHistory(skip_corrupt=True).skipped_rows == []
    capsys.readouterr()
    series.getEditorsFromHistory()
    assert "unreadable" not in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# the narrowing is real
# --------------------------------------------------------------------------- #
def test_a_non_parse_error_still_propagates(series, monkeypatch):
    """The bare ``except:`` caught everything, including bugs.

    ``skip_corrupt`` is deliberately not a second bare except: only the two
    exception types a row's parse can raise are skipped. Anything else -- here
    an error standing in for a defect in the parser itself -- still reaches the
    caller instead of being turned into a silently empty editors set.
    """
    write_log(series, GOOD)

    def boom(s):
        raise RuntimeError("not a parse failure")

    monkeypatch.setattr(Log, "fromStr", boom)
    with pytest.raises(RuntimeError):
        series.getEditorsFromHistory()


def test_a_read_failure_still_yields_an_empty_set(series, capsys):
    """A missing log file is the one case with nothing to salvage.

    Series.__init__ calls this on every open of a series with no stored
    editors, including one whose hidden directory has no log yet, so this path
    must not raise.
    """
    os.remove(os.path.join(series.hidden_dir, "existing_log.csv"))

    assert series.getEditorsFromHistory() == set()
    assert "cannot read history" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# blast radius: every other caller is untouched
# --------------------------------------------------------------------------- #
def test_from_list_still_raises_by_default():
    """The history table, the import comparison and the curation restore all
    read the log through the default and would rather fail loudly than show a
    history they know is incomplete. That default is unchanged."""
    with pytest.raises(ValueError):
        LogSet.fromList([GOOD, BAD])

    kept = LogSet.fromList([GOOD, BAD], skip_corrupt=True)
    assert [l.user for l in kept.all_logs] == ["alice"]


def test_get_full_history_still_raises_by_default(series):
    write_log(series, GOOD, BAD)

    with pytest.raises(ValueError):
        series.getFullHistory()


def test_session_logs_are_still_appended_to_the_recovered_history(series):
    """``getFullHistory`` is the on-disk log plus the current session's. The
    skip must not cost the session half."""
    write_log(series, GOOD, BAD)
    series.log_set.addLog("erin", "obj_e", 2, "Modify trace(s)")

    users = [l.user for l in series.getFullHistory(skip_corrupt=True).all_logs]
    assert users == ["alice", "erin"]
    assert "erin" in series.getEditorsFromHistory()


# --------------------------------------------------------------------------- #
# end to end: the series open that this function exists for
# --------------------------------------------------------------------------- #
def test_reopening_the_series_keeps_the_surviving_editor(series):
    """The whole point: ``Series.__init__`` stores what this returns.

    The fixture carries an empty ``editors`` list, which is the condition under
    which __init__ consults the history at all -- asserted, not assumed, so the
    test cannot pass by never reaching the code it is about.
    """
    assert series.editors == set()
    write_log(series, GOOD, BAD)

    reopened = Series(series.filepath, dict(series.sections))
    try:
        assert reopened.editors == {"alice"}
    finally:
        reopened.leave_open = True  # the fixture owns the hidden dir
        reopened.close()


# --------------------------------------------------------------------------- #
# the greedy continuation join: what it costs, and which half of that is fixed
#
# Everything above is about a row that arrives whole. A row SHORT of six comma
# fields is glued to the line after it first, and the join cannot tell a real
# continuation from an unrelated next row -- so it can take a well-formed row
# belonging to somebody else before ``fromStr`` ever sees that row alone.
#
# Which of two things happens then depends on what the concatenation parses as,
# and the two have very different fixes:
#
# * the join FAILS to parse. Fixed. The handler records only the first physical
#   line and resumes at the line after it, so every line the join swept up is
#   re-read on its own. That handler is reached only on an attempt that already
#   raised, so it cannot change any log that parses today -- it is a recovery,
#   not a parsing rule, and needed no decision about the format.
# * the join SUCCEEDS. Still live, and silent: a fabricated ``Log`` stands in
#   for both rows, nothing is recorded, and it fires on the default path too.
#   Curing that means refusing the join, which changes what every default
#   caller sees, so it is a maintainer's call. Pinned below rather than fixed.
#
# The pins below are not endorsements. They are here so that the live half is
# written down with the price next to it, and so that changing the join is a
# decision somebody makes on purpose.
# --------------------------------------------------------------------------- #
LATE = "26-07-01, 14:00, carol, obj_c, 9, Modify trace(s)"

# A series-level row: every ``addLog(None, ...)`` call site writes one, and
# there are on the order of forty of them -- alignment and profile events,
# "Reorder sections", "Modify transform", "Create series", every import. Both
# the object and the section slot come back as the ``"-"`` ``Log.__str__``
# writes for an empty field, which is what makes them the second half of the
# live fabrication below.
SERIES_LEVEL = "26-07-01, 14:00, carol, -, -, Create series"


def test_the_writer_uses_a_colon_in_the_time_field():
    """The premise the shapes below rest on, asserted rather than assumed.

    Which of the next row's fields lands in the section-range slot -- the only
    slot that has to read as an integer -- is what decides whether a join
    parses, and for one alignment that field is the next row's *time*. So a
    test written against an ``HHMM`` timestamp can pin a fabrication this app
    cannot produce. ``getDateTime`` has written ``"%H:%M"`` since the commit
    that created the log (``c46d5204``, Aug 2023); ``git log --all -S '"%H%M"'``
    finds nothing. Recorded here so the constants in this module cannot drift
    back to a shape no version of the product has ever written.
    """
    from PyReconstruct.modules.constants import getDateTime

    assert ":" in getDateTime()[1]
    assert ":" in str(Log(*getDateTime(), "alice", "obj_a", 5, "Modify")).split(", ")[1]


def test_a_row_swallowed_by_a_FAILED_join_is_given_back():
    """The half that is fixed, and the regression guard for it.

    ``TRUNCATED`` is short, so the join runs and takes ``LATE`` -- a perfectly
    well-formed row belonging to somebody else. The concatenation does not
    parse. It used to cost carol her row: both lines went into ``skipped_rows``
    as ONE entry, so the count callers print undercounted the file lines too.

    Now the failure records only the line that was actually short and the scan
    resumes at the next line, so carol's row is read on its own and survives,
    and the recorded entry is one file line rather than two rows' worth.
    """
    ls = LogSet.fromList([GOOD, TRUNCATED, LATE], skip_corrupt=True)

    assert [l.user for l in ls.all_logs] == ["alice", "carol"], (
        "the well-formed row the join swallowed must be given a second read"
    )
    assert len(ls.skipped_rows) == 1
    assert ls.skipped_rows[0].strip() == TRUNCATED
    assert "carol" not in ls.skipped_rows[0], (
        "the recorded entry must be the short line alone, not the concatenation"
    )


def test_position_no_longer_decides_whether_the_next_row_survives():
    """The control, and the point of the fix stated as an invariant.

    The same three rows with the short one last always worked. The same three
    rows with the short one in the middle used to lose carol -- so a row's fate
    turned on where the damage sat relative to it, which is not a property
    anyone would choose. Both orders now agree, and both record the short line
    and nothing else.
    """
    middle = LogSet.fromList([GOOD, TRUNCATED, LATE], skip_corrupt=True)
    last = LogSet.fromList([GOOD, LATE, TRUNCATED], skip_corrupt=True)

    assert [l.user for l in middle.all_logs] == [l.user for l in last.all_logs]
    assert [s.strip() for s in middle.skipped_rows] == [TRUNCATED]
    assert [s.strip() for s in last.skipped_rows] == [TRUNCATED]


def test_the_recovery_cannot_reach_a_log_that_parses():
    """Why the fix above needed no judgement call about the format.

    The recovery lives entirely in the handler for a join that has ALREADY
    raised. There is no way for it to make a currently-succeeding parse succeed
    differently, so no caller whose log reads sees any change -- which is what
    made this half a commit rather than a design decision, and is worth pinning
    so a later "improvement" that moves logic out of the handler and into the
    join is a visible change rather than a quiet one.
    """
    clean = [GOOD, LATE, SERIES_LEVEL]
    for skip in (False, True):
        ls = LogSet.fromList(list(clean), skip_corrupt=skip)
        assert [str(l) for l in ls.all_logs] == clean
        assert ls.skipped_rows == []

    # and a row that fails on its own still costs exactly itself
    ls = LogSet.fromList([GOOD, BAD, LATE], skip_corrupt=True)
    assert [l.user for l in ls.all_logs] == ["alice", "carol"]
    assert len(ls.skipped_rows) == 1


# --------------------------------------------------------------------------- #
# the half that is NOT fixed: a join that succeeds, and fabricates
#
# KNOWN LIMITATION, pinned deliberately and not worked around. Curing it means
# deciding what may count as a continuation, and any such rule makes a short
# head that is never completed RAISE where it used to fabricate -- a change
# every default caller sees. That is a maintainer's call, so these tests record
# the price rather than paying it, the same way ``test_contour_name_collision``
# records the collision it does not resolve.
# --------------------------------------------------------------------------- #
def test_a_two_field_orphan_before_a_series_level_row_invents_an_editor():
    """The live fabrication, with the timestamps this app actually writes.

    Let ``k`` be the number of ``", "`` fields on the orphan line. The
    concatenation puts the next row's field ``k-1`` into the section-range slot
    -- the only slot that must read as an integer -- so ``k`` alone decides
    whether the join parses. ``k=4`` puts the next row's *time* there, which
    needs a time with no colon and is therefore unreachable (see
    ``test_the_writer_uses_a_colon_in_the_time_field``). ``k=2`` puts the next
    row's *obj_name* there, and every series-level row writes ``"-"`` in that
    field -- so ``k=2`` parses whenever the next row is series-level, which is
    an ordinary thing for a row to be. A series-level follower is sufficient,
    not necessary: ``normalizeObjectName`` permits digits, so an object
    literally named ``5`` puts a readable section range there too.

    What that costs: carol's row is gone, an editor nobody was is invented in
    its place -- here the next row's own timestamp, read as a username -- and
    ``skipped_rows`` is EMPTY, so no caller can report any of it.
    """
    orphan = "d, e"
    assert len(orphan.split(", ")) == 2, "k=2 is the alignment being pinned"

    ls = LogSet.fromList([GOOD, orphan, SERIES_LEVEL], skip_corrupt=True)

    users = [l.user for l in ls.all_logs]
    assert "carol" not in users, "carol's whole row was folded into another"
    assert "14:00" in users, "a raw timestamp is now standing in for a person"
    assert ls.skipped_rows == [], "and nothing at all records the loss"


def test_the_four_field_orphan_goes_loud_instead_and_is_recovered():
    """The alignment an earlier draft of these tests pinned, corrected.

    A ``k=4`` orphan puts the next row's *time* in the section-range slot, so
    it parses only for a time with no colon -- and this app has never written
    one. Under the real format the same shape fails the join and is now
    recovered by the handler, so it fabricates nothing and loses nobody.

    Kept as a test rather than deleted because it is the discriminating control
    for the pin above: it shows that ``k`` and not "a short row" is what
    selects the fabrication, and it would fail loudly if the writer ever went
    back to a colon-less timestamp.
    """
    row = str(Log("26-06-30", "13:00", "bob", "a, b, c\nd, e", None,
                  "Modify ztrace"))
    head, tail = row.split("\n")
    assert len(head.split(",")) >= 6, "head is self-contained; the join skips it"
    assert len(tail.split(", ")) == 4, "k=4 is the alignment being contrasted"

    ls = LogSet.fromList([head, tail, LATE], skip_corrupt=True)

    users = [l.user for l in ls.all_logs]
    assert "carol" in users, "no fabrication, and the well-formed row survives"
    assert "-" not in users, "the '-' editor needs a colon-less time; there is none"
    assert len(ls.skipped_rows) == 2, "one entry per lost file line"


def test_the_fabrication_fires_on_the_default_path_too():
    """``skip_corrupt`` is not what admits it.

    The join succeeds, so the flag never comes into it: the history table, the
    import comparison and the curation restore -- every default caller -- read
    the fabricated row too. This is the half of the defect that no exception
    handler can reach, which is why it is a decision and not a commit.
    """
    ls = LogSet.fromList([GOOD, "d, e", SERIES_LEVEL])  # default skip_corrupt

    assert [l.user for l in ls.all_logs] == ["alice", "14:00"]
    assert ls.skipped_rows == []


def test_a_one_field_orphan_pollutes_the_next_row_instead():
    """The other silent shape, and the cheapest one to reach.

    ``k=1`` puts the next row's own section range in the section slot, so the
    join ALWAYS parses. The next row survives and keeps its user, but the
    orphan is glued onto its date, so the entry the app shows is not the one
    that was written -- and, again, nothing is recorded.
    """
    clean_head = "26-06-30, 13:00, bob, zt_old, -, Rename ztrace to new"
    orphan = "name"

    ls = LogSet.fromList([clean_head, orphan, LATE])  # default: skip_corrupt=False

    assert [l.user for l in ls.all_logs] == ["bob", "carol"]
    assert ls.all_logs[1].date == "name26-07-01"
    assert ls.skipped_rows == []


def test_the_fabrication_is_reachable_through_the_real_recovery_path(series, capsys):
    """End to end, through a real series and the app's own writer.

    Every physical line here is one ``Log.__str__`` emits, written the way the
    app writes ``existing_log.csv`` and read back the way ``getFullHistory``
    reads it, with the timestamps ``getDateTime`` returns.

    The reachable trigger is a literal newline in the EVENT text of a row --
    the one pinned here happens to be series-level, but that is not required;
    ``Series.editZtraceAttributes``' rename row is object-level and reaches the
    same outcome -- leaving exactly one comma after it, followed by a row whose
    obj_name reads as a section range. ``Series`` writes such events with names
    it never normalizes -- ``Series.modifyAlignments`` writes
    ``f"Rename alignment {old_a} to {new_a}"``, and
    ``Series.editZtraceAttributes`` writes both
    ``f"Rename ztrace to {new_name}"`` and ``f"Create ztrace from {name}"``.
    Only ``Trace.name`` goes through ``normalizeObjectName``; ztrace and
    alignment names are plain attributes, and ``QLineEdit`` keeps a pasted
    newline, so a paste into either rename box is enough. The ztrace box needs
    one extra condition, because its rename writes a *pair* of rows and the
    second usually drags the chain back into loudness: the pasted name's first
    line must be ``-`` or numeric, so that the pair supplies its own ``"-"``
    section field (``new_name = "-\\n, b"`` does it). Both boxes are live; it
    is alignment rename *as well as* ztrace rename, not one instead of the
    other. Four more routes carry the same unnormalized free text into event
    text -- brightness/contrast profile names, object group names, user column
    names, and the per-object user-column value.

    A newline in an *obj_name* cannot reach this shape where it would matter:
    the section and event fields trail the name, so the *last* fragment of an
    obj_name-split row -- the only one a fresh row follows -- is ``k>=3``.
    Interior fragments of a multi-newline obj_name can be ``k=2``, but another
    fragment of the same row follows them rather than a row.

    What the user is told: nothing. No warning prints, and the series then
    claims an editor that is a timestamp.
    """
    hazard = str(Log("26-08-04", "19:14", "bob", None, None,
                     "Rename alignment old to x\ny, z"))
    head, tail = hazard.split("\n")
    assert len(tail.split(", ")) == 2, "the writer produced the k=2 orphan"

    write_log(series, GOOD, head, tail, SERIES_LEVEL)

    capsys.readouterr()
    editors = series.getEditorsFromHistory()
    out = capsys.readouterr().out

    assert "carol" not in editors, "a well-formed row was swallowed by the join"
    assert "14:00" in editors, "the series now claims an editor that never existed"
    assert "unreadable" not in out, "and the loss is not reported at all"
    assert series.getFullHistory(skip_corrupt=True).skipped_rows == []
