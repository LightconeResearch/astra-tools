"""`astra rules [CODE]`: the rule catalogue, `rules.json` (Annex E)."""

from __future__ import annotations

import click


@click.command("rules")
@click.argument("code", required=False)
def command(code: str | None) -> None:
    """List the specification's rules, or show one.

    Without CODE, every rule, by layer, with its code, level and statement. With CODE, whatever
    its case, that rule, with its section and, for a check rule, its status when broken.
    """
    from astra.cli.text.rules import show_rule, show_rules
    from astra.diagnostics import Catalogue

    catalogue = Catalogue.load()
    if code is None:
        show_rules(catalogue)
        return
    rule = catalogue.rules.get(code.upper())
    if rule is None:
        raise click.BadParameter(f"no rule has the code {code}", param_hint="CODE")
    show_rule(rule)
