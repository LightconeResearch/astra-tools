"""§11 Recipes: every brace of a recipe's `command` belongs to a `{{`, a `}}` or a placeholder,
and every placeholder is one its output gives (`UNDECLARED_TEMPLATE_REF`).

The command is read from the left, as §11 *The command as a template* says: `{{` is a literal
`{` and `}}` a literal `}`, and any other `{` opens a placeholder, which ends at the next `}`.
A placeholder is `{inputs}`, `{output}`, or `{inputs.<entry>}` or `{decisions.<entry>}` for an
entry of the output's `inputs` or `decisions` exactly as written.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from astra import model
from astra.diagnostics import Diagnostic
from astra.rules.context import Context

CODES = frozenset({"UNDECLARED_TEMPLATE_REF"})


def check(context: Context) -> Iterator[Diagnostic]:
    for member, analysis in context.stack.determined():
        for id_, output in analysis.outputs.items():
            at = context.at(member.identity, ("outputs", id_, "recipe", "command"))
            for problem in _problems(output):
                yield context.diagnostic("UNDECLARED_TEMPLATE_REF", problem, at)


_BRACES = re.compile(r"\{\{|\}\}|\{[^}]*\}|\{|\}")
"""Read from the left: `{{`, `}}`, a placeholder up to the next `}`, or a stray brace."""


def _problems(output: model.Output) -> Iterator[str]:
    """What is wrong with `output`'s command as a template, one problem at a time."""
    for brace in _BRACES.finditer(output.recipe.command):
        text, at = brace[0], brace.start() + 1
        if text == "}":
            yield f"the `}}` at character {at} ends no placeholder: write `}}}}` for `}}`"
        elif text == "{":
            yield f"the `{{` at character {at} opens a placeholder that never ends"
            return
        elif text not in ("{{", "}}") and not _gives(output, text[1:-1]):
            yield f"`{text}` isn't a placeholder of this output: {_FORMS}"


_FORMS = (
    "it takes `{inputs}`, `{output}`, and `{inputs.<entry>}` and `{decisions.<entry>}` for an "
    "entry of its `inputs` or `decisions` as written; `{{` and `}}` are literal braces"
)


def _gives(output: model.Output, placeholder: str) -> bool:
    """Whether `placeholder`, between its braces, is one of `output`'s (§11's table)."""
    if placeholder in ("inputs", "output"):
        return True
    field, dot, entry = placeholder.partition(".")
    if field == "inputs" and dot:
        return entry in output.inputs
    if field == "decisions" and dot:
        return entry in output.decisions
    return False
