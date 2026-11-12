"""The forms of a name: parse and format.

```abnf
id               = lower *( lower / DIGIT / "_" )
address          = id *( "." id )               ; [declaration "."]... element
reference        = address [ "#" id ]           ; "#" pins a universe
option-reference = address "." id              ; a decision's address, then an option id
```

Binding parses only what the schema accepted, which takes its form (`INVALID_REFERENCE`), so a
value is parsed by splitting it. An address formats as it is written, through `str()`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Address:
    """Ids joined by `.`: the ids of the declarations that lead to an element, then its own."""

    segments: tuple[str, ...]

    @property
    def declarations(self) -> tuple[str, ...]:
        """Every segment but the last: the ids of the declarations the address goes through."""
        return self.segments[:-1]

    @property
    def id(self) -> str:
        """The last segment: the id of the element in the analysis reached."""
        return self.segments[-1]

    def __str__(self) -> str:
        return ".".join(self.segments)


@dataclass(frozen=True)
class Reference:
    """An address, which may be followed by a pin, `#` and a universe's id."""

    address: Address
    pin: str | None = None


@dataclass(frozen=True)
class OptionReference:
    """A decision's address, `.`, then an option's id: the last segment is always the option."""

    decision: Address
    option: str


def parse_address(text: str) -> Address:
    return Address(tuple(text.split(".")))


def parse_reference(text: str) -> Reference:
    address, hash_, pin = text.partition("#")
    return Reference(parse_address(address), pin if hash_ else None)


def parse_option_reference(text: str) -> OptionReference:
    address = parse_address(text)
    return OptionReference(Address(address.declarations), address.id)
