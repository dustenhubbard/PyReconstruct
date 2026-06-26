#!/usr/bin/env bash
# Wrap dist/PyReconstruct.app into a .dmg (macOS only; needs `create-dmg`,
# e.g. `brew install create-dmg`). Run from the repo root after PyInstaller.
#   PYR_PUBLIC=<version> ARCH=x86_64 bash packaging/macos/make_dmg.sh
set -euo pipefail

: "${PYR_PUBLIC:?set PYR_PUBLIC to the public version string}"
ARCH="${ARCH:-x86_64}"
APP="dist/PyReconstruct.app"
OUT="PyReconstruct-${PYR_PUBLIC}-macOS-${ARCH}.dmg"

[ -d "$APP" ] || { echo "error: $APP not found (build with PyInstaller first)" >&2; exit 1; }
rm -f "$OUT"

# --skip-jenkins skips the Finder/AppleScript window-styling step, which times
# out (AppleEvent -1712 / exit 64) on headless CI runners; hdiutil still writes
# a plain but valid $OUT. (The cosmetic --icon/--app-drop-link layout needs that
# AppleScript step, so it's intentionally dropped here.)
create-dmg \
    --volname "PyReconstruct ${PYR_PUBLIC}" \
    --no-internet-enable \
    --skip-jenkins \
    "$OUT" "$APP" || true

[ -f "$OUT" ] || { echo "error: create-dmg did not produce $OUT" >&2; exit 1; }
echo "wrote $OUT"
