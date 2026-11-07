"""`astra spec [TERM]`: the field reference, through LinkML (extra [reference])."""

from __future__ import annotations

import click

from astra.cli import fail


@click.command("spec")
@click.argument("term", required=False)
def command(term: str | None) -> None:
    """Describe the fields of ASTRA files.

    It needs the [reference] extra. Without TERM, every class, enum and type, each with its
    first sentence. With TERM, whatever its case, a class, enum or type in full, a field of
    every class that has it, or Class.field.
    """
    from astra.cli.text.spec import show_summary, show_terms
    from astra.reference import ReferenceUnavailable, load_reference, lookup

    try:
        terms = load_reference()
    except ReferenceUnavailable as error:
        fail(str(error))
    if term is None:
        show_summary(terms)
        return
    found = lookup(terms, term)
    if not found:
        raise click.BadParameter(
            f"no class, enum, type or field is named {term}", param_hint="TERM"
        )
    show_terms(found)
