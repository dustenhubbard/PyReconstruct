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
  row that arrives whole, and NOT for a row short of six comma fields, which
  ``fromList``'s greedy continuation join first glues to whatever follows. The
  last section of this module pins that, because it is a live behaviour and not
  a hypothetical: the swallowed row is lost, and depending on what the
  concatenation parses as, lost either loudly (both rows in one
  ``skipped_rows`` entry, so the printed count undercounts the file lines) or
  silently (a fabricated ``Log`` in place of both, nothing recorded, on the
  default path too). Fixing it means choosing what counts as a continuation,
  which changes every default caller and is a maintainer's call; these tests
  exist so that choice is a deliberate one and not an accident.
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
GOOD = "26-06-29, 1200, alice, obj_a, 5, Modify trace(s)"
BAD = "26-06-30, 1300, bob, weird, name, 7, Modify trace(s)"

# The other failing shape, and the only one that reaches the IndexError half of
# the handler: a final row that stops partway through. fromList's continuation
# join (which exists so a row holding a literal newline can be reassembled from
# the physical lines it was split across) keeps pulling log_list[i+1] while the
# row is short of six comma fields, so a short row with nothing after it runs
# the index off the end. Position is what picks the arm: the same text with a
# row after it gets joined to that row and fails in fromStr instead.
TRUNCATED = "26-07-03, 1600, bob"


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
    assert BAD == str(Log("26-06-30", "1300", "bob", "weird, name", 7,
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
    row = str(Log("26-06-30", "1300", "bob", "a, b, c\nd", 7, "Modify trace(s)"))
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
    late = "26-07-01, 1400, carol, obj_c, 9, Modify trace(s)"
    for rows in ([BAD, GOOD, late], [GOOD, BAD, late], [GOOD, late, BAD]):
        write_log(series, *rows)
        assert series.getEditorsFromHistory() == {"alice", "carol"}


def test_several_bad_rows_cost_only_themselves(series):
    """The recovery is per row, not "tolerate one and give up"."""
    other_bad = "26-07-02, 1500, dave, another, bad, 3, Modify trace(s)"
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
    write_log(series, GOOD, "26-07-01, 1400, carol, obj_c, 9, Modify trace(s)")

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
# the limit of the guarantee: the greedy continuation join
#
# Everything above is about a row that arrives whole. A row SHORT of six comma
# fields is glued to the line after it first, and the join cannot tell a real
# continuation from an unrelated next row. These pin what that costs. They are
# not endorsements -- they are here so that changing the join is a decision
# somebody makes on purpose, with the price of the current behaviour written
# down next to it.
# --------------------------------------------------------------------------- #
LATE = "26-07-01, 1400, carol, obj_c, 9, Modify trace(s)"


def test_a_short_row_that_is_not_last_swallows_the_row_after_it():
    """The loud half: two file lines lost, one ``skipped_rows`` entry.

    ``TRUNCATED`` is short, so the join runs and takes ``LATE`` -- a perfectly
    well-formed row belonging to somebody else -- before ``fromStr`` ever sees
    it alone. The concatenation does not parse, so both go as one.
    """
    ls = LogSet.fromList([GOOD, TRUNCATED, LATE], skip_corrupt=True)

    assert [l.user for l in ls.all_logs] == ["alice"], "carol's row was swallowed"
    assert len(ls.skipped_rows) == 1, "two file lines, one recorded entry"
    # the recorded entry is the concatenation, so carol's text is inside it --
    # which is what makes the printed count undercount the lines that were lost
    assert TRUNCATED in ls.skipped_rows[0]
    assert "carol" in ls.skipped_rows[0]


def test_position_alone_decides_whether_the_next_row_survives():
    """The control that makes the test above non-vacuous.

    The same three rows, the short one last. Nothing about ``LATE`` changed;
    only where the short row sits. carol survives, so the loss is caused by
    position and not by anything wrong with her row.
    """
    ls = LogSet.fromList([GOOD, LATE, TRUNCATED], skip_corrupt=True)

    assert [l.user for l in ls.all_logs] == ["alice", "carol"]
    assert len(ls.skipped_rows) == 1
    assert ls.skipped_rows[0].strip() == TRUNCATED


def test_a_swallowed_row_can_vanish_with_nothing_recorded_at_all():
    """The silent half, and the worse one.

    When the concatenation happens to reach six ``", "`` fields it PARSES, and
    one fabricated ``Log`` stands in for both rows. ``skipped_rows`` stays
    empty for it, so no caller can report the loss, and the invented row
    carries ``"-"`` as its user -- the placeholder ``Log.__str__`` writes for
    an empty field, which ``getEditorsFromHistory`` then adds as though it were
    a person.

    The input is the app's own writer's output: an object name holding two
    ``", "`` and a newline (see
    ``test_the_log_writer_itself_can_leave_a_short_last_line`` for why such a
    name reaches the log at all), which splits into a self-contained head and a
    four-field orphan tail.
    """
    row = str(Log("26-06-30", "1300", "bob", "a, b, c\nd, e", None,
                  "Modify ztrace"))
    head, tail = row.split("\n")
    assert len(head.split(",")) >= 6, "head is self-contained; the join skips it"
    assert len(tail.split(",")) < 6, "the tail is short, so the join runs on it"

    ls = LogSet.fromList([head, tail, LATE], skip_corrupt=True)

    users = [l.user for l in ls.all_logs]
    assert "carol" not in users, "carol's whole row was folded into another"
    assert "-" in users, "and a user nobody was got invented in its place"
    # the head is unreadable on its own and IS recorded; the swallowed row is
    # not, which is the asymmetry that makes this half silent
    assert len(ls.skipped_rows) == 1
    assert "carol" not in ls.skipped_rows[0]


def test_the_silent_swallow_fires_on_the_default_path_too():
    """``skip_corrupt`` is not what admits it.

    The parse succeeds, so the flag never comes into it: every default caller
    -- the history table, the import comparison, the curation restore -- reads
    the fabricated row too. Asserted with a shape whose head reads cleanly, so
    nothing raises before the join is reached.
    """
    clean_head = "26-06-30, 1300, bob, zt_old, -, Rename ztrace to new"
    orphan = "name"

    ls = LogSet.fromList([clean_head, orphan, LATE])  # default: skip_corrupt=False

    assert [l.user for l in ls.all_logs] == ["bob", "carol"]
    # carol's row parsed -- but the orphan was absorbed into her date, so the
    # entry the app now shows for her is not the one that was written
    assert ls.all_logs[1].date == "name26-07-01"
    assert ls.skipped_rows == []


def test_the_swallow_is_reachable_through_the_real_recovery_path(series, capsys):
    """End to end, through a real series rather than a list.

    The count printed to the user is the point: three file lines are gone --
    the two the hazard row occupies and carol's -- and the figure says one.
    """
    row = str(Log("26-06-30", "1300", "bob", "a, b, c\nd, e", None,
                  "Modify ztrace"))
    head, tail = row.split("\n")
    write_log(series, GOOD, head, tail, LATE)

    capsys.readouterr()
    editors = series.getEditorsFromHistory()

    assert "carol" not in editors, "a well-formed row was swallowed by the join"
    assert "-" in editors, "the series now claims an editor that never existed"
    assert "1 unreadable history row" in capsys.readouterr().out
