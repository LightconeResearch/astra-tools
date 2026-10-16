"""Pytest configuration and fixtures."""

import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from astra.helpers import load_yaml


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --run-network option to pytest."""
    parser.addoption(
        "--run-network",
        action="store_true",
        default=False,
        help="Run tests that require network access",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip network tests unless --run-network is passed."""
    if not config.getoption("--run-network"):
        skip_network = pytest.mark.skip(reason="use --run-network to run network tests")
        for item in items:
            if "network" in item.keywords:
                item.add_marker(skip_network)


def pytest_configure(config: pytest.Config) -> None:
    """Run the tests as if in a terminal 1000 columns wide.

    The CLI tests check phrases in what the CLI prints. Rich and
    ``astra spec`` otherwise size that output from the terminal pytest runs
    in and wrap long lines - so a phrase could be split and a test pass in
    one terminal and fail in another. Both take ``COLUMNS`` over the real
    terminal. It's set here because Rich fixes a console's width from
    ``COLUMNS`` when the console is created - and this runs before any test
    module imports ``astra.cli``.
    """
    os.environ["COLUMNS"] = "1000"


# Fixture directories
FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_DIR = FIXTURES_DIR / "valid"
INVALID_DIR = FIXTURES_DIR / "invalid"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def valid_dir() -> Path:
    """Return the valid fixtures directory."""
    return VALID_DIR


@pytest.fixture
def invalid_dir() -> Path:
    """Return the invalid fixtures directory."""
    return INVALID_DIR


@pytest.fixture
def minimal_analysis_path() -> Path:
    """Return path to minimal valid analysis."""
    return VALID_DIR / "minimal.yaml"


@pytest.fixture
def full_analysis_path() -> Path:
    """Return path to full valid analysis."""
    return VALID_DIR / "full.yaml"


@pytest.fixture
def with_universe_entry() -> Callable[[Path, Path], dict[str, Any]]:
    """Return a function that declares one universe entry in an analysis.

    It loads the analysis at the first path and makes the entry at the second
    its only universe - so the entry is validated through the analysis's
    ``universes`` list, as it would be in an ``astra.yaml``.
    """

    def build(analysis: Path, entry: Path) -> dict[str, Any]:
        data = load_yaml(analysis)
        data["universes"] = [load_yaml(entry)]
        return data

    return build


@pytest.fixture
def minimal_analysis_data() -> dict[str, Any]:
    """Return minimal analysis data as dict."""
    return {
        "version": "1.0",
        "name": "Test Analysis",
        "inputs": [{"id": "test_data", "type": "data"}],
        "outputs": [{"id": "result", "type": "metric"}],
        "decisions": {
            "method": {
                "label": "Method",
                "options": {"a": {"label": "A"}, "b": {"label": "B"}},
            }
        },
    }
