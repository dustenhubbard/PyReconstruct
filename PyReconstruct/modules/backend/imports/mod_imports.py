import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Union

from PyReconstruct.modules.gui.utils import notifyConfirm, notify as note


## Some optional modules are thin Python wrappers around a *native* library
## that they dlopen at import time. On those, a failed import raises OSError
## rather than ModuleNotFoundError, and reinstalling the Python package cannot
## fix it -- the remedy is a system package manager. Keyed by module name;
## the value is the human name of the library and the per-platform remedy.
NATIVE_LIBRARY_REMEDIES: Dict[str, Tuple[str, str]] = {
    "cairosvg": (
        "Cairo",
        "Debian/Ubuntu:  sudo apt-get install libcairo2\n"
        "macOS:          brew install cairo, then set "
        "DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib\n"
        "Windows:        put a Cairo DLL (libcairo-2.dll) on PATH"
    ),
}


def native_library_message(unloadable: Dict[str, OSError]) -> str:
    """Compose the notice shown when a module's native library will not load.

    Deliberately not a yes/no install prompt: `pip install` cannot supply a
    system library, so offering it would send the user down a path that cannot
    work.
    """
    lines = [
        "This feature needs a system library that is not installed (or not on "
        "the library search path). The Python package is installed correctly; "
        "reinstalling it will not help.\n"
    ]

    for module, exc in unloadable.items():

        library, remedy = NATIVE_LIBRARY_REMEDIES.get(module, ("", ""))
        heading = f"{module} could not load"
        if library:
            heading += f" the native {library} library"

        ## First line only: cairocffi reports every dlopen candidate it tried,
        ## which is a dozen paths of no use to a user in a modal dialog.
        detail = str(exc).splitlines()[0] if str(exc) else type(exc).__name__

        lines.append(f"{heading}:\n{detail}\n")

        if remedy:
            lines.append(f"{remedy}\n")

    return "\n".join(lines).rstrip()


def running_frozen() -> bool:
    """True when this is a PyInstaller bundle rather than a source install.

    PyInstaller sets ``sys.frozen``. Read through ``getattr`` because the
    attribute simply does not exist outside a bundle.
    """

    return bool(getattr(sys, "frozen", False))


def frozen_install_message(modules: List[str]) -> str:
    """Compose the notice shown when packages are missing from a frozen build.

    Deliberately not a yes/no install prompt, for the same reason
    ``native_library_message`` is not: the install on offer cannot succeed, and
    offering it sends the user down a path with no end. See ``install_module``
    for what a frozen bundle actually does with a pip command.
    """

    unavail_str = ", ".join(modules)

    return (
        f"This feature requires additional Python packages ({unavail_str}) "
        "that this copy of PyReconstruct does not include.\n\n"
        "PyReconstruct is running as a self-contained application bundle. It "
        "carries its own private Python, and packages cannot be added to it -- "
        "not from inside the app, and not with a `pip install` in a terminal, "
        "which would install into a different Python that this app cannot see."
        "\n\n"
        "To use this feature, run PyReconstruct from source and install the "
        "package into that environment. The project README has the from-source "
        "setup."
    )


def module_path(module: str) -> Path:
    """Return path to a module."""

    mod = __import__(module)
    mod_init = mod.__file__
    
    if not mod_init:
        
        _, submod = module.split(".")
        mod_init = getattr(mod, submod).__file__

    return Path(mod_init).parent
        

def modules_available(modules: Union[str, List[str]], notify: bool=True) -> bool:
    """Check if module available."""

    if not isinstance(modules, list):
        modules = [modules]

    unavailable = []

    ## Modules whose Python package is present but whose native library is
    ## not loadable. A separate bucket because it has a separate remedy.
    unloadable: Dict[str, OSError] = {}

    ## Test if modules unavailable
    for module in modules:

        try:

            __import__(module)

        except ModuleNotFoundError:

            unavailable.append(module)

        except OSError as e:

            ## e.g. `import cairosvg` -> cairocffi dlopens libcairo and
            ## raises OSError('no library called "cairo-2" was found').
            ## Uncaught, this reaches customExcepthook as a crash report.
            unloadable[module] = e

    if not unavailable and not unloadable:  # all modules available

        return True

    if notify:

        if unloadable:

            note(native_library_message(unloadable))

        if unavailable:

            ## Same principle as the native-library notice above: do not offer
            ## an install that cannot work. A frozen bundle cannot have packages
            ## added to it by any route (see `install_module`), so the yes/no
            ## prompt would be a dead end whichever way it is answered.
            if running_frozen():

                note(frozen_install_message(unavailable))

                return False

            unavail_str = ", ".join(unavailable)

            response = notifyConfirm(
                f"This feature requires additional Python packages to work ({unavail_str}). "
                "Would you like to install them into your current environment?",
                yn=True
            )

            if response == True:

                ## Catch modules with different names on pip install
                mod_pip_names = {
                    "cloudvolume": "cloud-volume",
                    "dask": "dask==2024.12.1"
                }

                for mod, pip_install_name in mod_pip_names.items():
                    if mod in unavailable:
                        index = unavailable.index(mod)
                        unavailable[index] = (mod, pip_install_name)

                pip_outcomes = map(install_module, unavailable)

                ## A successful pip install still does not make the feature
                ## usable if a native library is missing alongside it. Two
                ## cases, and they need separate handling: a *different* module
                ## in this same call already went into the unloadable bucket
                ## (`not unloadable`), or the just-installed module is itself
                ## the native wrapper, which `install_module` finds when it
                ## imports the module to report where it landed and reports
                ## by returning False.
                return all(list(pip_outcomes)) and not unloadable

    return False


def install_module(module: Union[str, Tuple[str, str]]) -> bool:
    """Interactively install a pip module."""

    if isinstance(module, tuple):
        
        module, pip_install_name = module
        
    else:
        
        pip_install_name = module

    ## A frozen bundle cannot install into itself, and must not try. Guarded
    ## here as well as at the prompt in `modules_available` because this
    ## function is exported and can be called on its own.
    ##
    ## `sys.executable` in a PyInstaller build is the app's own launcher, not a
    ## Python interpreter, and the bootloader does not interpret Python's
    ## command-line options: it hands `-m pip install <name>` to the app as
    ## `sys.argv`. Measured against a one-folder build -- the child process was
    ## a second copy of the app, which `capture_output=True` then waits on until
    ## it exits, and which exits 0, so the success branch below would report an
    ## install that never happened. The bare `pip` this used to run is no better
    ## in a bundle: it resolves off PATH to a *different* interpreter, so a
    ## genuinely successful install lands somewhere this process cannot import
    ## from, and `module_path`'s import then raises into `customExcepthook` --
    ## invisibly, since the spec builds with `console=False`.
    if running_frozen():

        note(frozen_install_message([module]))

        return False

    ## `sys.executable -m pip`, never a bare `pip`: the install has to target
    ## the same interpreter that is about to do the import. The argument list
    ## with `shell=False` also keeps the package name out of a shell.
    output = subprocess.run(
        [sys.executable, "-m", "pip", "install", pip_install_name],
        capture_output=True,
        text=True,
    )

    if output.returncode == 0:

        try:

            installed_to = module_path(module)

        except ImportError as e:

            ## pip reported success and the module still will not import, so it
            ## did not land where this process can see it -- a `--user` install
            ## that missed the environment, a `pip` shadowed by another
            ## interpreter, a package whose import name differs from its
            ## distribution name. Uncaught this reaches customExcepthook, which
            ## a `console=False` build shows the user nothing of. Report it with
            ## the command that would install into *this* interpreter, and count
            ## the install as failed: the feature is still unusable.
            note(
                f"{module} reported a successful install, but the running copy "
                f"of PyReconstruct still cannot import it:\n\n{e}\n\n"
                "The package was most likely installed into a different Python "
                "environment. Installing it by hand, in a terminal, with this "
                "exact command will target the right one:\n\n"
                f"    {sys.executable} -m pip install {pip_install_name}"
            )

            return False

        except OSError as e:

            ## pip succeeded but the package wraps a native library that will
            ## not load, so `module_path`'s own `__import__` raises the OSError
            ## `modules_available`'s probe already handles. Uncaught here it
            ## reaches customExcepthook as a crash report. Report the real
            ## remedy and count the install as failed: the feature is still
            ## unusable, and re-offering pip cannot supply a system library.
            note(native_library_message({module: e}))

            return False

        note(
            f"{module} successfully installed to:\n\n{installed_to}"
        )

        return True

    else:

        note(
            "Something went wrong. "
            f"Please try pip installing {module} in a terminal."
        )

        return False


def is_conda_package_installed(package_name: str) -> bool:
    """Check if conda package installed"""

    try:
        
        result = subprocess.run(
            ['conda', 'list', package_name], capture_output=True, text=True, check=True
        )

        results = result.stdout.strip().split("\n")
        
        results = [line for line in results if not line.startswith("#")]
        
        if not results:
            
            return False
        
        else:
            
            return True
    
    except subprocess.CalledProcessError:
        
        return False

