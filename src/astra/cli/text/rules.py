"""The rule catalogue as text."""

from __future__ import annotations

from collections.abc import Iterable

from rich.console import Console
from rich.text import Text

from astra.cli.text import console
from astra.diagnostics import OWN, Catalogue, Rule

LAYERS = ("parse", "schema", "validator", "check", "runner")


def show_rules(catalogue: Catalogue) -> None:
    """`rules.json`'s rules by layer, then astra-tools' own."""
    out = console()
    for layer in LAYERS:
        _section(out, layer, (rule for rule in catalogue.rules.values() if rule.layer == layer))
    for layer in LAYERS:
        own = [rule for rule in OWN.values() if rule.layer == layer]
        if own:
            _section(out, f"{layer}, astra-tools' own", own)


def _section(out: Console, heading: str, rules: Iterable[Rule]) -> None:
    out.print(Text(heading, style="bold underline"))
    for rule in rules:
        out.print(Text.assemble("  ", (rule.code, "bold"), f" {rule.level} {rule.statement}"))
    out.print()


def show_rule(rule: Rule) -> None:
    out = console()
    out.print(Text(rule.code, style="bold"))
    where = f"{rule.layer}, {rule.level}"
    out.print(Text(where if rule.source is None else f"{where}, {rule.source}"))
    out.print(Text(rule.statement))
    if rule.status is not None:
        out.print(Text(f"Status when broken: {rule.status}"))
