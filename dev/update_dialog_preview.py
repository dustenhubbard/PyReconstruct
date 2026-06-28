"""Preview the in-app update dialog without a frozen build or a real release.

Run on a machine WITH a display (macOS / Windows):

    PYTHONPATH=<repo-root> <python-with-PySide6> dev/update_dialog_preview.py

It shows the UpdateDialog populated with sample data so you can sign off the
look (version line, channel, size, "What's new" notes, buttons). NOTE: the
"Download & Install" button points at a fake URL and will fail — this is a
LAYOUT preview; click "Later" to close.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication, QMainWindow
from PyReconstruct.modules.gui.dialog.update_dialog import UpdateDialog

INFO = {
    "release": {
        "tag_name": "v1.21.0",
        "body": (
            "## PyReconstruct 1.21.0\n\n"
            "### Highlights\n"
            "- **3–4× faster** opening large autoseg series\n"
            "- Theme now follows your system light/dark setting\n"
            "- Modernized tool-button icons\n\n"
            "### Fixes\n"
            "- Correctness audit of the performance rewrite\n"
            "- Assorted UI polish\n\n"
            "[Full changelog](https://github.com/dustenhubbard/PyReconstruct/releases)\n"
        ),
    },
    "asset": {
        "name": "PyReconstruct-1.21.0-macOS-arm64.dmg",
        "size": 96_300_000,
        "browser_download_url": "https://example.invalid/asset",
    },
    "remote_version": "1.21.0",
    "local_version": "1.20.0",
    "status": "newer",
}


def main():
    app = QApplication(sys.argv)
    parent = QMainWindow()
    parent._updater_pool = None
    parent._pending_installer = None
    parent._pending_update_dir = None
    parent.resize(700, 500)
    parent.show()
    UpdateDialog(parent, INFO, "release").exec()


if __name__ == "__main__":
    main()
