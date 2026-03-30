"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest

from astra.crate import ASTRACrate


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


# Example directories
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


@pytest.fixture
def iris_crate() -> ASTRACrate:
    """Load the iris example crate."""
    return ASTRACrate.load(EXAMPLES_DIR / "iris")


@pytest.fixture
def iris_pipeline_crate() -> ASTRACrate:
    """Load the iris_pipeline example crate."""
    return ASTRACrate.load(EXAMPLES_DIR / "iris_pipeline")
