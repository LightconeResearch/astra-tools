"""astra-spec's conformance suite (`conformance/analyses/`): each analysis case, built and
compared as astra-spec's `conformance/README.md` says, gives the verdict its `expected.json`
gives. Its documents are `test_fixtures.py`'s."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from astra import api
from tests.conftest import SPEC

ANALYSES = SPEC / "conformance" / "analyses"
CASES = sorted(ANALYSES.glob("[0-9]*"))


def environment(place: Path) -> dict[str, str]:
    """What a case's git commands and `setup.sh` run with, `place` being the working folder's
    parent: `PATH` and the README's variables only."""
    (place / "home").mkdir()
    (place / "remotes").mkdir()
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(place / "home"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "ASTRA conformance",
        "GIT_COMMITTER_NAME": "ASTRA conformance",
        "GIT_AUTHOR_EMAIL": "conformance@astra.invalid",
        "GIT_COMMITTER_EMAIL": "conformance@astra.invalid",
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00Z",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00Z",
        "GIT_CEILING_DIRECTORIES": str(place),
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "protocol.file.allow",
        "GIT_CONFIG_VALUE_0": "always",
        "ASTRA_CASE_REMOTES": str(place / "remotes"),
    }


def build(case: Path, place: Path) -> Path:
    """The working folder of `case`, built in the empty folder `place`: its files copied in,
    then its `setup.sh` run there, or else one commit of every file."""
    work = place / "work"
    shutil.copytree(case / "files", work, symlinks=True)
    setup = case / "setup.sh"
    commands = (
        [["sh", "-eu", str(setup)]]
        if setup.is_file()
        else [["git", "init"], ["git", "add", "--all"], ["git", "commit", "--message", "files"]]
    )
    env = environment(place)
    for command in commands:
        process = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True)
        assert process.returncode == 0, process.stderr
    return work


def matches(entry: dict[str, str], found: tuple[str, str, str]) -> bool:
    """Whether a diagnostic, as its code, file and pointer, is one that `entry` of `must_report`
    asks for: its code, and its file and pointer where the entry gives them. A file read at a
    commit is named as in the working tree, from the top of its repository."""
    keys = ("code", "file", "pointer")
    return all(entry.get(key, value) == value for key, value in zip(keys, found, strict=True))


def test_the_cases_are_found() -> None:
    assert len(CASES) >= 3


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.relative_to(ANALYSES).as_posix())
def test_a_case_gives_its_verdict(
    case: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validated in a cache of its own (`conftest.cache`), with git looking for no repository
    above the working folder."""
    expected = json.loads((case / "expected.json").read_text("utf-8"))
    work = build(case, tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    report = api.validate(work / expected.get("root", "."))
    found = [(d.code, d.location.file, d.location.pointer) for d in report.diagnostics]
    assert report.valid == expected["valid"], found
    unmatched = [
        entry
        for entry in expected.get("must_report", [])
        if not any(matches(entry, diagnostic) for diagnostic in found)
    ]
    assert unmatched == [], found
    assert [d for d in found if d[0] in expected.get("must_not_report", [])] == []
