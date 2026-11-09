"""The checker (§20, design §4.7): each planned result's record and bytes statuses at each of
its places, by the check rules, and the evidence's; `api.check`, its shape
`astra-check-report/1`, and `astra check`.

The stacks are §2's worked example, built as a runner builds it (`conftest.build`); §18's
`inner`, reached through `inner` and `stage.inner`; §17's analysis from a commit, read through
its records; and astra-spec's record fixtures, at a planned result's place. At the end, phase 3's
*Done when* (design §6): every check code of rules.json has a case that breaks it, and §20's
table of edits to the worked example, its records committed, gives the effects it lists.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from astra import api
from astra.check import CODES, CheckReport
from astra.cli import main
from astra.diagnostics import Catalogue
from astra.records import new_record, write_record
from tests.conftest import DOCUMENTS, ENVIRONMENT, MINIMAL, RUNNER, build, git, repository
from tests.test_plan import FROM_COMMIT as DRIVING
from tests.test_plan import INNER, LIB, PAIR, STAGE
from tests.test_planned import ROOT, SUBANALYSIS
from tests.test_validate import WORKED_EXAMPLE


def astra(*args: str) -> Result:
    return CliRunner().invoke(main, list(args))


def statuses(report: CheckReport) -> dict[str, tuple[str, str | None]]:
    """Each place's address, and its record and bytes statuses."""
    return {
        status.place.address: (status.record_status, status.bytes_status)
        for checked in report.results
        for status in checked.statuses
    }


def reasons(report: CheckReport, address: str) -> list[str]:
    """The codes of the rules broken at the place of `address`."""
    return [
        reason.code
        for checked in report.results
        for status in checked.statuses
        if status.place.address == address
        for reason in status.reasons
    ]


def messages(report: CheckReport, address: str) -> list[str]:
    return [
        reason.message
        for checked in report.results
        for status in checked.statuses
        if status.place.address == address
        for reason in status.reasons
    ]


def rewrite(path: Path, change: Callable[[dict[str, Any]], object]) -> None:
    """Change the JSON value of the record at `path` in place."""
    value = json.loads(path.read_text("utf-8"))
    change(value)
    path.write_text(json.dumps(value), "utf-8")


def remake(top: Path, address: str, data: bytes, environment: str = ENVIRONMENT) -> None:
    """Make the result whose first place is `address` again in the working tree `top`, as a
    runner would from HEAD: `data` its bytes, and its record from `new_record`, run in
    `environment` (§19)."""
    (result,) = [r for r in api.plan(top).results if r.places[0].address == address]
    (top / result.places[0].bytes).write_bytes(data)
    commit = git(top, "rev-parse", "HEAD").strip()
    (record,) = new_record(
        result, checkout=top, commit=commit, environment=environment, runner=RUNNER
    )
    write_record(top / result.places[0].record, record)


UNCHANGED = {
    "output1#u1": ("unchanged", "present"),
    "output1#u2": ("unchanged", "present"),
    "output2": ("unchanged", "present"),
}


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """§2's worked example, committed with its input, and built from that commit."""
    files = {"astra.yaml": WORKED_EXAMPLE, "data/input1.csv": "1\n"}
    top = repository(tmp_path_factory.mktemp("worked"), files)
    build(top)
    return top


@pytest.fixture
def worked(built: Path, tmp_path: Path) -> Path:
    """A copy of `built` of the test's own."""
    return Path(shutil.copytree(built, tmp_path / "worked", symlinks=True))


# --- the worked example: every rule kept, and MISSING_RECORD ---


def test_a_built_analysis_is_unchanged_and_present(worked: Path) -> None:
    """§20 *The rules*: a result for which every rule holds is `unchanged` and `present`, and so
    is the evidence that cites it (§2 *Checking*). A checker reads records only through planned
    results, so a record of nothing planned isn't read."""
    (worked / ".astra" / "records" / "output3.json").write_text("not a record")
    report = api.check(worked)
    assert statuses(report) == UNCHANGED
    assert all(status.reasons == () for c in report.results for status in c.statuses)
    assert [(e.artifact, e.cites, e.record_status) for e in report.evidence] == [
        ("output2", ("output2",), "unchanged")
    ]
    assert (report.ok, report.at, report.root) == (True, "worktree", "astra.yaml")


def test_a_result_with_no_record_is_missing(tmp_path: Path) -> None:
    """MISSING_RECORD: a result built nowhere is `missing`, with no recorded bytes (`absent`), and
    neither INVALID_RECORD, MISPLACED_RECORD nor MISSING_RECORD_INPUTS is checked for it, nor
    ABSENT_RESULT, for a result that is `missing` (design §4.13 case 9)."""
    files = {"astra.yaml": WORKED_EXAMPLE, "data/input1.csv": "1\n"}
    report = api.check(repository(tmp_path, files))
    assert statuses(report) == {address: ("missing", "absent") for address in UNCHANGED}
    assert reasons(report, "output2") == ["MISSING_RECORD"]
    assert not report.ok


def test_a_record_missing_at_one_place_makes_that_result_missing(worked: Path) -> None:
    """MISSING_RECORD, at `.astra/records/{universe}/{name}.json`; and a result made from it has
    a valid record, but not what it was made from, so it is stale (§20)."""
    (worked / ".astra" / "records" / "u2" / "output1.json").unlink()
    report = api.check(worked)
    assert statuses(report)["output1#u2"] == ("missing", "absent")
    assert reasons(report, "output1#u2") == ["MISSING_RECORD"]
    assert statuses(report)["output2"] == ("stale", "present")
    assert messages(report, "output2") == ["`output1#u2`, which it reads, has no valid record"]


# --- INVALID_RECORD, and astra-spec's record fixtures ---


INVALID = sorted((DOCUMENTS / "invalid").glob("ProvenanceRecord-*.json"))
VALID = sorted((DOCUMENTS / "valid").glob("ProvenanceRecord-*.json"))


def header(fixture: Path) -> str:
    """The code a fixture's `.header` sidecar names, as `# rule: CODE`."""
    text = fixture.with_suffix(".header").read_text("utf-8")
    return next(line.split(":", 1)[1].strip() for line in text.splitlines() if "rule:" in line)


@pytest.mark.parametrize("fixture", INVALID, ids=lambda path: path.stem)
def test_an_invalid_record_fixture_leaves_its_result_missing(worked: Path, fixture: Path) -> None:
    """§4, §20 *The rules*: a record that breaks a parse or schema rule leaves its result
    `missing`, under INVALID_RECORD with the code it breaks as the reason, and isn't checked by
    MISPLACED_RECORD or MISSING_RECORD_INPUTS (design §4.13 case 9)."""
    shutil.copy(fixture, worked / ".astra" / "records" / "output2.json")
    report = api.check(worked)
    assert statuses(report)["output2"] == ("missing", "absent")
    (found,) = [s for c in report.results for s in c.statuses if s.place.address == "output2"]
    broken = [reason for reason in found.reasons if reason.code != "ABSENT_RESULT"]
    assert {reason.code for reason in broken} == {"INVALID_RECORD"}
    assert {reason.breaks for reason in broken} == {header(fixture)}
    assert all(r.location.file == ".astra/records/output2.json" for r in broken)


@pytest.mark.parametrize("fixture", VALID, ids=lambda path: path.stem)
def test_a_valid_record_fixture_breaks_no_parse_or_schema_rule(worked: Path, fixture: Path) -> None:
    """Read at a planned result's place, it is judged by the other rules: its address and commit
    are another result's, so the result is still missing, but not by INVALID_RECORD."""
    shutil.copy(fixture, worked / ".astra" / "records" / "output2.json")
    found = reasons(api.check(worked), "output2")
    assert "INVALID_RECORD" not in found
    assert "MISPLACED_RECORD" in found


def test_a_record_of_a_later_minor_version_is_read_by_the_open_schema(worked: Path) -> None:
    """§19, Annex D: a field it doesn't know is ignored in a record of a greater minor version,
    and is UNKNOWN_FIELD in one of 0.1; a record below 0.1 has no schema (§4)."""
    path = worked / ".astra" / "records" / "output2.json"
    rewrite(path, lambda value: value.update(spec_version="0.2.0", later=1))
    assert statuses(api.check(worked))["output2"] == ("unchanged", "present")
    rewrite(path, lambda value: value.update(spec_version="0.1.3"))
    report = api.check(worked)
    (found,) = [s for c in report.results for s in c.statuses if s.place.address == "output2"]
    assert [(r.code, r.breaks, r.location.key) for r in found.reasons][0] == (
        "INVALID_RECORD",
        "UNKNOWN_FIELD",
        "later",
    )
    rewrite(path, lambda value: value.update(spec_version="0.0.9"))
    report = api.check(worked)
    (found,) = [s for c in report.results for s in c.statuses if s.place.address == "output2"]
    assert [(r.code, r.breaks, r.location.pointer) for r in found.reasons][0] == (
        "INVALID_RECORD",
        None,
        "/spec_version",
    )


# --- MISPLACED_RECORD and MISSING_RECORD_INPUTS ---


def test_a_record_of_another_result_is_misplaced(worked: Path) -> None:
    """MISPLACED_RECORD: a record is the record only of the result its `address` names (§18)."""
    records = worked / ".astra" / "records"
    shutil.copy(records / "u1" / "output1.json", records / "u2" / "output1.json")
    report = api.check(worked)
    assert statuses(report)["output1#u2"] == ("missing", "absent")
    assert reasons(report, "output1#u2") == ["MISPLACED_RECORD"]


def test_a_record_holds_one_item_for_each_entry_its_output_lists(worked: Path) -> None:
    """MISSING_RECORD_INPUTS: exactly one item for each entry its output lists at the record's
    commit, matched by `entry`, and no other item (§19)."""
    path = worked / ".astra" / "records" / "output2.json"
    original = json.loads(path.read_text("utf-8"))
    items = original["generated_by"]["inputs"]

    def check(new: list[dict[str, Any]]) -> tuple[str, list[str]]:
        rewrite(path, lambda value: value["generated_by"].update(inputs=new))
        report = api.check(worked)
        return statuses(report)["output2"][0], reasons(report, "output2")

    assert check(items[::-1]) == ("unchanged", [])  # their order carries no meaning
    assert check(items[:1]) == ("missing", ["MISSING_RECORD_INPUTS"])
    assert check([*items, items[0]]) == ("missing", ["MISSING_RECORD_INPUTS"])
    extra = {**items[0], "entry": "input1"}
    assert check([*items, extra]) == ("missing", ["MISSING_RECORD_INPUTS"])


def test_a_record_of_an_output_that_lists_no_inputs_has_none(tmp_path: Path) -> None:
    """§19: a record of an output that lists no inputs can leave `inputs` out."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL})
    build(top)
    assert "inputs" not in json.loads((top / ".astra" / "records" / "result.json").read_text())
    assert statuses(api.check(top)) == {"result": ("unchanged", "present")}


def test_a_record_whose_commit_cant_be_read_makes_its_result_stale(worked: Path) -> None:
    """§20: a valid record naming a commit the repository hasn't makes its result
    `stale`, with that as its reason; and so does one naming a commit at which its output
    isn't there. Its bytes are still compared with the record's."""
    path = worked / ".astra" / "records" / "output2.json"
    rewrite(path, lambda value: value["generated_by"].update(commit="0" * 40))
    report = api.check(worked)
    assert statuses(report)["output2"] == ("stale", "present")
    assert reasons(report, "output2") == ["STALE_RESULT"]
    assert "0" * 40 in messages(report, "output2")[0]
    (worked / "astra.yaml").write_text(MINIMAL)
    git(worked, "commit", "--quiet", "--all", "--message", "minimal")
    before = git(worked, "rev-parse", "HEAD").strip()
    (worked / "astra.yaml").write_text(WORKED_EXAMPLE)
    rewrite(path, lambda value: value["generated_by"].update(commit=before))
    report = api.check(worked)
    assert statuses(report)["output2"] == ("stale", "present")
    assert reasons(report, "output2") == ["STALE_RESULT"]
    assert "`output2` names no output" in messages(report, "output2")[0]


# --- STALE_RESULT: §20 *When a result is unchanged* ---


def test_editing_a_description_or_a_label_changes_nothing(worked: Path) -> None:
    """§20: editing a description leaves a result unchanged, and so does a label: STALE_RESULT
    compares neither. A finding reworded is §20's table (`EDITS`)."""
    text = WORKED_EXAMPLE.replace(
        "    type: table\n", "    type: table\n    description: The comparison.\n"
    )
    (worked / "astra.yaml").write_text(text.replace("label: Example", "label: An example"))
    assert statuses(api.check(worked)) == UNCHANGED


@pytest.mark.parametrize(
    "old, new, what",
    [
        ("python src/output1.py", "python3 src/output1.py", "its recipe's command"),
        ("format: json", "format: csv", "its format is `csv`, where it was `json`"),
    ],
)
def test_a_change_to_the_outputs_declaration_makes_it_stale(
    worked: Path, old: str, new: str, what: str
) -> None:
    """STALE_RESULT: its recipe's command, and its format, the extension of its default place
    (§10), so that its bytes are absent there too; and `output2`, which reads it, is stale."""
    (worked / "astra.yaml").write_text(WORKED_EXAMPLE.replace(old, new, 1))
    report = api.check(worked)
    assert statuses(report)["output1#u1"][0] == "stale"
    assert messages(report, "output1#u1")[0].startswith(what)
    assert statuses(report)["output2"][0] == "stale"


def test_the_order_of_inputs_counts_and_that_of_decisions_doesnt(tmp_path: Path) -> None:
    """§20: its inputs and their order (`{inputs}` passes them in that order), and its
    decisions, in any order (each reaches the recipe by name)."""
    text = WORKED_EXAMPLE.replace(
        "    options:\n      a: {}\n      b: {}\n",
        "    options:\n      a: {}\n      b: {}\n  decision2:\n    options: {c: {}}\n",
    ).replace("decisions: [decision1]", "decisions: [decision1, decision2]")
    text = text.replace("{decision1: a}", "{decision1: a, decision2: c}").replace(
        "{decision1: b}", "{decision1: b, decision2: c}"
    )
    top = repository(tmp_path, {"astra.yaml": text, "data/input1.csv": "1\n"})
    build(top)
    (top / "astra.yaml").write_text(
        text.replace("[decision1, decision2]", "[decision2, decision1]")
    )
    report = api.check(top)
    assert {s[0] for s in statuses(report).values()} == {"unchanged"}
    (top / "astra.yaml").write_text(
        text.replace("[output1#u1, output1#u2]", "[output1#u2, output1#u1]")
    )
    report = api.check(top)
    assert statuses(report)["output2"][0] == "stale"
    assert messages(report, "output2") == [
        "its inputs are [`output1#u2`, `output1#u1`], in that order, where they were "
        f"[`output1#u1`, `output1#u2`] at {git(top, 'rev-parse', 'HEAD').strip()[:12]}"
    ]


def test_a_result_made_again_with_other_bytes_makes_its_readers_stale(worked: Path) -> None:
    """§20's table: the script `output1`'s recipe runs is edited, and all three stay unchanged;
    once `output1` in `u1` is made again with other bytes, `output2` is stale until it is
    rebuilt, and unchanged again where the rebuilt bytes are the same."""
    (worked / "src").mkdir()
    (worked / "src" / "output1.py").write_text("print('edited')\n")
    git(worked, "add", "src")
    git(worked, "commit", "--quiet", "--message", "the script is edited")
    assert statuses(api.check(worked)) == UNCHANGED
    remake(worked, "output1#u1", b"output1#u1\n")  # the same bytes
    assert statuses(api.check(worked)) == UNCHANGED
    remake(worked, "output1#u1", b"other\n")
    report = api.check(worked)
    assert statuses(report)["output2"] == ("stale", "present")
    assert messages(report, "output2") == [
        "`output1#u1`, which it reads, was made again since, with other bytes than it read"
    ]
    remake(worked, "output2", b"output2\n")
    assert statuses(api.check(worked)) == UNCHANGED


LFS = f"version https://git-lfs.github.com/spec/v1\noid sha256:{'a' * 64}\nsize 6\n"

STANDING_IN = MINIMAL.replace("    format: json\n", "    format: json\n    inputs: [input1]\n") + (
    "inputs:\n  input1: {path: data/input1.bin}\n"
)


def test_an_inputs_content_is_never_what_stands_in_for_it(tmp_path: Path) -> None:
    """STALE_RESULT compares the content of its inputs, never what stands in for it (§20): a
    Git LFS pointer gives its content's hash and size (design §4.5), and the record of what the
    recipe read holds those, not the pointer's own."""
    top = repository(tmp_path, {"astra.yaml": STANDING_IN, "data/input1.bin": LFS})
    build(top)  # it hashes the pointer, as no runner would
    report = api.check(top)
    assert statuses(report) == {"result": ("stale", "present")}
    assert messages(report, "result") == [
        "the content of `input1`, data/input1.bin, isn't what the recipe read"
    ]
    path = top / ".astra" / "records" / "result.json"
    content = {"entry": "input1", "content_hash": f"sha256:{'a' * 64}", "size": 6}
    rewrite(path, lambda value: value["generated_by"].update(inputs=[content]))
    assert statuses(api.check(top)) == {"result": ("unchanged", "present")}


# --- ABSENT_RESULT ---


def test_bytes_that_arent_the_recorded_ones_are_absent(worked: Path) -> None:
    """ABSENT_RESULT, a SHOULD: other bytes, a stand-in or nothing at the default place are
    `absent`, which leaves the record `unchanged` and the check passing (§18, §20)."""
    (worked / "results" / "output2.csv").write_text("other\n")
    report = api.check(worked)
    assert statuses(report)["output2"] == ("unchanged", "absent")
    (reason,) = [r for c in report.results for s in c.statuses for r in s.reasons]
    assert (reason.code, reason.level, reason.location.file) == (
        "ABSENT_RESULT",
        "warning",
        "results/output2.csv",
    )
    assert report.ok
    (worked / "results" / "output2.csv").write_text(LFS)
    assert statuses(api.check(worked))["output2"] == ("unchanged", "absent")
    (worked / "results" / "output2.csv").unlink()
    assert statuses(api.check(worked))["output2"] == ("unchanged", "absent")


# --- STALE_EVIDENCE: §20 *Evidence* ---


def test_evidence_gets_the_status_of_the_records_it_cites(worked: Path) -> None:
    """STALE_EVIDENCE: an `artifact` pinned names one result; one naming an output built per
    universe without a pin cites its results in each of the root's universes, and gets the
    worst of their statuses, `missing` then `stale`."""
    text = WORKED_EXAMPLE.replace(
        "      - artifact: output2\n",
        "      - artifact: output2\n      - artifact: output1#u2\n      - artifact: output1\n",
    )
    (worked / "astra.yaml").write_text(text)
    report = api.check(worked)
    assert [(e.artifact, e.cites, e.record_status) for e in report.evidence] == [
        ("output2", ("output2",), "unchanged"),
        ("output1#u2", ("output1#u2",), "unchanged"),
        ("output1", ("output1#u1", "output1#u2"), "unchanged"),
    ]
    (worked / "astra.yaml").write_text(text.replace("{decision1: a}", "{decision1: b}"))
    report = api.check(worked)
    assert [e.record_status for e in report.evidence] == ["stale", "unchanged", "stale"]
    (worked / ".astra" / "records" / "u2" / "output1.json").unlink()
    report = api.check(worked)
    assert [e.record_status for e in report.evidence] == ["stale", "missing", "missing"]
    evidence = report.evidence[2]
    assert [(r.code, r.level, r.location.pointer) for r in evidence.reasons] == [
        ("STALE_EVIDENCE", "error", "/findings/insight1/evidence/2/artifact")
    ]


UNBUILT = MINIMAL + (
    """\
analyses:
  lib: {path: lib}
universes:
  u1:
    decisions: {}
findings:
  insight1:
    claim: lib's out is cited.
    evidence:
      - artifact: lib.out
"""
)
"""A root whose evidence cites `lib`'s `out`, built per universe, without a pin, though no
universe of the root drives `lib`."""


def test_evidence_that_cites_no_result_is_missing_and_fails_the_check(tmp_path: Path) -> None:
    """§20 *Evidence*: an `artifact` naming an output built per universe without a pin cites its
    results in each of the root's universes where its analysis is built, here none, and if there
    are none, it is `missing`; design §4.12: `astra check` exits 1, though every planned result is
    unchanged."""
    top = repository(tmp_path, {"astra.yaml": UNBUILT, "lib/astra.yaml": LIB})
    build(top)
    report = api.check(top)
    assert statuses(report) == {"result": ("unchanged", "present")}
    assert [(e.cites, e.record_status) for e in report.evidence] == [((), "missing")]
    assert [r.code for r in report.evidence[0].reasons] == ["STALE_EVIDENCE"]
    assert astra("check", str(top)).exit_code == 1


CITING = (
    PAIR
    + """\
findings:
  insight1:
    claim: Both chains reach one result.
    evidence:
      - artifact: stage.inner.output1#u1
"""
)


@pytest.fixture
def pair(tmp_path: Path) -> Path:
    """§18's `inner`, reached through `inner` and `stage.inner`, built, with evidence citing
    `stage.inner.output1#u1`."""
    files = {"astra.yaml": CITING, "stage/astra.yaml": STAGE, "stage/inner/astra.yaml": INNER}
    top = repository(tmp_path, files)
    build(top)
    return top


def test_a_result_with_two_names_gets_its_statuses_at_each_place(pair: Path) -> None:
    """§20: a result with two names gets its statuses at each place (§18)."""
    (pair / ".astra" / "records" / "u1" / "inner.output1.json").unlink()
    found = statuses(api.check(pair))
    assert found["inner.output1#u1"] == ("missing", "absent")
    assert found["stage.inner.output1#u1"] == ("unchanged", "present")


CITING_SUBANALYSIS = SUBANALYSIS + (
    """\
findings:
  own:
    claim: Its decision changes its output.
    evidence:
      - artifact: output1
      - artifact: unread
"""
)
"""§15's `subanalysis`, whose evidence cites its `output1`, built per universe, and `unread`,
which nothing plans."""


def test_a_declared_analysiss_evidence_citing_a_planned_result_gets_a_status(
    tmp_path: Path,
) -> None:
    """§20 *Evidence*: a check covers the evidence of each declared analysis that cites a result
    the root plans, not only the root's. `subanalysis`'s `output1` cites its results in each of
    the root's universes, as the root's evidence does, and not in `subanalysis`'s own `u1` and
    `v1`, though `output5`'s pins plan them too; its declarations give none of the names, so it
    gets the worst of their records. `unread`, which the root doesn't plan, gets no status. A
    missing one fails the check (`STALE_EVIDENCE`), shown under the file that holds it."""
    files = {
        "astra.yaml": ROOT,
        "data/input1.csv": "1\n",
        "subanalysis/astra.yaml": CITING_SUBANALYSIS,
        "subanalysis/data/input1.csv": "2\n",
    }
    top = repository(tmp_path, files)
    build(top)
    cites = ("subanalysis.output1#u1", "subanalysis.output1#u2")
    found = [
        (e.location.file, e.artifact, e.cites, e.record_status) for e in api.check(top).evidence
    ]
    assert found == [
        ("astra.yaml", "subanalysis.output1", cites, "unchanged"),
        ("subanalysis/astra.yaml", "output1", cites, "unchanged"),
    ]
    (top / "subanalysis" / ".astra" / "records" / "v1" / "output1.json").unlink()
    assert [e.record_status for e in api.check(top).evidence] == ["unchanged", "unchanged"]
    (top / ".astra" / "records" / "u2" / "subanalysis.output1.json").unlink()
    report = api.check(top)
    assert [e.record_status for e in report.evidence] == ["missing", "missing"]
    assert [(r.code, r.location.file, r.location.pointer) for r in report.evidence[1].reasons] == [
        ("STALE_EVIDENCE", "subanalysis/astra.yaml", "/findings/own/evidence/0/artifact")
    ]
    result = astra("check", str(top))
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    assert lines[lines.index("subanalysis/astra.yaml") + 1].endswith(
        "`output1` cites `subanalysis.output1#u1`, `subanalysis.output1#u2`, whose record is "
        "missing"
    )


def test_evidence_reads_the_record_of_the_name_along_its_declarations(pair: Path) -> None:
    """§20 *Evidence*: evidence citing `stage.inner.output1#u1` reads the record of
    `stage.inner.output1`, not of `inner.output1`."""
    records = pair / ".astra" / "records" / "u1"
    (records / "inner.output1.json").unlink()
    (evidence,) = api.check(pair).evidence
    assert (evidence.cites, evidence.record_status) == (("stage.inner.output1#u1",), "unchanged")
    (records / "stage.inner.output1.json").unlink()
    (evidence,) = api.check(pair).evidence
    assert evidence.record_status == "missing"


# --- §20 *Results of an analysis from a commit* ---


FROM_COMMIT = """\
spec_version: "0.1.0"
analyses:
  lib: {path: lib, commit: "%s"}
outputs:
  result:
    type: table
    format: csv
    inputs: [lib.out#v1]
    recipe:
      command: python make.py {inputs} '{output}'
findings:
  insight1:
    claim: lib's once is cited, and read by nothing.
    evidence:
      - artifact: lib.once
"""
"""A root that reads `lib`'s `out` in `lib`'s own `v1`, and cites `lib`'s `once`, `lib` read at
a commit that holds its records (§17 *Using one*)."""


def test_results_of_an_analysis_from_a_commit_are_read_through_their_records(
    tmp_path: Path,
) -> None:
    """§20: `lib` is built at `A` and its records committed in `B`, which the root declares.
    Its results are read through their records at `B`, unchanged where nothing changed between
    `A` and `B`; only `out`, which a planned result reads, gets a bytes status, from what `B`
    holds (§20 *Results of an analysis from a commit*)."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    build(top, top / "lib")
    holding = git(repository(top, {}), "rev-parse", "HEAD").strip()
    repository(top, {"astra.yaml": FROM_COMMIT % holding})
    report = api.check(top)
    assert statuses(report) == {
        "out#v1": ("unchanged", "present"),
        "result": ("missing", "absent"),
        "once": ("unchanged", None),
    }
    assert all(s.committed for c in report.results for s in c.statuses if c.result.read_only)
    assert [(e.cites, e.record_status) for e in report.evidence] == [(("once",), "unchanged")]
    build(top)
    assert {s[0] for s in statuses(api.check(top)).values()} == {"unchanged"}


CHAINED = LIB.replace(
    "universes:",
    "  twice:\n    type: metric\n    format: json\n    inputs: [once]\n"
    "    recipe:\n      command: python make.py {inputs} '{output}'\nuniverses:",
)
"""`lib`, whose `twice` reads its `once`."""


def test_a_result_of_an_analysis_from_a_commit_that_a_planned_result_reads_has_its_bytes(
    tmp_path: Path,
) -> None:
    """§20 *The rules*, ABSENT_RESULT: only a result of an analysis from a commit that no
    planned result reads is left out. `once` is read by `twice`, itself read through its
    record, so it gets a bytes status from what `B` holds, which hasn't its bytes: `absent`,
    and ABSENT_RESULT."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": CHAINED})
    build(top, top / "lib")
    (top / "lib" / "results" / "once.json").unlink()
    holding = git(repository(top, {}), "rev-parse", "HEAD").strip()
    root = FROM_COMMIT.split("findings:")[0].replace("lib.out#v1", "lib.twice")
    report = api.check(repository(top, {"astra.yaml": root % holding}))
    assert statuses(report) == {
        "twice": ("unchanged", "present"),
        "once": ("unchanged", "absent"),
        "result": ("missing", "absent"),
    }
    assert reasons(report, "once") == ["ABSENT_RESULT"]


def test_a_result_of_an_analysis_from_a_commit_is_stale_where_its_commit_changed_it(
    tmp_path: Path,
) -> None:
    """§20: unchanged only where nothing STALE_RESULT compares changed between the commit its
    record names, `A`, and the declared one, `B`; and a result made from it is stale too."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    build(top, top / "lib")
    edited = LIB.replace("python make.py '{decisions.d}'", "python3 make.py '{decisions.d}'")
    holding = git(repository(top, {"lib/astra.yaml": edited}), "rev-parse", "HEAD").strip()
    repository(top, {"astra.yaml": FROM_COMMIT % holding})
    build(top)
    report = api.check(top)
    assert statuses(report)["out#v1"] == ("stale", "present")
    assert statuses(report)["once"] == ("unchanged", None)
    assert messages(report, "result") == ["`out#v1`, which it reads through `lib.out#v1`, is stale"]


def test_results_of_an_analysis_from_another_repository_are_read_from_its_remote(
    tmp_path: Path,
) -> None:
    """§20: in the repository that holds that analysis at the commit it is read at, got from
    its `url` (§17), the record's own commit too."""
    remote = repository(tmp_path / "remote", {"astra.yaml": LIB})
    build(remote)
    holding = git(repository(remote, {}), "rev-parse", "HEAD").strip()
    url = remote.as_uri()
    text = FROM_COMMIT.replace('{path: lib, commit: "%s"}', f"{{url: '{url}', commit: '%s'}}")
    top = repository(tmp_path / "top", {"astra.yaml": text % holding})
    report = api.check(top)
    assert statuses(report) == {
        "out#v1": ("unchanged", "present"),
        "result": ("missing", "absent"),
        "once": ("unchanged", None),
    }
    (checked,) = [c for c in report.results if c.result.names == ("out",)]
    assert checked.statuses[0].reasons == ()
    assert (checked.result.owner.commit, report.evidence[0].record_status) == (holding, "unchanged")


def test_what_a_driver_builds_of_an_analysis_from_a_commit_is_checked_as_its_own(
    tmp_path: Path,
) -> None:
    """§17 *Using one*, §19: what the root's universes build of `lib` belongs to the root, and
    its record names the root's commit, at which the root's file declares `lib` at its commit;
    a universe that selects another option for `lib`'s decision makes it stale, and what reads
    it."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL, "lib/astra.yaml": LIB})
    build(top, top / "lib")
    holding = git(repository(top, {}), "rev-parse", "HEAD").strip()
    repository(top, {"astra.yaml": DRIVING % holding})
    build(top)
    assert {s[0] for s in statuses(api.check(top)).values()} == {"unchanged"}
    (top / "astra.yaml").write_text((DRIVING % holding).replace("lib.d: a", "lib.d: b"))
    report = api.check(top)
    assert statuses(report)["lib.out#u1"][0] == "stale"
    assert statuses(report)["out#v1"][0] == "unchanged"
    assert messages(report, "result#u1") == [
        "`lib.out#u1`, which it reads through `lib.out`, is stale"
    ]


# --- committed, and --at ---


def test_committed_says_whether_git_has_the_record_as_it_is(worked: Path) -> None:
    """Design §4.7: the record at its place in HEAD's tree, byte for byte."""
    report = api.check(worked)
    assert {s.committed for c in report.results for s in c.statuses} == {False}
    git(worked, "add", "--all")
    git(worked, "commit", "--quiet", "--message", "records")
    report = api.check(worked)
    assert {s.committed for c in report.results for s in c.statuses} == {True}
    rewrite(worked / ".astra" / "records" / "output2.json", lambda value: value.update(size=1))
    found = {s.place.address: s.committed for c in api.check(worked).results for s in c.statuses}
    assert found == {"output1#u1": True, "output1#u2": True, "output2": False}


def test_at_a_commit_the_stack_records_and_bytes_are_read_there(worked: Path) -> None:
    """design §4.7: `at=<commit>` checks the stack as it is at that commit, with its records and
    bytes read there: not yet committed, they aren't there."""
    head = git(worked, "rev-parse", "HEAD").strip()
    report = api.check(worked, at="HEAD")
    assert report.at == head
    assert {s[0] for s in statuses(report).values()} == {"missing"}
    git(worked, "add", "--all")
    git(worked, "commit", "--quiet", "--message", "records")
    text = WORKED_EXAMPLE.replace("decisions: {decision1: a}", "decisions: {decision1: b}")
    (worked / "astra.yaml").write_text(text)
    assert statuses(api.check(worked, at="HEAD")) == UNCHANGED
    assert statuses(api.check(worked))["output1#u1"][0] == "stale"
    with pytest.raises(api.RequestError):
        api.check(worked, at="nowhere")


# --- api.check narrowing, and the shape ---


def test_universes_and_outputs_only_narrow_the_report(worked: Path) -> None:
    """design §4.7: the results built in the universes asked for and of the outputs asked for;
    the evidence isn't narrowed (§20 *Evidence*: a check covers the evidence of the analysis it
    is run on)."""
    report = api.check(worked, universes=["u1"])
    assert list(statuses(report)) == ["output1#u1"]
    assert [e.artifact for e in report.evidence] == ["output2"]
    report = api.check(worked, outputs=["output2"])
    assert list(statuses(report)) == ["output2"]
    assert [e.artifact for e in report.evidence] == ["output2"]
    for asked in ({"universes": ["u3"]}, {"outputs": ["output3"]}):
        with pytest.raises(api.RequestError):
            api.check(worked, **asked)
    with pytest.raises(api.RequestError, match="no planned result in the universes asked for"):
        api.check(worked, universes=["u1"], outputs=["output2"])


UNDETERMINED = """\
  broken:
    type: table
    format: csv
    inputs: [nothing]
    recipe:
      command: python src/broken.py '{inputs}' '{output}'
  reader:
    type: table
    format: csv
    inputs: [broken]
    recipe:
      command: python src/reader.py '{inputs}' '{output}'
"""
"""Two outputs for §2's worked example: `broken` reads an address that names nothing, and
`reader` reads `broken`."""

INVALID_WORKED = WORKED_EXAMPLE.replace("\nuniverses:", UNDETERMINED + "\nuniverses:").replace(
    "      - artifact: output2\n", "      - artifact: output2\n      - artifact: reader\n"
)
"""§2's worked example, broken by `UNDETERMINED`, with evidence citing `reader` too."""


def test_an_invalid_analysis_gets_statuses_where_planning_is_determined(worked: Path) -> None:
    """Design §4.7: the report holds the validation errors, and every result whose planning
    is determined (design §4.13 case 12) gets its statuses, as does the evidence citing only
    such results. `broken` reads what names nothing (case 5), and `reader` reads `broken`, so
    neither gets a status, nor does the evidence citing `reader`; the rest are as they were. The
    check
    fails."""
    (worked / "astra.yaml").write_text(INVALID_WORKED)
    report = api.check(worked)
    assert [(d.code, d.location.pointer) for d in report.errors] == [
        ("UNRESOLVED_ADDRESS", "/outputs/broken/inputs/0")
    ]
    assert statuses(report) == UNCHANGED
    assert [(e.artifact, e.record_status) for e in report.evidence] == [("output2", "unchanged")]
    assert not report.ok


def test_results_on_a_cycle_get_no_statuses(tmp_path: Path) -> None:
    """Design §4.13 cases 12 and 13: a result that reads itself back, through another
    (OUTPUT_CYCLE), has no determined planning, nor has the other; the analysis's other result
    gets its statuses."""
    cycle = "".join(
        f"  {id_}:\n    type: metric\n    format: json\n    inputs: [{reads}]\n"
        "    recipe:\n      command: python make.py '{inputs}' '{output}'\n"
        for id_, reads in (("first", "second"), ("second", "first"))
    )
    report = api.check(repository(tmp_path, {"astra.yaml": MINIMAL + cycle}))
    assert [d.code for d in report.errors] == ["OUTPUT_CYCLE", "OUTPUT_CYCLE"]
    assert statuses(report) == {"result": ("missing", "absent")}


def test_an_analysis_with_no_stack_gets_no_statuses(tmp_path: Path) -> None:
    """Design §4.13 cases 2 and 12: a root whose file isn't a valid document is undetermined,
    so no result's planning is: the report holds only the errors."""
    top = repository(tmp_path, {"astra.yaml": MINIMAL.replace("type: metric", "type: plot")})
    report = api.check(top)
    assert [d.code for d in report.errors] == ["INVALID_VALUE"]
    assert (report.results, report.evidence, report.ok) == ((), (), False)


def test_the_report_as_astra_check_report_1(worked: Path) -> None:
    """Each result in the plan's order, with each place's statuses, `committed` and
    reasons, and design §4.7: what each environment scheme answered, none being registered; then the
    evidence."""
    (worked / "results" / "output2.csv").unlink()
    shape = api.check(worked).to_json()
    assert (shape["shape"], shape["root"], shape["at"]) == (
        "astra-check-report/1",
        "astra.yaml",
        "worktree",
    )
    assert shape["results"][2] == {
        "names": ["output2"],
        "owner": {"folder": "", "commit": None},
        "output": {"analysis": {"folder": "", "commit": None}, "kind": "output", "id": "output2"},
        "universe": None,
        "places": [
            {
                "name": "output2",
                "address": "output2",
                "record": ".astra/records/output2.json",
                "bytes": "results/output2.csv",
                "record_status": "unchanged",
                "bytes_status": "absent",
                "committed": False,
                "reasons": [
                    {
                        "code": "ABSENT_RESULT",
                        "level": "warning",
                        "message": "no file is at results/output2.csv, the result's default place",
                        "location": {
                            "file": "results/output2.csv",
                            "pointer": "",
                            "line": None,
                            "column": None,
                            "key": None,
                            "commit": None,
                            "url": None,
                        },
                        "breaks": None,
                    }
                ],
                "environment": [],
            }
        ],
    }
    assert shape["errors"] == []
    (evidence,) = shape["evidence"]
    assert {key: evidence[key] for key in ("artifact", "cites", "record_status", "reasons")} == {
        "artifact": "output2",
        "cites": ["output2"],
        "record_status": "unchanged",
        "reasons": [],
    }
    assert evidence["location"]["pointer"] == "/findings/insight1/evidence/0/artifact"


# --- astra check ---


def test_astra_check_exits_0_when_every_result_is_unchanged(worked: Path) -> None:
    result = astra("check", str(worked))
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert (
        lines[0] == ".astra/records/u1/output1.json  output1#u1  unchanged  present  not committed"
    )
    assert lines[3] == "astra.yaml"
    assert lines[4].endswith("unchanged `output2`")
    assert lines[-1] == (
        "astra.yaml: 3 place(s) of planned results, 3 unchanged, 0 stale, 0 missing; 0 absent"
    )


def test_astra_check_exits_1_when_one_isnt(worked: Path) -> None:
    (worked / "data" / "input1.csv").write_text("2\n")
    result = astra("check", str(worked))
    assert result.exit_code == 1
    assert "  error STALE_RESULT the content of `input1`" in result.stdout
    shape = json.loads(astra("check", str(worked), "--json").stdout)
    assert [p["record_status"] for r in shape["results"] for p in r["places"]] == ["stale"] * 3


def test_astra_check_of_an_invalid_analysis_shows_why_and_exits_1(worked: Path) -> None:
    """Design §4.7: the errors first, as `astra validate` shows them, then the statuses they
    leave determined; with `--json`, its shape, which holds the errors."""
    (worked / "astra.yaml").write_text(INVALID_WORKED)
    result = astra("check", str(worked))
    assert result.exit_code == 1
    assert result.stdout.index("UNRESOLVED_ADDRESS") < result.stdout.index("output2  unchanged")
    assert "astra.yaml: invalid, 1 error(s), so only the results it leaves" in result.stdout
    shape = json.loads(astra("check", str(worked), "--json").stdout)
    assert shape["shape"] == "astra-check-report/1"
    assert [d["code"] for d in shape["errors"]] == ["UNRESOLVED_ADDRESS"]
    assert len(shape["results"]) == 3


def test_astra_check_exits_2_where_it_cant_check(tmp_path: Path, worked: Path) -> None:
    result = astra("check", str(tmp_path / "nothere"))
    assert result.exit_code == 2
    result = astra("check", str(worked), "--at", "nowhere")
    assert result.exit_code == 2
    assert "--at" in result.stderr


# --- design §6, phase 3: every check code has a case ---


def _pop_an_input(top: Path) -> None:
    rewrite(
        top / ".astra/records/output2.json", lambda value: value["generated_by"]["inputs"].pop()
    )


BREAKING: Mapping[str, tuple[str, Callable[[Path], object]]] = {
    "MISSING_RECORD": ("§20", lambda top: (top / ".astra/records/output2.json").unlink()),
    "INVALID_RECORD": (
        "§20 The rules",
        lambda top: (top / ".astra/records/output2.json").write_text("{"),
    ),
    "MISPLACED_RECORD": (
        "§18",
        lambda top: shutil.copy(
            top / ".astra/records/u1/output1.json", top / ".astra/records/u2/output1.json"
        ),
    ),
    "MISSING_RECORD_INPUTS": ("§19", _pop_an_input),
    "STALE_RESULT": ("§2 Checking", lambda top: (top / "data/input1.csv").write_text("2\n")),
    "ABSENT_RESULT": ("§20", lambda top: (top / "results/output2.csv").unlink()),
    "STALE_EVIDENCE": (
        "§20 Evidence",
        lambda top: (top / "astra.yaml").write_text(
            WORKED_EXAMPLE.replace("{decision1: a}", "{decision1: b}")
        ),
    ),
}
"""For each check code, an edit of the built worked example that breaks it, and the section it
comes from. The worked example as built keeps every one
(`test_a_built_analysis_is_unchanged_and_present`)."""


def test_every_check_code_has_a_case() -> None:
    """design §3: the codes the checker declares are the check layer's, and each has a case."""
    assert CODES == set(BREAKING) == set(Catalogue.load().codes("check"))


@pytest.mark.parametrize("code", sorted(BREAKING))
def test_the_checker_reports_each_code(worked: Path, code: str) -> None:
    section, edit = BREAKING[code]
    edit(worked)
    report = api.check(worked)
    found = {r.code for c in report.results for s in c.statuses for r in s.reasons}
    found |= {r.code for evidence in report.evidence for r in evidence.reasons}
    assert code in found, (section, found)


# --- design §6, phase 3: §20's table of edits, the records committed ---


@pytest.fixture(scope="module")
def committed(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """§2's worked example with the scripts its recipes run, built from its commit, its records
    and bytes then committed in a later commit (§19)."""
    files = {
        "astra.yaml": WORKED_EXAMPLE,
        "data/input1.csv": "1\n",
        "src/output1.py": "print('output1')\n",
        "src/output2.py": "print('output2')\n",
    }
    top = repository(tmp_path_factory.mktemp("committed"), files)
    build(top)
    return repository(top, {})


def _select(universe: str, option: str) -> Callable[[Path], object]:
    """The edit by which `universe` selects `option` for `decision1`."""
    old = "{decision1: a}" if universe == "u1" else "{decision1: b}"
    text = WORKED_EXAMPLE.replace(
        f"{universe}:\n    decisions: {old}", f"{universe}:\n    decisions: {{decision1: {option}}}"
    )
    assert text != WORKED_EXAMPLE
    return lambda top: (top / "astra.yaml").write_text(text)


EDITS: Mapping[str, tuple[Callable[[Path], object], tuple[str, str, str], Mapping[str, str]]] = {
    "§20: `u1` selects another option for `decision1`": (
        _select("u1", "b"),
        ("stale", "unchanged", "stale"),
        {
            "output1#u1": "`decision1` selects `b` in `u1`, where it selected `a` at {commit}",
            "output2": "`output1#u1`, which it reads, is stale",
        },
    ),
    "§20: `insight1`'s claim is reworded": (
        lambda top: (top / "astra.yaml").write_text(
            WORKED_EXAMPLE.replace("give different results.", "don't give the same results.")
        ),
        ("unchanged", "unchanged", "unchanged"),
        {},
    ),
    "§20: the script that `output1`'s recipe runs is edited": (
        lambda top: (top / "src/output1.py").write_text("print('edited')\n"),
        ("unchanged", "unchanged", "unchanged"),
        {},
    ),
    "§2: `data/input1.csv` is changed": (
        lambda top: (top / "data/input1.csv").write_text("2\n"),
        ("stale", "stale", "stale"),
        {"output1#u1": "the content of `input1`, data/input1.csv, isn't what the recipe read"},
    ),
    "§2: `u2` selects `a`": (
        _select("u2", "a"),
        ("unchanged", "stale", "stale"),
        {"output1#u2": "`decision1` selects `a` in `u2`, where it selected `b` at {commit}"},
    ),
}
"""Each edit of §20's table, and of §2's *Checking*, the record statuses it leaves `output1` in
`u1`, `output1` in `u2` and `output2` with, and what the checker says changed at some of their
places, `{commit}` being the commit the records name (design §4.7: "A stale result says what
changed")."""


@pytest.mark.parametrize("edit", EDITS)
def test_each_edit_of_20s_table_gives_its_effect(
    committed: Path, tmp_path: Path, edit: str
) -> None:
    top = Path(shutil.copytree(committed, tmp_path / "top", symlinks=True))
    assert statuses(api.check(top)) == UNCHANGED
    change, effect, said = EDITS[edit]
    change(top)
    report = api.check(top)
    assert tuple(s[0] for s in statuses(report).values()) == effect
    commit = git(top, "rev-parse", "HEAD~1").strip()[:12]
    for address, message in said.items():
        assert messages(report, address) == [message.format(commit=commit)]
