# Release channels

PyReconstruct's in-app updater serves two channels. Users pick one under
**Series ▸ Options ▸ Update channel**; the default is Stable.

| Radio label | Channel value | Serves |
| ----------- | ------------- | ------ |
| Stable (recommended) | `release` | the newest release that is not marked pre-release |
| Beta (early features, may be unstable) | `prerelease` | the newest release that is marked pre-release |

The updater reads GitHub Releases from the repository named in `GITHUB_REPO`
(`PyReconstruct/modules/backend/updater/updater.py`). Both channels skip drafts.
The Beta channel also skips any release under the legacy `ROLLING_TAG`
(`prerelease`), which no longer gets published but is excluded as defense in
depth for old clients.

Ordering is by parsed version, using [PEP 440](https://peps.python.org/pep-0440/)
semantics, and not by the order GitHub lists releases in. So a re-published or
out-of-order tag cannot mis-select an update:

```
1.21.0b1 < 1.21.0b2 < 1.21.0rc1 < 1.21.0
```

A final release with no pre-release suffix outranks every pre-release of the same
version, so once `v1.21.0` ships, both channels offer it.

Switching from Beta back to Stable is safe at any time. The updater never
installs anything without being told to. If you are running a beta that is newer
than the current stable, the next check heads the dialog "Downgrade" and offers
`Later` and `Download && Install`. Install is the default button, so choose
`Later` to keep the beta until a stable release catches up to it.

## Tag convention

| Kind | Spelling | Examples |
| ---- | -------- | -------- |
| stable | `vX.Y.Z` | `v1.20.4`, `v1.21.0` |
| pre-release | `vX.Y.Z-beta-N` | `v1.21.0-beta-1` … `v1.21.0-beta-7` |

`-beta-N` is the convention in use. Other PEP 440 spellings (`v1.21.0rc1`,
`v1.21.0-rc.1`, `v1.21.0a1`) classify as pre-releases too, but the shipped tags
all use `-beta-N` and new ones should match.

`setuptools-scm` derives the build's embedded version from the tag, so the tag
must point at the exact commit you intend to ship. The tag string is what the
updater orders on. Assets are named with the PEP 440 public version rather than
the raw tag, so `v1.21.0-beta-7` produces `PyReconstruct-1.21.0b7-*`.

## How a tag becomes a GitHub Release

`.github/workflows/build-installers.yml` runs on a pushed tag matching `v*.*.*`
(and on `workflow_dispatch`). It does not run on a push to `main`: the former
rolling per-commit build, and the Developer channel it fed, were removed.

The "Classify release" step decides stable-vs-pre-release from the tag alone:

```bash
if [[ "$GITHUB_REF_NAME" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then  # stable
```

Only a clean `vX.Y.Z` is stable. Everything else publishes with
`prerelease: true`. Note that this is stricter than testing whether the tag
contains a hyphen: a dashless `v1.20.4rc1` is correctly classified as a
pre-release, which a hyphen test would get wrong.

The same step decides whether to stage the release as a hidden draft, reading the
repository variable `STAGE_RELEASE_AS_DRAFT`:

| Value | Effect |
| ----- | ------ |
| unset or `auto` (current setting) | draft if stable, publish immediately if pre-release |
| `true` | always draft |
| `false` | never draft |

The default exists because the draft is an asset-completeness gate, which matters
most for the release that reaches every user, while testers want betas
immediately. Under `auto`, a stable cut does not go live on its own. See the
stable runbook below.

Each release carries 8 assets: Windows `Setup.exe`, macOS `arm64` and `x86_64`
dmgs, the Linux installer tarball, and a `.sha256` for each. Release notes are
built from the matching `## [VERSION]` section of `WHATS_NEW.md` plus a compare
link to the previous tag.

`publish-pypi.yml` is not part of this. It is `workflow_dispatch` only and has no
tag trigger, so cutting a release ships installers through GitHub Releases and
nothing to PyPI.

## Cutting a beta

Betas are tagged on `main`.

```bash
git checkout main
git pull
# confirm WHATS_NEW.md has a '## [1.21.0-beta-8]' section for this version
git tag v1.21.0-beta-8
git push origin v1.21.0-beta-8
```

The workflow builds the installers, generates checksums, and publishes a GitHub
pre-release immediately (no draft, under `auto`). Within a few minutes every user
on the Beta channel is offered it from inside the app.

## Cutting a stable release

Same tag push, different aftermath. Under `STAGE_RELEASE_AS_DRAFT=auto` the
stable release is created as a draft, which is invisible to the updater and
to the Releases page.

```bash
git checkout main
git pull
# confirm WHATS_NEW.md has a '## [1.21.0]' section, not just the beta sections
git tag v1.21.0
git push origin v1.21.0
```

Then, once the run finishes:

1. Open the draft release and confirm all 8 assets attached. A matrix leg is
   allowed to fail without blocking the release, so a missing dmg is possible and
   silent.
2. Check the generated notes. They come from the `## [1.21.0]` section of
   `WHATS_NEW.md`; if that section is missing, the notes body is empty apart from
   the compare link.
3. Publish the draft. Assets are already built, so it goes live instantly.

### Pruning is skipped for a staged draft

The workflow's "Prune superseded pre-releases" step deletes the pre-releases of
the same `X.Y.Z` line (`v1.21.0-beta-1` … `v1.21.0-beta-7`) and their git tags,
so the Releases page and the updater only offer the stable. It is scoped by
`scripts/prune_prereleases.py` to that exact version line; the stable itself and
every other line are never touched.

That step is gated on the release not being a draft. Under `auto`, a stable cut
is a draft, so the prune does not run and the betas are left behind. After
publishing the draft, delete the superseded pre-releases and their tags by hand:

```bash
gh release delete v1.21.0-beta-1 --cleanup-tag --yes
# ... through v1.21.0-beta-7
```

Otherwise a Beta-channel user keeps being offered `v1.21.0-beta-7` alongside the
stable `v1.21.0`. The PEP 440 ordering means the stable wins on the Stable
channel regardless, but the stale betas stay visible on the Releases page and on
the Beta channel until the next pre-release supersedes them.

## Notes

- Retagging: `build-installers` scopes its concurrency group per matrix leg, so
  re-pushing a moved tag cancels only the older run's same-platform leg. The
  group must keep the matrix key: a ref-only group made the three legs of one run
  cancel each other, which broke every build until it was fixed.
- The Linux installer pins its install source to the exact tag, and the workflow
  fails loudly if that pin does not apply, so a release cannot silently ship an
  installer that installs the tip of `main`.
- `setuptools-scm` needs full history and tags. Both release jobs check out with
  `fetch-depth: 0`; a shallow checkout produces a `0.0.0` fallback version and the
  workflow fails on it deliberately.
