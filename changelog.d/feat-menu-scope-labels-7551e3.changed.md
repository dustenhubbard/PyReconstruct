- **Three right-click commands that appeared on two menus under the same label
  now say which one they are.** `Smooth traces`, `Edit radius...` and `Edit
  shape...` each existed twice, once on the object menu and once on the trace
  menu, with nothing in either label to tell them apart. The object copies walked
  every section the object appears on and edited every trace of the contour
  (`Series.smoothObject`, `Series.editObjectRadius`, `Series.editObjectShape`);
  the trace copies edited the traces you had selected, on the section in front of
  you (`Section.editTraceRadius`, `Section.editTraceShape`, `Trace.smooth`).
  Picking the wrong one on a large series meant a series-wide edit where you
  wanted a local one, and the only way to tell them apart was to run one. The
  object copies are now `Smooth object`, `Edit object radius...` and `Edit object
  shape...`; the trace copies are `Smooth selected traces`, `Edit selected
  radius...` and `Edit selected shape...`. The commands themselves are unchanged,
  so anything you were doing still works. Only the label moved.

- **The object menu's `Geometry ▸` submenu is gone and its four commands are
  top-level.** `Smooth object` is promoted because smoothing is frequent and did
  not deserve a hop, and `Split into separate objects` now sits directly under
  `Duplicate object`, being a structural command rather than a trace edit. That
  left the submenu holding two items, which is not enough to earn one, so it was
  dissolved rather than renamed: with the scope in the labels there is nothing
  left for a container to describe. `Comment...` becomes `Leave object
  comment...` and closes the object-settings section, whose order is now `Object
  attributes ▸`, `Smooth object`, `Duplicate object`, `Split into separate
  objects`, `Edit object radius...`, `Edit object shape...`, `Group ▸`, `Set
  curation ▸`, `Custom categories ▸`, `Leave object comment...`. One builder
  backs both surfaces, so the object list's menu and the field menu's `Object ▸`
  submenu change together.
