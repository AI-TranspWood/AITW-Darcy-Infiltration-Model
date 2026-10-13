"""Module for running infiltration simulation using Darcy's law."""
import json
import os

import numpy as np
import ufl
from basix.ufl import element
from dolfinx import default_scalar_type, fem, io, log, mesh
from dolfinx.fem.petsc import NonlinearProblem
from dolfinx.nls.petsc import NewtonSolver
# from matplotlib import pyplot
from mpi4py import MPI
# from petsc4py import PETSc
from tqdm import tqdm
from ufl import cos, dot, dx, erf, grad, pi, sqrt

from .data import DarcyParams


def run_simulation(parameters: DarcyParams, visualize: bool = False):
    """ Run the infiltration simulation with given parameters"""
    io_node = MPI.COMM_WORLD.rank == 0
    def mpi_print(msg):
        if io_node:
            print(msg)

    # MPI + OpenMP info
    threads = os.environ.get('OMP_NUM_THREADS', os.cpu_count())
    mpi_print(f'Running infiltration simulation with {MPI.COMM_WORLD.size} MPI processes and {threads} OpenMP threads')

    label = parameters.label
    xmin = parameters.xmin
    xmax = parameters.xmax
    ymin = parameters.ymin
    ymax = parameters.ymax
    zmin = parameters.zmin
    zmax = parameters.zmax
    nx = parameters.nx
    ny = parameters.ny
    nz = parameters.nz
    delta_t0 = parameters.delta_t0
    delta_tmin = parameters.delta_tmin
    delta_tmax = parameters.delta_tmax
    t_end = parameters.t_end

    porosity_phi = parameters.porosity
    surf_tens_gamma = parameters.surface_tension
    c_ang = parameters.contact_angle

    mean_pore_radius = parameters.mean_pore_radius
    rstd = parameters.rstd

    r_cutoff = parameters.r_cutoff

    k_long = parameters.k_long
    k_trans = parameters.k_trans

    viscosity = parameters.viscosity
    u_ext = parameters.u_ext

    output_dir = parameters.output_dir

    # Output
    solution_file = f'{label}_solution.npy'   # Full solution
    visualization_dir = f'{label}_output.bp'        # VTX mesh for visualization

    # Ensure output directory exist
    if os.path.exists(output_dir):
        mpi_print(f'Output directory {output_dir} already exists. Files may be overwritten.')

    os.makedirs(output_dir, exist_ok=True)
    json_file = os.path.join(output_dir, f'{label}.json')
    solution_file = os.path.join(output_dir, solution_file)
    visualization_dir = os.path.join(output_dir, visualization_dir)
    log_file = os.path.join(output_dir, f'{label}.log')

    log.set_output_file(log_file)
    mpi_print(f'Log file: {log_file}')
    log.set_log_level(log.LogLevel.INFO)

    # Helper functions

    def get_variable_value(v):
        """ Get the nodal values for an expression v """
        q = fem.Function(V)
        q.interpolate(fem.Expression(v, V.element.interpolation_points()))
        return q.x.array

    def ramp_up(val=1, t1=0.1):
        """ Linear ramp from zero beginning for t = 0, useful to assist convergence in the beginning """
        return val*ufl.min_value(1, t/t1)

    # Generate 3D mesh
    domain = mesh.create_box(
        MPI.COMM_WORLD,
        [[xmin, ymin, zmin], [xmax, ymax, zmax]], [nx, ny, nz],
        mesh.CellType.hexahedron
    )

    x = ufl.SpatialCoordinate(domain)

    # Current time and time step size
    t = fem.Constant(domain, default_scalar_type(0))
    delta_t = fem.Constant(domain, default_scalar_type(delta_t0))

    # Create function space
    P1 = element('Lagrange', domain.basix_cell(), 1)
    V = fem.functionspace(domain, P1)

    # Unknown solution (t=n+1)
    u = fem.Function(V, name='u')

    # Previous time step solution
    u_n = fem.Function(V, name='u_n')

    # Saturation curve
    def S_curve(r):
        sigma = rstd*mean_pore_radius
        return 1/2*(erf((r-mean_pore_radius)/(sqrt(2)*sigma)) - erf((r_cutoff-mean_pore_radius)/(sqrt(2)*sigma)))

    # Capillary radius
    theta = c_ang*pi/180
    r_c = -2*surf_tens_gamma*cos(theta)/u

    # Saturation
    #S = ufl.conditional(u < 0, S_curve(r_c), 1.0)
    S = S_curve(r_c)

    # Previous saturation
    S_n = ufl.replace(S, {u: u_n})

    # Flux
    k = ufl.as_tensor([[k_long, 0, 0], [0, k_trans, 0], [0, 0, k_trans]])
    k_s = 1 + ramp_up(-1+S)
    J = -k_s*k/viscosity*grad(u)

    ###############
    # Weak form
    ###############

    delta_u = ufl.TestFunction(V)

    F = delta_u * porosity_phi*(S - S_n) * dx - delta_t*dot(grad(delta_u), J) * dx

    # Direchlet boundary conditions

    fdim = domain.topology.dim - 1
    domain.topology.create_connectivity(fdim, fdim+1)
    boundary_facets = mesh.exterior_facet_indices(domain.topology)
    boundary_dofs = fem.locate_dofs_topological(V, fdim, boundary_facets)
    bc = fem.dirichletbc(default_scalar_type(u_ext), boundary_dofs, V)
    bcs = [bc]

    # Initial pressure
    u0 = -2*surf_tens_gamma*cos(theta)/r_cutoff

    # Initial moisture content
    u.interpolate(lambda x: np.full(x[0].shape, u0))
    u.x.array[boundary_dofs] = u_ext

    # Initialize the Newton solver
    problem = NonlinearProblem(F, u, bcs)
    # solver = NewtonSolver(MPI.COMM_WORLD, problem)
    solver = NewtonSolver(MPI.COMM_WORLD, problem)
    # Solution is rather sensitive to tolerance,
    # numerical accuracy seems to be close to 1e-11
    solver.rtol = 0
    solver.atol = 1e-11
    solver.report = True
    solver.error_on_nonconvergence = False
    solver.max_it = 10
    solver.relaxation_parameter = 0.8

    # Use mumps LU solver
    ksp = solver.krylov_solver
    ksp.setType('preonly')
    ksp.getPC().setType('lu')
    ksp.getPC().setFactorSolverType('mumps')

    # Solutions at each time step
    sol = [u.x.array.copy()]

    # Time values
    times = [t.value.item()]

    if domain.comm.rank == 0:
        pbar = tqdm(total=t_end, unit_scale=True)

    S_func = fem.Function(V, name='S')

    output_data = {
        # Store the input parameters for reproducibility
        'input_parameters': parameters.to_dict(),
    }

    def loop(visualize=visualize):
        while True:
            u_n.x.array[:] = u.x.array

            # Adaptive timestepping
            while True:
                n, converged = solver.solve(u)
                if converged:
                    solver.relaxation_parameter = 0.8
                    if n <= 3:
                        delta_t.value = min(delta_t.value * 1.2, delta_tmax)
                        log.log(log.LogLevel.INFO, f'Timestep = {delta_t.value}')
                    elif n >= 7:
                        delta_t.value = delta_t.value * 0.5
                        log.log(log.LogLevel.INFO, f'Timestep = {delta_t.value}')
                    break
                else:
                    solver.relaxation_parameter = 0.4
                    delta_t.value = delta_t.value * 0.5
                    if delta_t.value < delta_tmin:
                        raise RuntimeError('Minimum timestep size reached!')
                    u.x.array[:] = u_n.x.array
                    log.log(log.LogLevel.INFO, f'Timestep = {delta_t.value}')

            t.value += delta_t.value

            # Record values
            sol.append(u.x.array.copy())
            times.append(t.value.item())

            if domain.comm.rank == 0:
                pbar.update(delta_t.value)

            # Save output
            S_func.interpolate(fem.Expression(S, V.element.interpolation_points()))
            if visualize:
                vtxfile.write(t.value.item())

            # Termination criterion
            if t.value > t_end:
                break

            S_threshold = 0.99
            S_vals = get_variable_value(S)
            finished = np.all(S_vals > S_threshold)
            statuses = domain.comm.gather(finished, root=0)
            can_stop = None
            if domain.comm.rank == 0:
                can_stop = all(statuses)
            if domain.comm.bcast(can_stop, root=0):
                break

        saturation_time = t.value.item()
        mpi_print(f'Simulation finished at t = {saturation_time}')
        output_data['sat_time'] = saturation_time

    if visualize:
        mpi_print(f'Writing files for VTX mesh visualization to {visualization_dir}')
        with io.VTXWriter(domain.comm, visualization_dir, [u, S_func]) as vtxfile:
            loop(visualize=True)
    else:
        loop(visualize=False)

    mpi_print(f'Writing output data to {json_file}')
    with open(json_file, 'w') as f:
        json.dump(output_data, f, indent=4)

    # Numpy array output for single parallel runs
    mpi_print(f'Writing solution to {solution_file}')
    if domain.comm.size == 1:
        sol = np.array(sol)
        np.save(solution_file, sol)


# The residual and Jacobian for diagnostics
#residual = fem.form(F)
#RD = fem.petsc.create_vector(residual)
#fem.petsc.assemble_vector(RD, residual)
#jacobian = fem.form(ufl.derivative(F, u))

#fem.petsc.apply_lifting(RD, [jacobian], [bcs])

#A = fem.petsc.create_matrix(jacobian)
#fem.petsc.assemble_matrix(A, jacobian)
#A.assemble()
#print(domain.comm.rank, A.getSize())
#m = A.convert('dense').getDenseArray()
