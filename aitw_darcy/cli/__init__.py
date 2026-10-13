import json

import click as original_click
import rich_click as click
from rich.traceback import install

from aitw_darcy.data import DarcyParams

install(
    suppress=[original_click, click],
)

@click.group('aitw-darcy')
def cmd_root():
    """ Command line interface for AITW Darcy simulations """
    pass

@cmd_root.command()
@click.pass_context
# @click.argument('json_file', required=True, type=click.Path(exists=True))
# @click.option('--output_dir', type=click.Path(), help='Output directory')
@click.option(
    '--visualize/--no-visualize', default=False,
    help='Enable storing VTX files for visualization. Requires dolfinx and ParaView build with ADIOS2.'
)
@DarcyParams.to_click_options
def infiltration(
        ctx,
        config_file: str,
        visualize: bool,
        # output_dir: str = '.',
    ):
    """ Run the infiltration simulation command line interface """
    from aitw_darcy.data import DarcyParams
    from aitw_darcy.infiltration import run_simulation

    data = {}
    if config_file:
        with open(config_file, 'r') as f:
            data = json.load(f)

    overrides = ctx.obj.get('override_params', {})
    if overrides:
        for dct in data:
            dct.update(overrides)

    params = DarcyParams.from_dict(data)
    run_simulation(params, visualize=visualize)
