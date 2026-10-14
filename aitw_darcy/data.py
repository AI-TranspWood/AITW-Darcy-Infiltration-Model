import json
from collections.abc import Callable
from copy import copy
from dataclasses import dataclass, field, fields
from typing import ClassVar, Self

import rich_click as click
from click.core import ParameterSource


class DelimitedList(click.ParamType):
    """A custom Click parameter type that parses a comma-separated list of values."""

    name = 'list'

    def __init__(self, delimiter=',', subtype=str, exact_length=None):
        super().__init__()
        self.delimiter = delimiter
        self.subtype = subtype
        self.exact_length = exact_length

    def convert(self, value, param, ctx):
        if isinstance(value, list):
            res = [self.subtype(item) for item in value]
        else:
            try:
                items = value.split(self.delimiter)
                res = [self.subtype(item.strip()) for item in items]
            except Exception as e:
                self.fail(f'Could not parse list: {e}', param, ctx)

        if self.exact_length is not None and len(res) != self.exact_length:
            self.fail(f'Expected exactly {self.exact_length} items, got {len(res)}', param, ctx)

        return res


@dataclass
class JsonParams:
    params_map: ClassVar[dict[str, str]] = {}
    post_set: ClassVar[list[str]] = []

    def _to_json(self, data: dict) -> dict:
        """Convert the parameters to a JSON serializable dictionary"""
        return data

    def to_json(self, json_file: str):
        """Save the parameters to a JSON file"""
        data = self.to_dict()
        data = self._to_json(data)

        with open(json_file, 'w') as f:
            json.dump(data, f, indent=4)

    def to_dict(self) -> dict:
        """Convert the parameters to a dictionary"""
        data = {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
        return data

    @classmethod
    def from_json(cls, json_file: str) -> list[Self]:
        """Create an instance from a JSON file"""
        with open(json_file, 'r') as f:
            data = json.load(f)
        res = []
        if isinstance(data, dict):
            res = [cls.from_dict(data)]
        elif isinstance(data, list):
            res = [cls.from_dict(item) for item in data]
        else:
            raise ValueError('Invalid data format in JSON file')
        return res

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create an instance from a JSON file"""
        post = {}
        data = {cls.params_map.get(k, k): v for k, v in data.items()}
        for k in cls.post_set:
            if k in data:
                post[k] = data.pop(k)
        res = cls(**data)
        for k, v in post.items():
            setattr(res, k, v)
        return res

    @classmethod
    def to_click_options(cls, func: Callable) -> Callable:
        """Decorator to add click options for the parameters to a click command"""
        name_map = {}

        OVERRIDE_GROUP = 'Override Input Parameters'

        groups = {'Options'}

        def callback(ctx: click.Context, param: click.Parameter, value):
            ctx.ensure_object(dict)
            source = ctx.get_parameter_source(param.name)
            if source == ParameterSource.DEFAULT:
                return
            name = name_map.get(param.name, param.name)
            overrides = ctx.obj.setdefault('override_params', {})
            overrides[name] = value

        for fld in fields(cls)[::-1]:
            extra_help = ''
            metadata = getattr(fld, 'metadata', {})
            if not fld.init:
                continue
            if fld.name.startswith('_'):
                continue
            if fld.type not in (
                    int, float, str, bool,
                    list[str], tuple[int, int, int]
                ):
                continue

            typ = fld.type
            if typ in (int, float):
                min_val = metadata.get('min', None)
                max_val = metadata.get('max', None)
                if min_val is not None or max_val is not None:
                    cls_typ = click.FloatRange if typ == float else click.IntRange
                    typ = cls_typ(min=min_val, max=max_val)
            elif typ == str:
                if metadata.get('file', False):
                    typ = click.Path(exists=True, dir_okay=False, readable=True, resolve_path=True)
                elif metadata.get('dir', False):
                    typ = click.Path(exists=True, file_okay=False, readable=True, resolve_path=True)
            elif typ == list[str]:
                typ = DelimitedList()
                extra_help = ' (comma-separated list)'
            elif typ == tuple[int, int, int]:
                typ = DelimitedList(subtype=int, exact_length=3)
                extra_help = ' (comma-separated list of 3 integers)'

            expose = metadata.get('expose_value', False)
            # prefix = '--param-' if not expose else '--'
            prefix = '--'

            decl = f'{prefix}{fld.name}'
            if fld.type == bool:
                decl = f'{prefix}{fld.name}/{prefix}no-{fld.name}'
            name_map[f'param_{fld.name}'] = fld.name

            required = metadata.get('required', False)

            group = metadata.get('group', OVERRIDE_GROUP)
            groups.add(group)

            help_str = metadata.get('help', None)
            if help_str is not None and extra_help:
                help_str += extra_help

            kwargs = {
                'type': typ,
                'is_flag': fld.type == bool,
                'required': required,
                'expose_value': expose,
                'callback': callback,
                'help': help_str,
                'panel': group,
                'show_default': True,
            }

            if 'flag_value' in metadata:
                kwargs['flag_value'] = metadata['flag_value']

            func = click.option(decl, **kwargs)(func)

        func = click.option(
            '--config-file', type=click.Path(exists=True), help='Path to file with parameters'
        )(func)

        for group in sorted(groups, key=lambda x: (x != 'Options', x == 'Advanced', x))[::-1]:
            func = click.option_panel(group)(func)

        return func

@dataclass(kw_only=True)
class DarcyParams(JsonParams):
    # Label for the simulation
    label: str = field(
        default='3d_plate',
        metadata={'help': 'Label for the simulation used in the output files name', 'group': 'IO'}
    )
    output_dir: str = field(
        default='output',
        metadata={'help': 'Output directory', 'group': 'IO', 'dir': True}
    )

    # Mesh dimensions (m)
    xmin: float = field(
        default=0,
        metadata={'help': 'Minimum x-coordinate of the mesh (m)', 'group': 'Geometry'}
    )
    xmax: float = field(
        default=5e-2,
        metadata={'help': 'Maximum x-coordinate of the mesh (m)', 'group': 'Geometry'}
    )
    ymin: float = field(
        default=0,
        metadata={'help': 'Minimum y-coordinate of the mesh (m)', 'group': 'Geometry'}
    )
    ymax: float = field(
        # default=5e-2,
        metadata={'help': 'Maximum y-coordinate of the mesh (m)', 'group': 'Geometry'}
    )
    zmin: float = field(
        default=0,
        metadata={'help': 'Minimum z-coordinate of the mesh (m)', 'group': 'Geometry'}
    )
    zmax: float = field(
        default=1e-3,
        metadata={'help': 'Maximum z-coordinate of the mesh (m)', 'group': 'Geometry'}
    )
    # Number of nodes
    nx: int = field(
        default=40,
        metadata={'help': 'Number of nodes in the x-direction', 'group': 'Mesh'}
    )
    ny: int = field(
        default=160,
        metadata={'help': 'Number of nodes in the y-direction', 'group': 'Mesh'}
    )
    nz: int = field(
        default=40,
        metadata={'help': 'Number of nodes in the z-direction', 'group': 'Mesh'}
    )

    # Timestepping
    # Initial time step length (s)
    delta_t0: float = field(
        default=1e-1,
        metadata={'help': 'Initial time step length (s)', 'group': 'Time Stepping', 'min': 1e-10}
    )
    delta_tmin: float = field(
        default=1e-2,
        metadata={
            'help': (
                'Minimum time step length (s). '
                'Hard constraint that will stop the simulation if the dynamic time step decreases below this value. '
            ),
            'group': 'Advanced', 'min': 1e-10
        }
    )
    delta_tmax: float = field(
        default=10,
        metadata={
            'help': (
                'Maximum time step length (s). '
                'Soft constraint that will stop the dynamic time step from increasing more than this value. '
            ),
            'group': 'Advanced', 'min': 1e-10
        }
    )
    # Simulation time (s)
    t_end: float = field(
        default=120,
        metadata={
            'help': (
                'Maximum simulation time (s). '
                'The simulation will stop when this time is reached even if saturation has not been achieved.'
            ),
            'group': 'Time Stepping', 'min': 1e-10
        }
    )

    # Porosity
    porosity: float = field(
        default=0.6,
        metadata={'help': 'Porosity of the medium', 'group': 'Material Properties', 'min': 0, 'max': 1}
    )

    # Surface tension (N/m)
    surface_tension: float = field(
        default=30e-3,
        metadata={'help': 'Surface tension (N/m)', 'group': 'Material Properties', 'min': 0}
    )

    # Contact angle
    contact_angle: float = field(
        default=10,
        metadata={'help': 'Contact angle (degrees)', 'group': 'Material Properties', 'min': 0, 'max': 180}
    )

    # Mean pore radius (m)
    mean_pore_radius: float = field(
        default=20e-6,
        metadata={'help': 'Mean pore radius (m)', 'group': 'Material Properties', 'min': 0}
    )

    # Relative standard deviation of pore radius
    rstd: float = field(
        default=1/5,
        metadata={'help': 'Relative standard deviation of pore radius', 'group': 'Material Properties', 'min': 0}
    )

    # Pore radius cutoff
    r_cutoff: float = field(
        default=2e-6,
        metadata={'help': 'Pore radius cutoff (m)', 'group': 'Material Properties', 'min': 0}
    )

    # Permeability
    k_long: float = 1e-12
    k_long: float = field(
        default=1e-12,
        metadata={'help': 'Longitudinal permeability (m^2)', 'group': 'Material Properties', 'min': 0}
    )
    k_trans: float = field(
        default=1e-16,
        metadata={'help': 'Transverse permeability (m^2)', 'group': 'Material Properties', 'min': 0}
    )

    # Fluid viscosity (Pa s)
    viscosity: float = field(
        default=1e-3,
        metadata={'help': 'Fluid viscosity (Pa s)', 'group': 'Material Properties', 'min': 0}
    )

    # External pressure
    u_ext: float = field(
        default=-1e-6,
        metadata={'help': 'External pressure (Pa)', 'group': 'Material Properties'}
    )

    def __post_init__(self):
        if self.ymax is None and self.xmax is None:
            raise ValueError('At least one of xmax or ymax must be specified')
        if self.ymax is None:
            self.ymax = self.xmax
        elif self.xmax is None:
            self.xmax = self.ymax
