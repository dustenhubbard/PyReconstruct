- **Test: headless save-as for a never-saved series.** `saveAsToJser` calls
  `FileDialog.get` with no offscreen branch; on the offscreen platform the
  native dialog has no window manager to dismiss it, so a series with an empty
  `jser_fp` stalled in any headless context. `DialogRecorder.fileDialogGet`
  now pops from a `file_responses` queue when non-empty, following the same
  pattern as `quickDialogGet`'s `responses` queue. A new test supplies a
  real `tmp_path` destination via that queue and confirms the hidden directory
  is moved, the `.jser` is written, and the series is marked clean.
