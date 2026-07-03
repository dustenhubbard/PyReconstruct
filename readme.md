[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

<a id="pyreconstruct"></a>

# PyReconstruct

PyReconstruct is an actively maintained, extensible version of _Reconstruct_ written in Python in the lab of Kristen Harris at the University of Texas at Austin. Please check out [our paper](https://doi.org/10.1073/pnas.2505822122) introducing PyReconstruct and feel free to send us a message if you have any questions:

-   Michael Chirillo: michael.chirillo@uri.edu
-   Dusten Hubbard: dusten@utexas.edu

<a id="documentation"></a>

# Documentation

An installation guide, quickstart, and manuals can be found at our lab's [wiki site](https://wikis.utexas.edu/display/khlab/PyReconstruct+user+guide) hosted at UT Austin and at the [PyReconstruct repo wiki](https://github.com/SynapseWeb/PyReconstruct/wiki). A quick launch guide follows below.

<a id="submitting-bug-reports-and-feature-requests"></a>

# Installation

PyReconstruct can be installed into a virtual environment using the command line or it can be installed using a graphical installer similar to a normal desktop app.

## Install PyReconstruct into a virtual environment

In a virtual environment running Python 3.11, install bleeding-edge PyReconstruct:

```
pip install git+https://github.com/synapseweb/pyreconstruct
```

or stable PyReconstruct:

```
pip install pyreconstruct
```

then launch PyReconstruct from the command line:

```
PyReconstruct
```

To install a dev version of PyReconstruct, see [here](https://github.com/SynapseWeb/PyReconstruct/wiki/Developers).

## Install PyReconstruct using a graphical installer

Not comfortable using command line? You can install PyReconstruct like a normal desktop app by [downloading an installer](https://github.com/SynapseWeb/PyReconstruct/releases) and following the instructions below.

(Note for Windows and macOS users: PyReconstruct isn't yet "code-signed", which means you must explicitly give your system permission to run the app. The steps below walk you through this process.)

### Windows

Download the `.exe` installer for Windows and open it. Your system may warn you this PyReconstruct isn't yet "code-signed". If you trust us, simply click **More info** then **Run anyway**.

### macOS

Download the `.dmg` installer, open it, and drag PyReconstruct into your Applications folder. Your system may warn you that PyReconstruct isn't yet "code-signed" and a short **Read Before First Launch** note that walks you through the process.

### Linux

Download the installer shell script and run it. This will add PyReconstruct to your applications menu.

# Bug reports / Feature requests

If you notice a problem, would like to suggest a feature, or have ideas on improving our documentation, please [submit an issue](https://github.com/SynapseWeb/PyReconstruct/issues/). We appreciate the help!

# Citation

If you use PyReconstruct in published work, please cite [our paper](https://doi.org/10.1073/pnas.2505822122):

```
@article{Chirillo2025,
	title = {{PyReconstruct}: {A} fully open-source, collaborative successor to {Reconstruct}},
	author = {Chirillo, Michael A. and Falco, Julian N. and Musslewhite, Michael D. and Lindsey, Larry F. and Harris, Kristen M.},
	journal = {Proceedings of the National Academy of Sciences},
	volume = {122},
	number = {31},
	pages = {e2505822122},
	year = {2025},
	month = {July},
	doi = {10.1073/pnas.2505822122},
	url = {https://www.pnas.org/doi/10.1073/pnas.2505822122}
}
```

and this repo if you'd like:

```
@software{Falco2025,
    author = {Kristen Harris Lab},
    title = {PyReconstruct},
    version = {1.20.0},
    month = {June},
    year = {2026}
    url = {https://github.com/synapseweb/pyreconstruct},
}
```
