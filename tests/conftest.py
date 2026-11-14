"""Shared by the tests: the cache kept apart, git, and results built as a runner builds them.
astra-spec's conformance suite and examples are in `tests/spec.py`."""

from __future__ import annotations

import importlib.metadata
import subprocess
import tempfile
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest

from astra import api
from astra.plan import Result
from astra.records import Runner, new_record, write_record

MINIMAL = """\
spec_version: "0.1.0"
outputs:
  result:
    type: metric
    format: json
    recipe:
      command: python make.py '{output}'
"""
"""A minimal `astra.yaml` that makes something: a `spec_version` and one output."""


def pytest_report_header(config: pytest.Config) -> str:
    return f"astra-spec {importlib.metadata.version('astra-spec')}"


@pytest.fixture(autouse=True, scope="session")
def session_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A cache for fixtures wider than a test, such as a module's built repository, which are set
    up before `cache` and would otherwise use the user's own."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("ASTRA_CACHE_DIR", str(tmp_path_factory.mktemp("session-cache")))
        yield


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


RUNNER = Runner("astra-tools-tests", "1")
ENVIRONMENT = "urn:example:environment1"


def build(
    top: Path,
    folder: Path | None = None,
    *,
    commit: str | None = None,
    made: Callable[[Result], bytes] = lambda result: f"{result.places[0].address}\n".encode(),
) -> tuple[Result, ...]:
    """Build the analysis in `folder`, `top` by default, in the working tree whose top is `top`,
    as a runner would but without running a recipe: each planned result it doesn't read through
    a record, in the plan's order, gets the bytes `made` gives it at each of its default places,
    and a record from `records.new_record` at each of its places, naming `commit` (HEAD by
    default) as the commit its recipe ran from. What an entry reads at a commit is got through
    `api.history`, outside the checkout. Nothing is committed. Gives the plan's results."""
    commit = commit or git(top, "rev-parse", "HEAD").strip()
    results = api.plan(folder or top).results
    kept = Path(tempfile.mkdtemp(prefix="got-"))
    for result in results:
        if result.read_only:
            continue
        for place in result.places:
            (top / place.bytes).parent.mkdir(parents=True, exist_ok=True)
            (top / place.bytes).write_bytes(made(result))
        got = {}
        for read in result.inputs:
            if read.commit is not None and read.place is not None:
                data = api.history(folder or top).get(read.place.address, read.commit)
                path = kept / str(len(got))
                path.write_bytes(data)
                got[read.entry] = str(path)
        records = new_record(
            result, checkout=top, commit=commit, environment=ENVIRONMENT, runner=RUNNER, got=got
        )
        for place, record in zip(result.places, records, strict=True):
            write_record(top / place.record, record)
    return results
