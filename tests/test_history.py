"""History (design §6 *Phase 4*): `timeline`, `lineage`, `find` and `get` over the git history of
the records of the root's planned results (§18, §19), `api.history`, and `astra history`.

The repository is §2's worked example with a few commits of records, records and bytes both
committed: built and committed (`first`); `data/input1.csv` changed, `output1` made again in
both universes and then `output2`, each with other bytes (`second`); then `output1` in `u2`
alone, in another environment (`third`).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.cli import main
from astra.hashing import digest_bytes
from astra.history import Version
from astra.records import Record
from tests.conftest import ENVIRONMENT, MINIMAL, build, git, repository
from tests.test_check import FROM_COMMIT, remake
from tests.test_plan import LIB
from tests.test_validate import WORKED_EXAMPLE

OTHER = "urn:example:environment2"


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


def head(top: Path) -> str:
    return git(top, "rev-parse", "HEAD").strip()


def commit(top: Path) -> str:
    """Commit everything in the working tree `top`, and give the commit."""
    return head(repository(top, {}))


def record(version: Version | None) -> Record:
    assert version is not None and isinstance(version.record, Record)
    return version.record


@dataclass(frozen=True)
class Recorded:
    top: Path
    built_from: str  # the commit the first records name, which holds none
    first: str
    second: str
    third: str


@pytest.fixture(scope="module")
def recorded(tmp_path_factory: pytest.TempPathFactory) -> Recorded:
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("ASTRA_CACHE_DIR", str(tmp_path_factory.mktemp("cache")))
        files = {"astra.yaml": WORKED_EXAMPLE, "data/input1.csv": "1\n"}
        top = repository(tmp_path_factory.mktemp("history"), files)
        built_from = head(top)
        build(top)
        first = commit(top)
        (top / "data" / "input1.csv").write_text("2\n")
        remake(top, "output1#u1", b"output1#u1 2\n")
        remake(top, "output1#u2", b"output1#u2 2\n")
        remake(top, "output2", b"output2 2\n")
        second = commit(top)
        remake(top, "output1#u2", b"output1#u2 3\n", OTHER)
        third = commit(top)
    return Recorded(top, built_from, first, second, third)


@pytest.fixture
def copied(recorded: Recorded, tmp_path: Path) -> Path:
    """A copy of the recorded repository of the test's own."""
    return Path(shutil.copytree(recorded.top, tmp_path / "top", symlinks=True))


# --- timeline ---


def test_timeline_gives_each_version_of_a_record_newest_first(recorded: Recorded) -> None:
    """Each commit that changed the record at the result's place (§18), and what the record
    says there (§19): `output1#u2` was made three times, `output1#u1` twice."""
    history = api.history(recorded.top)
    versions = history.timeline("output1#u2")
    assert [v.commit for v in versions] == [recorded.third, recorded.second, recorded.first]
    assert [record(v).digest for v in versions] == [
        digest_bytes(b"output1#u2 3\n"),
        digest_bytes(b"output1#u2 2\n"),
        digest_bytes(b"output1#u2\n"),
    ]
    assert [record(v).commit for v in versions] == [
        recorded.second,
        recorded.first,
        recorded.built_from,
    ]
    assert [record(v).environment for v in versions] == [OTHER, ENVIRONMENT, ENVIRONMENT]
    assert {v.place.record for v in versions} == {".astra/records/u2/output1.json"}
    versions = history.timeline("output1#u1")
    assert [v.commit for v in versions] == [recorded.second, recorded.first]


def test_timeline_says_where_a_version_isnt_a_valid_record(copied: Path) -> None:
    """A version is read as a checker reads a record (§20 `INVALID_RECORD`): one that breaks a
    parse rule gives its code, and a commit that removes the record gives none."""
    (copied / ".astra" / "records" / "output2.json").write_text("{")
    broken = commit(copied)
    (copied / ".astra" / "records" / "output2.json").unlink()
    removed = commit(copied)
    versions = api.history(copied).timeline("output2")
    assert [v.commit for v in versions[:2]] == [removed, broken]
    assert versions[0].record is None
    assert isinstance(versions[1].record, tuple)
    assert [d.code for d in versions[1].record] == ["INVALID_SYNTAX"]
    assert versions[1].record[0].location.commit == broken
    assert len(versions) == 4


def test_a_record_never_committed_has_no_version(tmp_path: Path) -> None:
    top = repository(tmp_path, {"astra.yaml": WORKED_EXAMPLE, "data/input1.csv": "1\n"})
    build(top)
    assert api.history(top).timeline("output2") == ()


def test_an_address_names_a_planned_results_place(recorded: Recorded) -> None:
    """A result's address (§18), not an output's: `output1` is built per universe, so its
    results' addresses name a universe."""
    history = api.history(recorded.top)
    for address in ("output1", "output3", "output1#u3", "decision1"):
        with pytest.raises(api.RequestError, match="no planned result"):
            history.timeline(address)


# --- lineage ---


def test_lineage_gives_the_versions_a_record_was_made_from(recorded: Recorded) -> None:
    """`output2`'s record at HEAD was made from the second versions of `output1#u1` and
    `output1#u2`, not `output1#u2`'s third, the latest; and each of those from
    `data/input1.csv`, a leaf, with its hash (§19 `inputs`)."""
    lineage = api.history(recorded.top).lineage("output2")
    assert lineage.version is not None and lineage.version.commit == recorded.second
    assert lineage.users == ()
    made_from = {link.entry: link for link in lineage.inputs}
    assert set(made_from) == {"output1#u1", "output1#u2"}
    for address, link in made_from.items():
        assert link.place is not None and link.place.address == address
        assert link.version is not None and link.version.commit == recorded.second
        assert link.digest == digest_bytes(f"{address} 2\n".encode())
        (below,) = link.inputs
        assert (below.entry, below.path, below.place) == ("input1", "data/input1.csv", None)
        assert below.digest == digest_bytes(b"2\n")


def test_lineage_where_no_version_has_the_hash_recorded(copied: Path) -> None:
    """A record that lists bytes no version of the result's record gives: the version is
    none, and nothing is below it."""
    remake(copied, "output1#u1", b"never committed\n")
    remake(copied, "output2", b"output2 3\n")
    git(copied, "add", ".astra/records/output2.json")
    git(copied, "commit", "--quiet", "--message", "output2")
    lineage = api.history(copied).lineage("output2")
    made_from = {link.entry: link for link in lineage.inputs}
    assert (made_from["output1#u1"].version, made_from["output1#u1"].inputs) == (None, ())
    assert record(made_from["output1#u2"].version).digest == digest_bytes(b"output1#u2 3\n")


def test_lineage_never_gives_a_version_committed_after_the_record_that_lists_it(
    recorded: Recorded, copied: Path
) -> None:
    """§19: a result made again that reproduces has the same `content_hash`. `output1#u2`, made
    again after `output2`'s record with its second version's bytes, gives the hash `output2`'s
    record lists, but `output2`'s recipe can't have read a later run: both ways, the version
    read is still the second."""
    remake(copied, "output1#u2", b"output1#u2 2\n")
    commit(copied)
    history = api.history(copied)
    made_from = {link.entry: link for link in history.lineage("output2").inputs}
    version = made_from["output1#u2"].version
    assert version is not None and version.commit == recorded.second
    (use,) = history.lineage("output1#u2", used_by=True).users
    assert use.read is not None and use.read.commit == recorded.second


def test_lineage_used_by_gives_the_records_that_list_a_result(recorded: Recorded) -> None:
    """The other way: `output2`'s record at HEAD lists `output1#u2`, with the hash of its
    second version."""
    history = api.history(recorded.top)
    lineage = history.lineage("output1#u2", used_by=True)
    assert lineage.version is not None and lineage.version.commit == recorded.third
    assert lineage.inputs == ()
    (use,) = lineage.users
    assert (use.version.place.address, use.version.commit) == ("output2", recorded.second)
    assert (use.entry, use.digest) == ("output1#u2", digest_bytes(b"output1#u2 2\n"))
    assert use.read is not None and use.read.commit == recorded.second
    assert history.lineage("output2", used_by=True).users == ()


# --- find ---


def test_find_by_hash_gives_the_versions_with_those_bytes(recorded: Recorded) -> None:
    history = api.history(recorded.top)
    (found,) = history.find(content_hash=digest_bytes(b"output1#u1\n").content_hash)
    assert (found.place.address, found.commit) == ("output1#u1", recorded.first)
    assert history.find(content_hash=digest_bytes(b"made by no one\n").content_hash) == ()


def test_find_by_environment_gives_every_version_with_that_iri(recorded: Recorded) -> None:
    history = api.history(recorded.top)
    found = history.find(environment=ENVIRONMENT)
    assert sorted((v.place.address, v.commit) for v in found) == sorted(
        [
            ("output1#u1", recorded.first),
            ("output1#u1", recorded.second),
            ("output1#u2", recorded.first),
            ("output1#u2", recorded.second),
            ("output2", recorded.first),
            ("output2", recorded.second),
        ]
    )
    (other,) = history.find(environment=OTHER)
    assert (other.place.address, other.commit) == ("output1#u2", recorded.third)


def test_find_takes_one_of_a_hash_and_an_environment(recorded: Recorded) -> None:
    history = api.history(recorded.top)
    with pytest.raises(ValueError, match="exactly one"):
        history.find(content_hash=digest_bytes(b"output1#u1\n").content_hash, environment=OTHER)
    with pytest.raises(ValueError, match="exactly one"):
        history.find()


# --- get ---


def test_get_gives_the_bytes_a_result_had_at_a_commit(recorded: Recorded) -> None:
    history = api.history(recorded.top)
    assert history.get("output1#u1", recorded.first) == b"output1#u1\n"
    assert history.get("output1#u2", recorded.second) == b"output1#u2 2\n"
    assert history.get("output1#u2", "HEAD") == b"output1#u2 3\n"


def test_get_where_the_commit_holds_no_record(recorded: Recorded) -> None:
    with pytest.raises(api.NotInHistoryError, match="holds no record at"):
        api.history(recorded.top).get("output1#u1", recorded.built_from)


def test_get_where_the_bytes_arent_in_git(copied: Path) -> None:
    """Results are often left out of git (§18: "A record at a commit can be read whether or not
    the commit holds the bytes")."""
    git(copied, "rm", "--quiet", "--cached", "results/output2.csv")
    git(copied, "commit", "--quiet", "--message", "results left out")
    left_out = head(copied)
    with pytest.raises(api.NotInHistoryError, match="aren't in git there"):
        api.history(copied).get("output2", left_out)


def test_get_where_the_bytes_arent_the_recorded_ones(copied: Path) -> None:
    (copied / "results" / "u1" / "output1.json").write_bytes(b"edited\n")
    edited = commit(copied)
    with pytest.raises(api.NotInHistoryError, match="aren't the ones its record there gives"):
        api.history(copied).get("output1#u1", edited)


def test_get_at_a_revision_that_names_no_commit(recorded: Recorded) -> None:
    with pytest.raises(api.RequestError, match="names no commit"):
        api.history(recorded.top).get("output1#u1", "nowhere")


# --- the stack it reads ---


def test_an_invalid_analysis_has_no_history(tmp_path: Path) -> None:
    """As O27 reads it for the plan, and O5 for `check`."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL.replace("type: metric", "type: plot")})
    with pytest.raises(api.InvalidAnalysisError):
        api.history(top)


def test_a_result_of_an_analysis_from_a_commit_has_its_one_version(tmp_path: Path) -> None:
    """§17: its records are read at the declared commit, which is its one version (O46), and
    `get` reads at a revision of the repository that holds it."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    build(top, top / "lib")
    holding = commit(top)
    repository(top, {"astra.yaml": FROM_COMMIT % holding})
    history = api.history(top)
    (version,) = history.timeline("out#v1")
    assert (version.commit, version.place.record) == (holding, "lib/.astra/records/v1/out.json")
    assert record(version).address == "out#v1"
    assert history.get("out#v1", holding) == b"out#v1\n"


# --- astra history ---


def test_astra_history_timeline(recorded: Recorded) -> None:
    result = astra("history", "timeline", "output1#u2", str(recorded.top))
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0] == "output1#u2  .astra/records/u2/output1.json"
    commits = [line.strip() for line in lines if line.startswith("  ") and line[2] != " "]
    assert commits == [recorded.third, recorded.second, recorded.first]
    third = digest_bytes(b"output1#u2 3\n").content_hash
    assert f"    bytes        {third}, 13 byte(s)" in lines
    assert f"    made at      {recorded.second}" in lines
    assert f"    environment  {OTHER}" in lines
    assert lines[-1] == "3 version(s)"


def test_astra_history_timeline_exits_1_with_no_version_and_2_for_no_result(
    tmp_path: Path, recorded: Recorded
) -> None:
    top = repository(tmp_path, {"astra.yaml": WORKED_EXAMPLE, "data/input1.csv": "1\n"})
    result = astra("history", "timeline", "output2", str(top))
    assert result.exit_code == 1
    assert "no record of `output2` is in HEAD's history" in result.stderr
    result = astra("history", "timeline", "output1", str(recorded.top))
    assert result.exit_code == 2
    assert "ADDR" in result.stderr


def test_astra_history_lineage(recorded: Recorded) -> None:
    result = astra("history", "lineage", "output2", str(recorded.top))
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[:2] == ["output2  .astra/records/output2.json", f"  {recorded.second}"]
    at = lines.index("made from")
    u1, input1 = (digest_bytes(data).content_hash for data in (b"output1#u1 2\n", b"2\n"))
    assert lines[at + 1 : at + 5] == [
        f"  output1#u1: {u1}, 13 byte(s)",
        f"    output1#u1's record of {recorded.second}, made at {recorded.first}",
        f"    input1: {input1}, 2 byte(s)",
        "      the file data/input1.csv",
    ]


def test_astra_history_lineage_used_by(recorded: Recorded) -> None:
    result = astra("history", "lineage", "output1#u2", str(recorded.top), "--used-by")
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    at = lines.index("used by")
    assert lines[at + 1].startswith(
        f"  output2, its record of {recorded.second}, through `output1#u2`: "
    )
    read = f"    output1#u2's record of {recorded.second}, made at {recorded.first}"
    assert lines[at + 2] == read


def test_astra_history_lineage_of_a_record_that_isnt_valid_exits_1(copied: Path) -> None:
    (copied / ".astra" / "records" / "output2.json").write_text("{")
    commit(copied)
    result = astra("history", "lineage", "output2", str(copied))
    assert result.exit_code == 1
    assert "error INVALID_SYNTAX" in result.stdout


def test_astra_history_find(recorded: Recorded) -> None:
    old = digest_bytes(b"output1#u1\n").content_hash
    result = astra("history", "find", str(recorded.top), "--hash", old)
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[:2] == ["output1#u1  .astra/records/u1/output1.json", f"  {recorded.first}"]
    assert lines[-1] == "1 version(s)"
    result = astra("history", "find", str(recorded.top), "--environment", ENVIRONMENT)
    assert (result.exit_code, result.stdout.splitlines()[-1]) == (0, "6 version(s)")
    result = astra("history", "find", str(recorded.top), "--environment", "urn:example:none")
    assert result.exit_code == 1
    assert "no version of a planned result's record has urn:example:none" in result.stderr
    assert astra("history", "find", str(recorded.top)).exit_code == 2
    both = ("--hash", old, "--environment", ENVIRONMENT)
    assert astra("history", "find", str(recorded.top), *both).exit_code == 2


def test_astra_history_get(recorded: Recorded) -> None:
    result = astra("history", "get", f"output1#u1@{recorded.first}", str(recorded.top))
    assert result.exit_code == 0, result.stderr
    assert result.stdout_bytes == b"output1#u1\n"
    result = astra("history", "get", f"output1#u1@{recorded.built_from}", str(recorded.top))
    assert (result.exit_code, result.stdout_bytes) == (1, b"")
    assert f"astra: {recorded.built_from} holds no record at" in result.stderr
    for asked in ("output1#u1@nowhere", "output1#u1", "nothing@HEAD", "@HEAD"):
        result = astra("history", "get", asked, str(recorded.top))
        assert result.exit_code == 2, asked
        assert "ADDR@REV" in result.stderr


def test_astra_history_of_an_invalid_analysis_shows_why_and_exits_1(tmp_path: Path) -> None:
    top = repository(tmp_path, {"astra.yaml": MINIMAL.replace("type: metric", "type: plot")})
    result = astra("history", "timeline", "result", str(top))
    assert result.exit_code == 1
    assert "astra.yaml: invalid, 1 error(s), 0 warning(s)" in result.stdout


def test_astra_history_exits_2_where_there_is_no_analysis(tmp_path: Path) -> None:
    result = astra("history", "timeline", "output2", str(tmp_path / "nothere"))
    assert result.exit_code == 2
