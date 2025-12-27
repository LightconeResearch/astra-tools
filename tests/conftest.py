"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest

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
def minimal_analysis_data() -> dict:
    """Return minimal analysis data as dict."""
    return {
        "version": "1.0",
        "analysis": {
            "name": "Test Analysis",
            "problem": "Test problem statement",
            "inputs": [{"id": "test_data", "type": "data"}],
            "outputs": [{"id": "result", "type": "metric", "dtype": "float"}],
        },
        "decisions": {
            "method": {
                "label": "Method",
                "type": "method",
                "default": "a",
                "options": {"a": {"label": "A"}, "b": {"label": "B"}},
            }
        },
    }


@pytest.fixture
def baseline_universe_data() -> dict:
    """Return baseline universe data as dict."""
    return {
        "id": "baseline",
        "description": "Test baseline",
        "decisions": {"method": "a"},
    }
