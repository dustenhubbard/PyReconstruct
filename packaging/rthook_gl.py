# Windows software-OpenGL fallback.
#
# VTK 9's renderer needs OpenGL >= 3.2. On an RDP session or a GPU-less VM the
# system opengl32.dll provides only OpenGL 1.1; VTK then calls a null GL function
# pointer when the 3D viewport opens, crashing the whole app (access violation at
# offset 0, with an "unknown" faulting module). The spec bundles Qt's software GL
# implementation (Mesa llvmpipe) as mesa/opengl32.dll. Here we PRELOAD it -- but
# only when hardware GL is inadequate -- so the loader resolves the later
# "opengl32.dll" imports (Qt's and VTK's) to the software build. Preloading by
# absolute path registers the module under its base name "opengl32.dll", so
# subsequent base-name loads return the already-loaded software DLL regardless of
# the normal DLL search order. GPU machines skip this and keep hardware OpenGL.
import os
import sys


def _should_use_software_gl():
    # Explicit overrides win, in both directions.
    if os.environ.get("PYRECON_SOFTWARE_GL"):
        return True
    if os.environ.get("PYRECON_HW_OPENGL"):
        return False
    # Auto: a remote-desktop session has no usable hardware OpenGL.
    try:
        import ctypes
        SM_REMOTESESSION = 0x1000
        if ctypes.windll.user32.GetSystemMetrics(SM_REMOTESESSION):
            return True
    except Exception:
        pass
    return False


if sys.platform.startswith("win") and getattr(sys, "frozen", False):
    if _should_use_software_gl():
        try:
            import ctypes
            _sw = os.path.join(sys._MEIPASS, "mesa", "opengl32.dll")
            if os.path.exists(_sw):
                ctypes.WinDLL(_sw)  # preload before Qt/VTK pull in opengl32
                print(f"[gl] software OpenGL preloaded: {_sw}", flush=True)
            else:
                print(f"[gl] software OpenGL not bundled: {_sw}", flush=True)
        except Exception as e:
            print(f"[gl] software OpenGL preload failed: {e!r}", flush=True)
