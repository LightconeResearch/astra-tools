"""The catalogue: levels from rules.json, and the codes each check declares (§3, design §3)."""

from __future__ import annotations

import pytest

from astra import contract, load, validate
from astra.diagnostics import Catalogue, Location

AT = Location("astra.yaml", "", None, None)


def test_a_must_is_an_error_and_a_should_a_warning() -> None:
    catalogue = Catalogue.load()
    assert catalogue.diagnostic("MISSING_FIELD", "m", AT).level == "error"
    assert catalogue.rules["RESULT_IN_TWO_PLACES"].level == "SHOULD"
    assert catalogue.diagnostic("RESULT_IN_TWO_PLACES", "m", AT).level == "warning"


def test_a_code_missing_from_the_catalogue_is_an_internal_error() -> None:
    with pytest.raises(LookupError, match="NO_SUCH_CODE"):
        Catalogue.load().diagnostic("NO_SUCH_CODE", "m", AT)


def test_the_parse_layer_is_what_load_declares() -> None:
    assert set(Catalogue.load().codes("parse")) == load.CODES


def test_the_schema_layer_is_what_the_error_map_gives() -> None:
    catalogue = Catalogue.load()
    assert set(catalogue.errors.values()) == set(catalogue.codes("schema"))


def test_the_other_declared_codes_are_the_catalogues() -> None:
    catalogue = Catalogue.load()
    assert {catalogue.rules[code].layer for code in contract.CODES} == {"validator", "check"}
    assert {catalogue.rules[code].layer for code in validate.CODES} == {"validator"}
