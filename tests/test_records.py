"""Records, read as UTF-8 JSON text and checked by the record schema their minor version picks;
and `records`: reading one at a place, writing one, and making a result's records from its run."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from astra import api
from astra.contract import Contract
from astra.diagnostics import Catalogue
from astra.hashing import digest_bytes
from astra.load import ParseError, load_json
from astra.records import Record, RecordedInput, Runner, new_record, read_record, write_record
from astra.sources.reader import WorktreeReader
from tests.conftest import DOCUMENTS, RUNNER, git, repository
from tests.test_plan import INNER, PAIR, STAGE

RECORD = json.loads((DOCUMENTS / "valid" / "ProvenanceRecord-001-full.json").read_text("utf-8"))
"""A valid record of 0.1, astra-spec's fixture."""


@pytest.fixture(scope="module")
def contract() -> Contract:
    return Contract.load(Catalogue.load())


def check(contract: Contract, record: Any) -> list[tuple[str, str, str | None]]:
    document = load_json(json.dumps(record).encode())
    found = contract.check_record(document, "record.json")
    return [(d.code, d.location.pointer, d.location.key) for d in found]


def test_a_record_of_0_1_is_read_by_the_closed_schema(contract: Contract) -> None:
    assert check(contract, RECORD) == []
    assert check(contract, {**RECORD, "extra": 1}) == [("UNKNOWN_FIELD", "", "extra")]
    assert check(contract, {**RECORD, "spec_version": "0.1.9"}) == []


def test_a_record_of_a_later_minor_is_read_by_the_open_schema(contract: Contract) -> None:
    """It ignores the fields that version adds, and is checked for the rest."""
    later = {**RECORD, "spec_version": "0.2.0", "extra": 1}
    assert check(contract, later) == []
    del later["size"]
    assert check(contract, later) == [("MISSING_FIELD", "", None)]


def test_a_record_below_0_1_has_no_schema(contract: Contract) -> None:
    """Records begin at 0.1.0: INVALID_RECORD, at its version."""
    old = {**RECORD, "spec_version": "0.0.9", "extra": 1}
    assert check(contract, old) == [("INVALID_RECORD", "/spec_version", None)]


def test_a_malformed_version_is_read_by_the_0_1_schema(contract: Contract) -> None:
    assert check(contract, {**RECORD, "spec_version": "0.1"}) == [
        ("INVALID_VALUE", "/spec_version", None)
    ]


@pytest.mark.parametrize(
    "text",
    ['{"size": 1, "size": 2}', '{"size": 1, "\\u0073ize": 2}', '{"size": NaN}', "size: 1"],
)
def test_a_record_that_isnt_json_breaks_invalid_syntax(text: str) -> None:
    """RFC 8259 JSON text, in which no object has two equal names; and no `NaN`, which
    `json.loads` would take."""
    with pytest.raises(ParseError) as raised:
        load_json(text.encode())
    assert raised.value.code == "INVALID_SYNTAX"


def test_a_repeated_name_is_named() -> None:
    """A repeated name is INVALID_SYNTAX, whose message names it."""
    with pytest.raises(ParseError, match='the name "size" is twice'):
        load_json(b'{"size": 1, "size": 2}')


def test_a_record_is_utf_8() -> None:
    """A record is JSON text in UTF-8."""
    with pytest.raises(ParseError) as raised:
        load_json(b'{"x": "\xe9"}')
    assert raised.value.code == "INVALID_SYNTAX"


def test_a_record_that_is_json_is_read() -> None:
    assert load_json('{"x": [1, 2.5, "é", null, true]}'.encode()).value == {
        "x": [1, 2.5, "é", None, True]
    }


# --- reading, writing and making records ---


def test_a_record_is_written_with_sorted_keys_two_spaces_and_a_final_line_break(
    tmp_path: Path, contract: Contract
) -> None:
    record = Record.from_json(RECORD)
    path = tmp_path / ".astra" / "records" / "u1" / "output1.json"
    write_record(path, record)
    text = path.read_text("utf-8")
    assert text == json.dumps(RECORD, indent=2, sort_keys=True) + "\n"
    assert [p.name for p in path.parent.iterdir()] == ["output1.json"]  # no temporary file left
    reader = WorktreeReader(tmp_path, None)
    assert read_record(reader, ".astra/records/u1/output1.json", contract) == record


def test_reading_a_record_gives_it_or_each_rule_it_breaks(
    tmp_path: Path, contract: Contract
) -> None:
    """A record that breaks a parse or schema rule gives its diagnostic, at its place in the
    record; nothing at the path, or a symlink there, is no record."""
    (tmp_path / "broken.json").write_text(json.dumps({**RECORD, "size": -1}))
    (tmp_path / "bad.json").write_text("{")
    (tmp_path / "link.json").symlink_to("broken.json")
    reader = WorktreeReader(tmp_path, None)
    found = read_record(reader, "broken.json", contract)
    assert isinstance(found, tuple)
    assert [(d.code, d.location.file, d.location.pointer) for d in found] == [
        ("INVALID_VALUE", "broken.json", "/size")
    ]
    found = read_record(reader, "bad.json", contract)
    assert isinstance(found, tuple) and [d.code for d in found] == ["INVALID_SYNTAX"]
    assert read_record(reader, "link.json", contract) is None
    assert read_record(reader, "nothere.json", contract) is None


def test_a_later_minor_versions_fields_are_left_out_of_the_record(contract: Contract) -> None:
    later = {**RECORD, "spec_version": "0.2.0", "extra": 1}
    assert Record.from_json(later).to_json() == {**RECORD, "spec_version": "0.2.0"}


def test_new_record_fills_in_each_names_record(tmp_path: Path, contract: Contract) -> None:
    """The hash and size of the bytes made, at the first name's default place, and of what each
    entry read, the commit, environment, runner and times; and each name's record has the
    result's address at that name."""
    files = {"astra.yaml": PAIR, "stage/astra.yaml": STAGE, "stage/inner/astra.yaml": INNER}
    top = repository(tmp_path, files)
    commit = git(top, "rev-parse", "HEAD").strip()
    by_address = {r.places[0].address: r for r in api.plan(top).results}
    inner = by_address["inner.output1#u1"]
    (top / inner.places[0].bytes).parent.mkdir(parents=True)
    (top / inner.places[0].bytes).write_bytes(b"{}\n")
    started = datetime(2026, 10, 26, 14, 0, 0, 123456, tzinfo=UTC)
    records = new_record(
        inner,
        checkout=top,
        commit=commit,
        environment="urn:example:env",
        runner=Runner("example-runner", "1.2.0"),
        started=started,
        finished=started + timedelta(seconds=2),
    )
    made = digest_bytes(b"{}\n")
    assert [record.address for record in records] == ["inner.output1#u1", "stage.inner.output1#u1"]
    assert records[1].to_json() == {
        "spec_version": "0.1.0",
        "address": "stage.inner.output1#u1",
        "content_hash": made.content_hash,
        "size": 3,
        "generated_by": {
            "commit": commit,
            "environment": {"iri": "urn:example:env"},
            "runner": {"id": "example-runner", "version": "1.2.0"},
            "started": "2026-10-26T14:00:00.123Z",
            "finished": "2026-10-26T14:00:02.123Z",
        },
    }
    through = by_address["through_inner#u1"]
    (top / through.places[0].bytes).write_bytes(b"[]\n")
    (record,) = new_record(
        through, checkout=top, commit=commit, environment="urn:example:env", runner=RUNNER
    )
    assert record.inputs == (RecordedInput("inner.output1", made.content_hash, 3),)
    write_record(top / through.places[0].record, record)
    reader = WorktreeReader(top, None)
    assert read_record(reader, through.places[0].record, contract) == record
