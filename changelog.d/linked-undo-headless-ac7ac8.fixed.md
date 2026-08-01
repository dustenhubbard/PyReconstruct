- **Fixed: `undo()` no longer stalls permanently when the linked-undo prompt
  fires in a headless environment.** `MainWindow.undo` reached a three-way
  branch when both a series-wide and a section-only undo were available and
  linked: it asked the user "undo all sections or only this one?" via a
  constructed `QMessageBox(self).exec()`. Under `QT_QPA_PLATFORM=offscreen`
  that call spins a modal event loop nothing ever dismisses, so it was a
  permanent stall. A `user_is_present()` guard now takes the "undo all
  sections" default when the platform is offscreen, matching the behavior every
  other modal in this path follows.
