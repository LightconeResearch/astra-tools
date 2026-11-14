"""`astra spec [TERM] [--full]`: the schema as reference text, through LinkML."""

from __future__ import annotations

import click

from astra.cli import FAILED


@click.command("spec")
@click.argument("term", required=False)
@click.option("--full", is_flag=True, help="Dump the entire reference (VERY long).")
def command(term: str | None, full: bool) -> None:
    """Render the ASTRA schema as agent-friendly reference text.

    No args prints a concept summary; TERM prints one entry (case-insensitive);
    --full concatenates every entry (VERY long).
    """
    from astra import spec_render

    if full and term:
        raise click.UsageError("--full dumps every entry; drop TERM or drop --full.")
    if full:
        click.echo(spec_render.render_full(), nl=False)
        return
    if term:
        rendered = spec_render.render_term(term)
        if not rendered:
            click.echo(f"Unknown term: {term}")
            click.echo("Valid terms: " + ", ".join(spec_render.list_terms()))
            raise click.exceptions.Exit(FAILED)
        click.echo(rendered, nl=False)
        return
    click.echo(spec_render.render_summary())
