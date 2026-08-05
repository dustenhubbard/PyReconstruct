- **Every section now builds and maintains a columnar store beside its object
  model, in every session.** The store landed behind an environment variable
  whose whole premise was that a real launch could not reach it, which made the
  next step impossible: gated off, a section's store was `None` forever in a real
  session, so nothing outside a test had anything to read. The gate is removed
  rather than defaulted, and the repository is scanned for its name so that a
  half-removed gate -- a store on one machine and not another -- cannot survive.

  **Nothing reads the store yet and no byte of any `.jser` changes.** The object
  model still owns every value, `save()` still serializes it, and the store is a
  shadow copy that is written and checked against it. Measured on a 745 MB series
  (636 sections, 323,534 traces): loading a section costs 0.0225 s instead of
  0.0111 s, holding a whole series resident costs about 24% more memory, and a
  single-trace edit is unchanged at 0.002 ms.

  The check that compares the two representations moved from "the whole section,
  after every mutation" -- which measured 85 to 129 ms per edit and would have
  made dragging a selection unusable -- to a targeted per-row comparison at each
  mutation plus a full comparison at every save. Six places in the application
  that edited traces or contours without going through `Section` were found by
  that check and now rebuild the store afterwards: undo, redo, deleting an
  object, hiding objects, hiding all traces, and restoring previous visibility.
