- **`Ctrl+Shift+H` now runs `Set hosts...`, which it never did from a fresh
  install.** The action carried a default key in `default_settings.py` and an
  editable row in the shortcuts dialog, but the object menu built it with `""`
  as its shortcut, and only that third argument binds anything. The key was
  therefore dead out of the box. It went unreported because opening
  `Shortcuts...` and pressing OK repaired it in passing: `resetShortcuts` writes
  onto the QAction the menu already built, so anyone who went looking at the
  list fixed their own copy and could not reproduce it afterwards, until the
  next context-menu rebuild re-applied the `""`. The menu now passes the series,
  so the key resolves by action name like every other configurable shortcut.
