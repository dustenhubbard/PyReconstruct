- **The in-app offer to install an optional package no longer answers a
  uv-managed source install with advice that cannot work.** Declining a feature
  because `svgwrite`, `cairosvg` or `cloud-volume` is missing puts up a yes/no
  prompt, and accepting it runs `pip install <name>`. The project's documented
  from-source setup is `uv sync` (see the README), and uv does not put pip
  inside the environment it creates -- it installs packages itself and has no
  use for one. So on the setup the README tells people to use, that command
  fails before it starts: `/bin/sh: pip: command not found`. The user then saw
  the generic failure notice, whose entire content was "Something went wrong.
  Please try pip installing X in a terminal" -- naming the one command that had
  just been established not to exist, and sending them to look for a fault in
  their network or their permissions instead.

  A failed install now distinguishes "there is no pip here" from "pip ran and
  pip failed". The first gets a notice naming commands that work: `uv add
  <name>` and `uv pip install <name>` in a uv-created environment, and
  `python -m ensurepip --upgrade` followed by `pip install <name>` in any other
  pip-less interpreter, which is also told which interpreter it is. Both name
  the package's *install* name rather than its import name, so the lines can be
  copied as printed -- `cloudvolume` installs as `cloud-volume`. Ordinary
  install failures are untouched and keep the generic notice, which is honest
  advice for them.

  The environment is identified by the `uv = <version>` key uv stamps into
  `pyvenv.cfg`, which neither `venv` nor `virtualenv` writes, rather than by
  looking for a directory called `.venv`: a uv environment is not always named
  that, and a directory with that name was not necessarily made by uv. Whether
  a pip exists is established by looking for one rather than by matching the
  subprocess output, because the two spellings of the failure share no text --
  a shell `pip install` exits 127 with "command not found" and
  `sys.executable -m pip` exits 1 with "No module named pip".
