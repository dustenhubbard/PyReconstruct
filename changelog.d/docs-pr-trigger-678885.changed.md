- CI: `docs.yml` now runs `mkdocs build --strict` on every PR that touches a
  docs-relevant file (`docs/**`, `mkdocs.yml`, or the workflow itself). The
  `push` trigger and the Pages deploy job are unchanged and continue to fire
  only on merges to `main`.
