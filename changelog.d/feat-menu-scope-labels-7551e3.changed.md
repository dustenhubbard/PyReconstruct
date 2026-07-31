- **Four right-click commands that appeared on two menus under the same label
  now say which one they are.** `Smooth traces`, `Edit radius...`, `Edit
  shape...` and `Unhide` each existed twice, once on the object menu and once on
  the trace menu, with nothing in either label to tell them apart. The object
  copies walked every section the object appears on and changed every trace of
  the contour (`Series.smoothObject`, `Series.editObjectRadius`,
  `Series.editObjectShape`, `Series.hideObjects`); the trace copies changed the
  traces you had selected, on the section in front of you
  (`Section.editTraceRadius`, `Section.editTraceShape`, `Trace.smooth`,
  `Section.hideTraces`). Picking the wrong one on a large series meant a
  series-wide change where you wanted a local one, and the only way to tell them
  apart was to run one. The object copies are now `Smooth object`, `Edit object
  radius...`, `Edit object shape...` and `Unhide object`; the trace copies are
  `Smooth selected traces`, `Edit selected radius...`, `Edit selected shape...`
  and `Unhide selected traces`. The commands themselves are unchanged, so
  anything you were doing still works. Only the labels moved.

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

- **The visibility group keeps its members and its order.** `Unhide object` is
  the only label in it that changed, and nothing moved: `Hide`, `Unhide object`,
  `Hide other objects`, `Hide all objects`, `Show all objects`, one
  uninterrupted section, same as before. `Hide` needed no scope word because the
  trace menu's counterpart already reads `Hide traces`.
