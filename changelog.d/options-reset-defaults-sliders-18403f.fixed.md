- **Fixed: Reset Defaults now moves the sliders in `Series ▸ Options`.** The
  dialog rebuilds itself with `use_defaults=True` when Reset Defaults is
  pressed, and every option reads its value through
  `series.getOption(name, use_defaults)` so it comes back at the shipped
  default. Three did not pass the flag: the 3D XY resolution slider, the scale
  bar size slider and the CPU usage slider. They read the stored value
  unconditionally, so those three stayed exactly where the user had left them
  while everything around them reset.

  Also guards `determine_cpus` against `os.cpu_count()` returning `None`, which
  Python documents as possible and which would otherwise raise while the CPU
  usage section is built.
