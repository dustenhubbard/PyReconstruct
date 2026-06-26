import os, sys, importlib
from pathlib import Path

import PySide6
from PySide6.QtWidgets import QApplication


if __name__ == "__main__":

    # set up imports for run.py location
    run_script = Path(__file__)
    pypath = str(run_script.parents[1])
    sys.path.append(pypath)


import PyReconstruct.modules.gui.main as main


def runPyReconstruct(filename=None):

    # Stopgap for Wayland Qt issue (only needed from source; in a frozen bundle
    # PyInstaller's PySide6 hook wires the plugin path, and this PySide6.__file__
    # location would be wrong).
    # stackoverflow.com/questions/68417682/qt-and-opencv-app-not-working-in-virtual-environment
    if not getattr(sys, "frozen", False):
        ps6_dir = Path(PySide6.__file__).parent
        qt_plugins = ps6_dir / "Qt/plugins"
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(qt_plugins)

    # create the Qt Application
    app = QApplication(sys.argv)

    if sys.platform == "darwin" and _macos_keep_running():
        _run_macos(app, filename)
    else:
        _run_with_restart_loop(app, filename)


def _macos_keep_running():
    """User setting (macOS): keep the app alive in the Dock after the window is
    closed, instead of quitting. Read straight from QSettings so it applies at
    launch; default True (the Mac-native behavior)."""
    from PySide6.QtCore import QSettings
    return QSettings("KHLab", "PyReconstruct").value(
        "macos_keep_running_on_close", True, type=bool
    )


def _run_with_restart_loop(app, filename):
    """Windows/Linux: closing the (last) window quits the app; the in-app
    Restart reloads PyReconstruct modules and recreates the window."""
    run = True
    while run:
        main_window = main.MainWindow(filename)
        app.exec()
        if main_window.restart_mainwindow:  # restart requested
            if not main_window.series.isWelcomeSeries():
                filename = main_window.series.jser_fp
            loaded_modules = list(sys.modules.items())
            for module_name, module in loaded_modules:
                if module_name.startswith("PyReconstruct.modules"):
                    importlib.reload(module)
        else:
            run = False


def _run_macos(app, filename):
    """macOS: closing the window keeps the app running (in the Dock); activating
    the app with no open window reopens a fresh welcome window. Quit is Cmd+Q.

    (The in-app Restart action is a known rough edge here -- since closing no
    longer quits, it drops to the welcome window rather than reloading the same
    series; to be refined after testing the core behavior.)"""
    from PySide6.QtCore import Qt
    app.setQuitOnLastWindowClosed(False)
    holder = {"win": None}

    def open_window(fn):
        holder["win"] = main.MainWindow(fn)

    def on_state_changed(state):
        if state == Qt.ApplicationActive:
            win = holder["win"]
            if win is None or not win.isVisible():
                open_window(None)  # fresh welcome series

    open_window(filename)  # create the first window before connecting the handler
    app.applicationStateChanged.connect(on_state_changed)
    app.exec()


if __name__ == "__main__":

    # Frozen-build script dispatcher: a PyInstaller exe can't execute an
    # arbitrary .py via sys.executable, so bundled helper scripts are relaunched
    # as `<exe> __run_script__ <script.py> [args...]` and run here via runpy.
    if len(sys.argv) > 2 and sys.argv[1] == "__run_script__":

        import runpy
        script = sys.argv[2]
        sys.argv = [script] + sys.argv[3:]
        runpy.run_path(script, run_name="__main__")

    elif "--selftest" in sys.argv[1:]:

        # Reaching here means the full GUI/vedo import chain (imported at module
        # load, above) succeeded. CI runs the frozen exe with this flag to catch
        # windowed-only import failures (e.g. None stdout) without launching the UI.
        print("selftest ok")
        sys.exit(0)

    else:

        filename = sys.argv[1] if len(sys.argv) > 1 else None
        runPyReconstruct(filename)
