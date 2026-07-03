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

# Then it would say lanch party, Kevin.

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

# Install with an installer (no command line)

Prefer to install PyReconstruct like a normal desktop app? Grab an installer for your operating system from the [Releases page](https://github.com/SynapseWeb/PyReconstruct/releases). No Python or command line needed, and everything the app requires is bundled in.

- **Windows.** Download the `.exe` and run it. The first time, Windows may warn that it "protected your PC" because the app isn't code-signed yet; click **More info**, then **Run anyway**.
- **macOS.** Download the `.dmg`, open it, and drag PyReconstruct into your Applications folder. Because the app isn't signed yet, the first launch takes one extra step; the disk image includes a short **"Read Before First Launch"** note that walks you through it.
- **Linux.** Download the `.sh` installer and run it. It adds PyReconstruct to your applications menu.

*(Code signing, which removes those first-launch warnings, is on the way.)*

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
