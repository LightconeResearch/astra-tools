"""`astra spec [TERM] [--full]`: the field reference, through LinkML."""

from __future__ import annotations

import click

from astra.cli import FAILED


@click.command("spec")
@click.argument("term", required=False)
@click.option("--full", is_flag=True, help="Dump the entire reference (very long).")
def command(term: str | None, full: bool) -> None:
    """Describe the fields of ASTRA files.

    Without TERM, every class, enum and type, each with its first sentence. With TERM,
    whatever its case, a class, enum or type in full, a field of every class that has it, or
    Class.field. --full shows every class, enum and type in full (very long). Exits 1 for a
    TERM that names nothing.
    """
    from astra.cli.text.spec import show_summary, show_terms
    from astra.reference import load_reference, lookup

    if full and term is not None:
        raise click.UsageError("--full dumps every entry; drop TERM or drop --full.")
    terms = load_reference()
    if full:
        show_terms(terms)
        return
    if term is None:
        show_summary(terms)
        return
    found = lookup(terms, term)
    if not found:
        click.echo(f"Unknown term: {term}")
        click.echo("Valid terms: " + ", ".join(t.name for t in terms))
        raise click.exceptions.Exit(FAILED)
    show_terms(found)
