"""First-launch "What's new" dialog.

Shows what changed since the user's last-seen version -- on a fresh install or
after an update that may span several versions -- and can be reopened on demand
from Help -> What's new. It is a normal, dismissible, *modeless* dialog: it never
blocks startup or steals focus the way a prompt would.

This is the *only* place the app puts release notes in front of the user
unasked, and it does so once per version. The updater dialog deliberately does
not render them: at that point the notes describe a version the user has not
installed, so showing them there meant the same notes appeared twice around
every update.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
)
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import Qt, QSettings

from PyReconstruct.modules.backend.updater.install_info import current_version_str
from PyReconstruct.modules.gui.main.first_launch import (
    whats_new_due, whats_new_content, github_release_url, WHATSNEW_KEY,
    ON_DEMAND_CAP,
)

ORG, APP = "KHLab", "PyReconstruct"


def _space_after_headings(browser, extra=10):
    """Add breathing room below markdown headings in a notes browser.

    Qt's ``setMarkdown`` ignores the document default stylesheet, so we walk the
    blocks and bump the bottom margin on heading blocks instead. Applies to
    whatever headings the notes carry.
    """
    doc = browser.document()
    cursor = QTextCursor(doc)
    block = doc.begin()
    while block.isValid():
        fmt = block.blockFormat()
        if fmt.headingLevel() > 0:
            fmt.setBottomMargin(fmt.bottomMargin() + extra)
            cursor.setPosition(block.position())
            cursor.setBlockFormat(fmt)
        block = block.next()


def make_notes_browser(markdown_text, min_height=180):
    """Build a read-only ``QTextBrowser`` that renders release-note markdown.

    Falls back to plain text if the markdown can't be rendered.
    """
    text = markdown_text or "_No release notes were published._"
    browser = QTextBrowser()
    browser.setOpenExternalLinks(True)
    try:
        browser.setMarkdown(text)
        _space_after_headings(browser)
    except Exception:
        browser.setPlainText(text)
    browser.setMinimumHeight(min_height)
    return browser


class WhatsNewDialog(QDialog):
    """A dismissible, modeless summary of what changed since the last-seen version."""

    def __init__(self, parent, version, last_seen=None, content=None, url=None):
        super().__init__(parent)
        self._version = version
        if content is None:
            content = whats_new_content(version, last_seen)
        if url is None:
            url = github_release_url(version)

        self.setWindowTitle(
            f"What's new in PyReconstruct {version}" if version
            else "What's new in PyReconstruct"
        )
        self.setMinimumWidth(540)
        self.setModal(False)  # modeless: does not block the app

        lay = QVBoxLayout(self)

        # prominent version header, with the release date beneath it -- omitted
        # when the running version is unknown (never render "None"; the
        # orienter below then leads the dialog)
        if content["version"]:
            title = QLabel(f"PyReconstruct {content['version']}")
            tf = title.font()
            tf.setBold(True)
            tf.setPointSize(18 if tf.pointSize() <= 0 else tf.pointSize() + 6)
            title.setFont(tf)
            lay.addWidget(title)

        if content.get("date"):
            released = QLabel(f"Released {content['date']}")
            released.setEnabled(False)  # muted, secondary to the version
            lay.addWidget(released)

        orienter = QLabel(content["orienter"])
        of = orienter.font()
        of.setItalic(True)
        orienter.setFont(of)
        lay.addWidget(orienter)

        # The notes browser renders the release notes and nothing else. The
        # maintainer provenance line used to be appended to the end of this
        # markdown, below a rule, which put it inside the scroll: on a release
        # with more than a screenful of notes -- the normal case -- a reader had
        # to scroll to the bottom to find out who maintains this build, and most
        # never did. It is now its own widget below the browser (see below), so
        # it is on screen from the moment the dialog opens.
        self._notes = make_notes_browser(content["body"], min_height=260)
        lay.addWidget(self._notes)

        # The provenance line itself: quiet and italic, the same register the
        # markdown `_..._` gave it, so it still reads as an aside about who
        # maintains this build rather than as one more release bullet. Italic
        # from the font (as the orienter above does) and muted by
        # `setEnabled(False)` (as the release date does) -- this dialog has no
        # shared muted-label helper and those are its two existing idioms for
        # secondary text. It comes from the builder as its own field and is the
        # same on every framing (update, welcome, on-demand, generic fallback);
        # rendering it here, once, is the only place it appears, so it can never
        # double up with the notes above it. Some framings carry no byline, and
        # then no widget is added at all.
        byline = content.get("byline")
        if byline:
            self._byline = QLabel(byline)
            bf = self._byline.font()
            bf.setItalic(True)
            self._byline.setFont(bf)
            self._byline.setEnabled(False)  # muted, secondary to the notes
            self._byline.setWordWrap(True)
            lay.addWidget(self._byline)
        else:
            self._byline = None

        link = QLabel(f'<a href="{url}">Full release notes on GitHub ↗</a>')
        link.setTextFormat(Qt.RichText)
        link.setOpenExternalLinks(True)
        lay.addWidget(link)

        row = QHBoxLayout()
        row.addStretch(1)
        close_btn = QPushButton("Got it")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        lay.addLayout(row)


def _default_show(parent, version, last_seen=None, content=None):
    """Construct and show the dialog modelessly, transiently."""
    dialog = WhatsNewDialog(parent, version, last_seen=last_seen, content=content)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    if parent is not None:
        # Hold a reference so the modeless dialog isn't garbage-collected before
        # it shows, and drop it once dismissed so nothing lingers on the window.
        parent._whatsnew_dialog = dialog
        dialog.finished.connect(lambda *_: setattr(parent, "_whatsnew_dialog", None))
    dialog.show()
    return dialog


def maybe_show_whats_new(parent, settings=None, current=None, show=None,
                         key=WHATSNEW_KEY):
    """Show the What's-new dialog once per version; record the version seen.

    The pure gate lives in ``whats_new_due``; this wires it to QSettings and the
    dialog. The stored last-seen version is threaded into the builder so the
    dialog can summarise everything missed since then. ``settings`` / ``current``
    / ``show`` are injectable for headless testing. Returns True if shown.
    """
    if settings is None:
        settings = QSettings(ORG, APP)
    if current is None:
        current = current_version_str()
    stored = settings.value(key)
    if not whats_new_due(stored, current):
        return False
    (show or _default_show)(parent, current, stored)
    settings.setValue(key, current)
    return True


def show_whats_new(parent, current=None, show=None):
    """Show the What's-new dialog on demand (Help -> What's new).

    Unlike ``maybe_show_whats_new`` there is no once-per-version gate and the
    stored last-seen version is neither consulted nor updated: the dialog always
    opens on the running version's notes rather than a fresh-install welcome.
    Earlier releases are reached through the truncation line and the "Full
    release notes on GitHub" link rather than being listed in full; see
    ``ON_DEMAND_CAP`` for why this path is capped tighter than the post-update
    one. ``current`` / ``show`` are injectable for headless testing. Returns the
    dialog.
    """
    if current is None:
        current = current_version_str()
    content = whats_new_content(current, on_demand=True, cap=ON_DEMAND_CAP)
    return (show or _default_show)(parent, current, content=content)
