"""The rule catalogue as text."""

from __future__ import annotations

from rich.text import Text

from astra.cli.text import console
from astra.diagnostics import Catalogue, Rule

LAYERS = ("parse", "schema", "validator", "check", "runner")


def show_rules(catalogue: Catalogue) -> None:
    out = console()
    for layer in LAYERS:
        out.print(Text(layer, style="bold underline"))
        for code in catalogue.codes(layer):
            rule = catalogue.rules[code]
            out.print(Text.assemble("  ", (code, "bold"), f" {rule.level} {rule.statement}"))
        out.print()


def show_rule(rule: Rule) -> None:
    out = console()
    out.print(Text(rule.code, style="bold"))
    out.print(Text(f"{rule.layer}, {rule.level}, {rule.source}"))
    out.print(Text(rule.statement))
    if rule.status is not None:
        out.print(Text(f"Status when broken: {rule.status}"))
