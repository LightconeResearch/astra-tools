"""The catalogue: levels from rules.json, and the codes each check declares."""

from __future__ import annotations

import pytest

from astra import contract, load, rules, validate
from astra.diagnostics import OWN, Catalogue, Location
from astra.evidence import quotes

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


def test_the_other_declared_codes_are_the_catalogues_or_astra_tools() -> None:
    catalogue = Catalogue.load()
    assert {catalogue.rule(code).layer for code in contract.CODES} == {"validator", "check"}
    assert {catalogue.rule(code).layer for code in validate.CODES} == {"validator"}
    assert {catalogue.rule(code).layer for code in rules.CODES} == {"validator"}


def test_astra_tools_own_codes_are_none_of_rules_json() -> None:
    """The four codes astra-tools has of its own, beside rules.json's, which has none of them."""
    catalogue = Catalogue.load()
    assert set(OWN) == {
        "UNSUPPORTED_SPEC_VERSION",
        "REMOTE_UNREACHABLE",
        "COMMIT_NOT_ANCESTOR",
        "EVIDENCE_PAPER_MISSING",
    }
    assert not set(OWN) & set(catalogue.rules)
    assert [catalogue.level(code) for code in OWN] == ["error", "error", "warning", "warning"]


def test_every_code_astra_tools_has_of_its_own_is_checked() -> None:
    """Each of astra-tools' own codes is declared by a check, as rules.json's are."""
    assert set(OWN) <= contract.CODES | validate.CODES | rules.CODES | quotes.CODES


def test_the_evidence_layer_is_what_quotes_declares() -> None:
    assert set(Catalogue.load().codes("evidence")) == quotes.CODES


def test_no_two_checks_declare_one_code() -> None:
    declared = [load.CODES, contract.CODES, validate.CODES, quotes.CODES]
    declared += [m.CODES for m in rules.MODULES]
    assert sum(len(codes) for codes in declared) == len(frozenset().union(*declared))
