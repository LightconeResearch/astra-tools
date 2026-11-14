"""The forms of a name: an address, a reference with its pin, and an option reference."""

from __future__ import annotations

from astra.grammar import (
    Address,
    parse_address,
    parse_option_reference,
    parse_reference,
)


def test_an_address_is_its_declarations_then_its_element() -> None:
    """`subanalysis.decision1` is the decision `decision1` of the analysis declared as
    `subanalysis`; `decision1` alone is an element of the analysis itself."""
    address = parse_address("subanalysis.decision1")
    assert (address.declarations, address.id) == (("subanalysis",), "decision1")
    assert parse_address("decision1").declarations == ()
    assert str(address) == "subanalysis.decision1"


def test_a_reference_may_end_in_a_pin() -> None:
    """Elements *reference* and *pin*: `output1#u1`."""
    reference = parse_reference("subanalysis.output1#u1")
    assert (reference.address, reference.pin) == (Address(("subanalysis", "output1")), "u1")
    assert parse_reference("output1").pin is None


def test_the_last_segment_of_an_option_reference_is_the_option() -> None:
    """The option `a` of `subanalysis`'s `decision1` is `subanalysis.decision1.a`."""
    reference = parse_option_reference("subanalysis.decision1.a")
    assert (reference.decision, reference.option) == (Address(("subanalysis", "decision1")), "a")
