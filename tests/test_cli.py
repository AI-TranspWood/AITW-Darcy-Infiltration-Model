"""Test the CLI of the aitw-darcy package."""
import os

from click.testing import CliRunner


def test_cli_infiltration(small_input_path, tmp_path):
    """Test the CLI command for infiltration simulation."""
    from aitw_darcy.cli import cmd_root
    label = 'small'
    runner = CliRunner()
    result = runner.invoke(
        cmd_root,
        [
           'infiltration',
            '--config-file', small_input_path,
            '--output_dir', str(tmp_path),
        ]
    )
    assert result.exit_code == 0
    assert os.path.exists(tmp_path / f'{label}_solution.npy')
    assert not os.path.exists(tmp_path / f'{label}_output.bp')
    assert os.path.exists(tmp_path / f'{label}.log')
    assert os.path.exists(tmp_path / f'{label}.json')
