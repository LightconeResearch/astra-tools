"""The field reference as text."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import console
from astra.reference import Term

_HEADINGS = (("class", "Classes"), ("enum", "Enums"), ("type", "Types"))


def show_summary(terms: tuple[Term, ...]) -> None:
    out = console()
    for kind, heading in _HEADINGS:
        out.print(Text(heading, style="bold underline"))
        for term in terms:
            if term.kind == kind:
                first = term.description.split(". ")[0].rstrip(".")
                out.print(Text.assemble("  ", (term.name, "bold"), f" {first}"))
        out.print()


def show_terms(terms: tuple[Term, ...]) -> None:
    out = console()
    for term in terms:
        out.print(Text.assemble((term.name, "bold"), f" ({term.kind})"))
        if term.description:
            out.print(Text(term.description))
        if term.pattern is not None:
            out.print(Text(f"Pattern: {term.pattern}"))
        for name, description in term.values:
            out.print(Text.assemble("  ", (name, "bold"), f" {description}"))
        for field in term.fields:
            flags = ", ".join(
                flag
                for flag, on in (("required", field.required), ("a list", field.multivalued))
                if on
            )
            kind = f"{field.range}, {flags}" if flags else field.range
            out.print(Text.assemble("  ", (field.name, "bold"), f" ({kind}) {field.description}"))
        out.print()
