"""`astra spec [TERM]`: the field reference, through LinkML."""

from __future__ import annotations

import click


@click.command("spec")
@click.argument("term", required=False)
def command(term: str | None) -> None:
    """Describe the fields of ASTRA files.

    Without TERM, every class, enum and type, each with its first sentence. With TERM,
    whatever its case, a class, enum or type in full, a field of every class that has it, or
    Class.field.
    """
    from astra.cli.text.spec import show_summary, show_terms
    from astra.reference import load_reference, lookup

    terms = load_reference()
    if term is None:
        show_summary(terms)
        return
    found = lookup(terms, term)
    if not found:
        raise click.BadParameter(
            f"no class, enum, type or field is named {term}", param_hint="TERM"
        )
    show_terms(found)
