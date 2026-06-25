# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for PyReconstruct (one-folder build).

Run from the repository root, after installing the project + PyInstaller into a
Python 3.11 environment (`pip install -e .` writes PyReconstruct/_version.py):

    pyinstaller --noconfirm packaging/PyReconstruct.spec

Output:
    Windows : dist/PyReconstruct/PyReconstruct.exe
    macOS   : dist/PyReconstruct.app   (needs packaging/PyReconstruct.icns first)

NOTE on VTK: vtk is pinned to 9.3.1, which predates pyinstaller-hooks-contrib's
vtkmodules coverage (>=9.4.2). The explicit hiddenimports below force the OpenGL
render stack so the 3D viewport is not a blank window. If the viewport still
renders blank in the frozen build, the fallbacks (in priority order) are:
bump vtk to 9.4.x (gets the official hook), or build via conda constructor.
"""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# SPECPATH is the absolute path of the directory containing this spec (packaging/).
REPO_ROOT = Path(SPECPATH).parent
PKG_DIR = REPO_ROOT / "PyReconstruct"
ASSETS = PKG_DIR / "assets"
ENTRY = str(PKG_DIR / "run.py")

datas = []
binaries = []
hiddenimports = []

# --- App assets: welcome series, icons, the "checker" data, and the helper .py
#     scripts that run.py relaunches via runpy. Bundle the full tree at
#     <_MEIPASS>/PyReconstruct/assets so locations.py (frozen branch) finds it.
for _p in ASSETS.rglob("*"):
    if _p.is_file():
        _dest = Path("PyReconstruct/assets") / _p.relative_to(ASSETS).parent
        datas.append((str(_p), str(_dest)))

# --- setuptools-scm version file (frozen repo_info reads PyReconstruct._version)
_version_file = PKG_DIR / "_version.py"
if _version_file.exists():
    datas.append((str(_version_file), "PyReconstruct"))

# --- VTK 9.3.1: collect everything, then force the render/interaction modules
#     that the import graph misses (cause of the classic blank 3D viewport).
_vd, _vb, _vh = collect_all("vtkmodules")
datas += _vd
binaries += _vb
hiddenimports += _vh
hiddenimports += [
    "vtkmodules.vtkRenderingOpenGL2",         # <- the key one (GL2 render factory)
    "vtkmodules.vtkRenderingFreeType",
    "vtkmodules.vtkRenderingUI",
    "vtkmodules.vtkRenderingVolumeOpenGL2",
    "vtkmodules.vtkRenderingContextOpenGL2",
    "vtkmodules.vtkRenderingAnnotation",
    "vtkmodules.vtkInteractionStyle",
    "vtkmodules.vtkInteractionWidgets",
    "vtkmodules.vtkRenderingCore",
    "vtkmodules.vtkCommonCore",
    "vtkmodules.vtkCommonDataModel",
    "vtkmodules.vtkCommonExecutionModel",
    "vtkmodules.vtkCommonMath",
    "vtkmodules.vtkCommonTransforms",
    "vtkmodules.vtkFiltersCore",
    "vtkmodules.vtkFiltersGeneral",
    "vtkmodules.vtkFiltersSources",
    "vtkmodules.vtkFiltersModeling",
    "vtkmodules.vtkIOImage",
    "vtkmodules.vtkIOXML",
    "vtkmodules.vtkIOGeometry",
    "vtkmodules.util.numpy_support",
    "vtkmodules.util.execution_model",
    "vtkmodules.qt",
    "vtkmodules.qt.QVTKRenderWindowInteractor",
    "vtk",
]

# --- vedo data (fonts, textures, colormaps) ---
datas += collect_data_files("vedo")

# --- scipy / scikit-image: lazily-imported submodules + data files ---
hiddenimports += collect_submodules("scipy")
hiddenimports += collect_submodules("skimage")
datas += collect_data_files("skimage")

# --- cloud-volume and its compiled codecs (best-effort; import names vary and
#     not all expose data/hooks). Failures here only affect remote-volume use.
for _pkg in (
    "cloudvolume", "DracoPy", "compressed_segmentation", "fpzip",
    "compresso", "crackle", "zfpc", "numcodecs", "zarr", "fastremap",
):
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception:
        pass

# --- trimesh data ---
datas += collect_data_files("trimesh")

block_cipher = None

a = Analysis(
    [ENTRY],
    pathex=[str(REPO_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[str(REPO_ROOT / "packaging" / "rthook_qt.py")],
    excludes=[
        "PyQt5", "PyQt6", "PySide2",   # forbid clashing Qt bindings
        "tkinter",
        "matplotlib.tests",
        "cv2.qt",                       # belt-and-suspenders (we ship cv2 headless)
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

is_win = sys.platform.startswith("win")
is_mac = sys.platform == "darwin"

win_icon = str(PKG_DIR / "assets" / "img" / "PyReconstruct.ico")
mac_icon = str(REPO_ROOT / "packaging" / "PyReconstruct.icns")  # built by make_icns.sh

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PyReconstruct",
    console=False,            # windowed (no console window)
    icon=win_icon if is_win else (mac_icon if is_mac else None),
    upx=False,                # UPX corrupts Qt/VTK shared libraries
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="PyReconstruct",
    upx=False,
)

if is_mac:
    app = BUNDLE(
        coll,
        name="PyReconstruct.app",
        icon=mac_icon,
        bundle_identifier="edu.utexas.synapseweb.pyreconstruct",
        info_plist={"NSHighResolutionCapable": True},
    )
