- **A row in a series' log that stops partway through no longer takes the
  well-formed row after it down as well.** The log is newline-delimited but its
  fields may contain newlines, so a name holding one splits its row across
  physical lines. `LogSet.fromList` reassembles those by joining a short line to
  the lines after it until it has six comma fields, and that join is greedy: it
  takes whatever follows, including a complete row belonging to somebody else.
  When the result then failed to parse, every line the join had consumed was
  discarded as a single skipped entry — so a well-formed row was lost for no
  reason of its own, and the count of skipped rows the reader prints described
  logical rows rather than the file lines actually gone. The failure now records
  only the line that was short and resumes reading at the line after it, so the
  swallowed rows get a fresh read and the count is one entry per lost line —
  except in the one case below, where a line handed back joins forward and
  succeeds, and the lines it absorbs go unrecorded just as they did before.

  Nothing about how a log is parsed changed: the recovery lives in the handler
  for a join that has already failed, so a log that reads today reads
  identically. Series ▸ About's editors list and the history table are where the
  recovered rows show up.

  One shape is deliberately left alone. When the greedy join happens to *succeed*
  it produces a single fabricated row standing in for two real ones, with nothing
  recorded and no warning printed — reachable today by pasting a multi-line name
  into the alignment rename box or the ztrace rename box (both are live routes,
  along with brightness/contrast profile names, object group names and user
  column names). No exception handler can reach that case; refusing the join
  would, but it would also make a row that can never be completed raise where it
  currently produces something, which is a change every reader of the log sees.
  It is pinned in `tests/test_editors_from_corrupt_history.py` as a known
  limitation, so the choice is a deliberate one.

  The recovery above can itself feed that shape: on a log that already fails to
  parse, a line handed back may join forward and succeed where the old code
  simply lost it. It takes a pasted name that splits one row across three lines,
  and it changes nothing on a log that reads today — but it does mean an
  already-broken log can lose an editor quietly where it used to lose one
  loudly. No annotation or trace data is involved either way.
