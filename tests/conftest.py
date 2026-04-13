"""Pytest configuration and fixtures."""

from pathlib import Path
from typing import Any

import pytest


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
def baseline_universe_path() -> Path:
    """Return path to baseline universe."""
    return VALID_DIR / "universe_baseline.yaml"


@pytest.fixture
def svm_universe_path() -> Path:
    """Return path to SVM universe."""
    return VALID_DIR / "universe_svm.yaml"


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
                "default": "a",
                "options": {"a": {"label": "A"}, "b": {"label": "B"}},
            }
        },
    }


@pytest.fixture
def baseline_universe_data() -> dict[str, Any]:
    """Return baseline universe data as dict."""
    return {
        "id": "baseline",
        "description": "Test baseline",
        "decisions": {"method": "a"},
    }
