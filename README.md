# AITW-Darcy-Infiltration-Model

This project contains code for simulating infiltration processes in porous materials using the FEniCSx finite element framework.

## Install

> [!NOTE] External Requirements
> Requires a working installation of `fenics-dolfinx==0.9.0` (see https://fenicsproject.org/download/) -
> Main FEniCS library + Python bindings.

```bash
cd <PATH to folder with pyproject.toml>
pip install .
```

## Description

The simulation models capillary infiltration in porous media using:
- 3D finite element mesh (hexahedral elements)
- Nonlinear saturation curve based on pore size distribution
- Adaptive timestepping for convergence
- Parallel computing support via MPI

### Key Features

- **Mesh**: 3D rectangular domain with configurable dimensions
- **Physics**: Capillary pressure, surface tension, contact angle effects
- **Material properties**: Porosity, permeability (anisotropic), pore radius distribution
- **Solver**: Newton-Raphson with adaptive timestepping
- **Output**: VTX files for visualization and numpy arrays for data analysis

## Usage

### Progamatically

Example.

```python
from aitw_darcy.data import Params
from aitw_darcy.infiltration import run_simulation

params = Params()
params.XXX = YYY  # Set parameters as needed

run_simulation(params)
```

### CLI

The installation will make available a `aitw-darcy` command line interface.

- Run `aitw-darcy --help` to see the available commands.
- Run `aitw-darcy infiltration --help` to see all available options for running the simulation.
- Run `aitw-darcy infiltration --config-file INPUT_JSON_FILE` to run the simulation using the parameters in `JSON_FILE`.

Example with the provided parameter file:

```bash
aitw-darcy infiltration --config-file examples/small.json
```

### Using multiple processes

The code supports parallel execution using MPI. To run the simulation with multiple processes, use `mpirun` or `mpiexec`:

```bash
mpirun -np 4 aitw-darcy infiltration --config-file examples/small.json
```

Also make sure to set the `OMP_NUM_THREADS` environment variable to control the number of threads per process.
If left unset it is possible that the simulation will use all available threads on the machine, which may lead to performance degradation.
For example, to use 4 processes with 2 threads each:

```bash
export OMP_NUM_THREADS=2
mpirun -np 4 aitw-darcy infiltration --config-file examples/small.json
```

#### Tab autocompletion

Enabling tab autocompletion https://click.palletsprojects.com/en/stable/shell-completion/

E.G for `bash` run the command

```bash
eval "$(_AITW_DARCY_COMPLETE=bash_source aitw-darcy)"
```

You can also add it to either `~/.bashrc` or, if you are using a virtual environment, to `bin/activate` of the virtual environment to avoid running the command for every new shell.

## Output

The simulation generates the following output files in the specified output directory `{output_dir}`:

- `{label}_solution.npy` - Complete solution array for analysis
- `{label}_output.bp` - VTX mesh files for ParaView visualization
- `{label}.log` - Simulation log file
- `{label}.json` - Copy of the input parameters for reproducibility + final saturation time

where `{label}` is defined in the input parameters.

## Parameters

Key simulation parameters:

- Mesh dimensions and resolution
- Material properties (porosity, permeability, surface tension)
- Fluid properties (viscosity, contact angle)
- Pore size distribution parameters
- Timestepping control
- Boundary conditions

---

*Part of the AITW project at VTT Technical Research Centre of Finland*
