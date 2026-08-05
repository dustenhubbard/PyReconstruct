- **SVG and PNG section export work again.** `File > Export > SVG` and
  `File > Export > PNG` reach
  `modules/backend/exports/svg_conversion.py`, which imports `svgwrite` and
  `cairosvg` -- neither of which was ever declared in `pyproject.toml`,
  `requirements.txt` or `uv.lock`. Both imports are function-local, so the
  package, the module and `Section` all imported cleanly and the failure was
  deferred to the single call a user makes, which raised
  `ModuleNotFoundError: No module named 'svgwrite'` in every correctly-installed
  environment. Nothing caught it because no test touched the export path at all.
  Both packages are now declared and locked, and
  `tests/test_export_svg_png.py` exports a real fixture section and checks the
  output is an SVG carrying that section's embedded image and named trace paths,
  and a PNG whose IHDR dimensions match the requested scale. Note for PNG
  specifically: `cairosvg` does not bundle Cairo -- it `dlopen`s the native
  library -- so PNG export additionally needs `libcairo2` (Debian/Ubuntu),
  `brew install cairo` plus `DYLD_FALLBACK_LIBRARY_PATH` (macOS), or a Cairo DLL
  on `PATH` (Windows). Declaring the package is necessary but not sufficient
  there; `docs/DEV_UV.md` records the per-platform requirement, and CI installs
  `libcairo2` so the PNG assertion runs on the gate. SVG export needs none of
  this and is fixed outright.
