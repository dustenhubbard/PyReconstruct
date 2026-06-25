"""Headless smoke test for CI / local checks.

Builds a QApplication, renders a VTK scene offscreen, and imports the app's GUI
and 3D-viewport modules. Run this BEFORE packaging so a broken build (most
likely a VTK OpenGL backend that is missing from the freeze) fails fast instead
of shipping a blank 3D viewport to users.

    QT_QPA_PLATFORM=offscreen python packaging/smoke_test.py

Offscreen VTK still needs an OpenGL context; CI Windows/macOS runners provide
one. On headless Linux, run under xvfb (e.g. `xvfb-run -a`) with software GL.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

# Force-register the OpenGL2 render factory, then render a sphere offscreen.
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
import vtk

render_window = vtk.vtkRenderWindow()
render_window.SetOffScreenRendering(1)
renderer = vtk.vtkRenderer()
render_window.AddRenderer(renderer)

mapper = vtk.vtkPolyDataMapper()
mapper.SetInputConnection(vtk.vtkSphereSource().GetOutputPort())
actor = vtk.vtkActor()
actor.SetMapper(mapper)
renderer.AddActor(actor)
render_window.Render()

grab = vtk.vtkWindowToImageFilter()
grab.SetInput(render_window)
grab.Update()
dims = grab.GetOutput().GetDimensions()
assert dims[0] > 0 and dims[1] > 0, f"VTK produced no image (dims={dims})"

# Import the app's GUI package and the 3D-viewport module (the render-risk path).
import PyReconstruct.modules.gui.main  # noqa: F401
import PyReconstruct.modules.gui.popup.custom_plotter  # noqa: F401

from PyReconstruct.modules.constants import repo_string

print(f"smoke OK: {repo_string} | VTK offscreen image {dims}")
