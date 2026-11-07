"""Shared by the tests: the cache kept apart, astra-spec's fixtures and examples, and git."""

from __future__ import annotations

import importlib.metadata
import subprocess
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

import pytest

SPEC = Path(str(files("astra.schema") / "generated")).parents[3]
"""The astra-spec the installed `astra.schema` comes from: its fixtures (`tests/data/`) and its
`examples/` are the oracle (design §1, principle 6)."""

MINIMAL = """\
spec_version: "0.1.0"
outputs:
  result:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
"""
"""The smallest valid `astra.yaml`: a `spec_version` and one output (§5)."""


def pytest_report_header(config: pytest.Config) -> str:
    return f"astra-spec {importlib.metadata.version('astra-spec')} at {SPEC}"


@pytest.fixture(autouse=True)
def cache(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test's cache is a folder of its own, outside every repository."""
    monkeypatch.setenv("ASTRA_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))


@pytest.fixture
def outside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A folder in no git repository: git looks for none above it."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    folder = tmp_path / "analysis"
    folder.mkdir()
    return folder


def git_init(folder: Path) -> Path:
    """A new git repository whose working tree is `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(folder)], check=True)
    return folder


GIT = (
    "git",
    "-c",
    "user.name=astra-tools tests",
    "-c",
    "user.email=tests@astra.invalid",
    "-c",
    "commit.gpgsign=false",
    "-c",
    "protocol.file.allow=always",
)
"""git, with an identity of its own, never signing, and free to add a local submodule."""


def git(top: Path, *args: str) -> str:
    """Run git in the working tree `top`, and give what it prints."""
    process = subprocess.run([*GIT, "-C", str(top), *args], capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    return process.stdout


def repository(top: Path, files: Mapping[str, str | bytes]) -> Path:
    """The git repository at `top`, made if need be, with `files` (each path from `top`, and
    its text or bytes) written and committed: a stack of analyses, say, as
    `{"astra.yaml": ROOT, "sub/astra.yaml": SUB, "sub/data/x.csv": "1,2\n"}`. Gives `top`."""
    if not (top / ".git").exists():
        git_init(top)
    for path, content in files.items():
        (top / path).parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else content
        (top / path).write_bytes(data)
    git(top, "add", "--all")
    git(top, "commit", "--quiet", "--no-verify", "--allow-empty", "--message", "stack")
    return top


def analysis(folder: Path, text: str = MINIMAL) -> Path:
    """`folder`, made if need be, with `text` as its `astra.yaml`."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "astra.yaml").write_text(text, encoding="utf-8")
    return folder
