- **The maintainer line in "What's new" is now visible without scrolling.** The
  provenance line -- "An independent build of PyReconstruct, maintained by
  Dusten Hubbard." -- was appended to the end of the release-notes markdown,
  below a rule, which put it inside the scrollable notes browser. On any release
  with more than a screenful of notes, which is the normal case, a reader had to
  scroll to the very bottom to reach it, and most never did: the line naming who
  maintains this build was the one part of the dialog that reliably went unread.

  It is now its own label between the notes and the "Full release notes on
  GitHub" link, so it is on screen from the moment the dialog opens. The wording
  is unchanged, and so is the italic the markdown had given it. What has changed
  is that it is no longer dimmed: it sits at the dialog's ordinary text colour
  rather than the muted one. Who maintains this build is what a lab needs in
  order to report an issue to the right person, so it is set to be read rather
  than skimmed past.
