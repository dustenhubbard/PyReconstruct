- **The shortcuts list no longer offers to rebind `Home`, which it could not
  actually rebind.** `Home` (`View ▸ Set view to image`) is one of the four fixed
  menu shortcuts, along with `PgUp`/`PgDown` and `Ctrl+\`. Unlike the other
  three it also had a default in `default_settings.py` and an editable field in
  **Help ▸ Shortcuts list**, so the dialog presented it as rebindable. It was
  not: the key is written into the action tuple in `menubar.py`, and
  `createMenuBar` runs on every series open, so a new key typed into that field
  was stored and then overwritten the next time a series was opened.

  The visible cost was to the dialog's duplicate check rather than to `Home`
  itself. On OK, the dialog reserves the keys held by actions it cannot edit and
  refuses an entry that collides with one, which is why it stops you putting
  `Ctrl+\` on a second command. Because `homeview_act` sat in the editable set,
  its `Home` was never added to that reserved list, so the dialog would accept
  `Home` for some other command with no warning. Two actions sharing a sequence
  means neither one fires, and `Home` returned to fitting the view on the next
  series open regardless, so the user lost the command they had just bound as
  well as the one they were trying to replace.

  `Home` is now fixed the way the other three are, with no settings default and
  no editable row. It keeps its plain-text entry in the shortcuts list beside
  `Page Up`, `Page Down` and `? (Shift+/)`, so it is still documented where it
  always was, and it is now reserved against being assigned to anything else.
  The key itself is unchanged. A value stored under the old editable field never
  had any effect and still has none.
