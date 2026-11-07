"""Records, read as Annex A says and checked by the record schema their minor version picks
(§3, §5 *Versions*, §20, Annex E)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from astra.contract import Contract
from astra.diagnostics import Catalogue
from astra.load import ParseError, load_json
from tests.conftest import SPEC

RECORD = json.loads(
    (SPEC / "tests" / "data" / "valid" / "ProvenanceRecord-001-full.json").read_text("utf-8")
)
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
    """It ignores the fields that version adds, and is checked for the rest (Annex E)."""
    later = {**RECORD, "spec_version": "0.2.0", "extra": 1}
    assert check(contract, later) == []
    del later["size"]
    assert check(contract, later) == [("MISSING_FIELD", "", None)]


def test_a_record_below_0_1_has_no_schema(contract: Contract) -> None:
    """Records begin at 0.1.0 (§3): INVALID_RECORD, at its version (§20)."""
    old = {**RECORD, "spec_version": "0.0.9", "extra": 1}
    assert check(contract, old) == [("INVALID_RECORD", "/spec_version", None)]


def test_a_malformed_version_is_read_by_the_0_1_schema(contract: Contract) -> None:
    assert check(contract, {**RECORD, "spec_version": "0.1"}) == [
        ("INVALID_VALUE", "/spec_version", None)
    ]


@pytest.mark.parametrize(
    "text, code",
    [
        ('{"size": 1, "size": 2}', "DUPLICATE_KEY"),
        ('{"size": 1, "\\u0073ize": 2}', "DUPLICATE_KEY"),
        ('{"size": NaN}', "INVALID_SYNTAX"),
        ('{"size": -Infinity}', "INVALID_SYNTAX"),
        ("size: 1", "INVALID_SYNTAX"),
    ],
)
def test_a_record_that_isnt_json_breaks_a_parse_rule(text: str, code: str) -> None:
    """Annex A: RFC 8259 JSON text, with distinct names."""
    with pytest.raises(ParseError) as raised:
        load_json(text.encode())
    assert raised.value.code == code


def test_a_record_is_utf_8() -> None:
    """Annex A: JSON text in UTF-8."""
    with pytest.raises(ParseError) as raised:
        load_json(b'{"x": "\xe9"}')
    assert raised.value.code == "INVALID_SYNTAX"


def test_a_record_that_is_json_is_read() -> None:
    assert load_json('{"x": [1, 2.5, "é", null, true]}'.encode()).value == {
        "x": [1, 2.5, "é", None, True]
    }
