"""Fixtures for the aitw-darcy tests."""
import json

import pytest


@pytest.fixture(scope='session')
def small_input_path():
    """Path to a small input file for testing."""
    return 'examples/small.json'

@pytest.fixture(scope='session')
def small_input_data(small_input_path):
    """Load the small input data from the JSON file."""
    with open(small_input_path, 'r') as f:
        return json.load(f)
