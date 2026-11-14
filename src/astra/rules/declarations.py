"""Declared analyses: a declaration's `path` stays inside the repository
(`DECLARATION_OUTSIDE_REPOSITORY`) and names a folder holding an `astra.yaml` file, reached
through no symlink (`MISSING_DECLARED_ANALYSIS`); no output shares its id with a declaration of
its analysis (`CLASHING_RESULT_NAME`).

A declaration whose analysis can't be got isn't checked by `MISSING_DECLARED_ANALYSIS`:
binding gives each declaration one outcome (`astra.stack.Outcome`). With a `commit`, the folder
is read at that commit, and measured from the top of the repository that holds it; with a
`url`, it is the top of that repository.
"""

from __future__ import annotations

from collections.abc import Iterator

from astra.diagnostics import Diagnostic
from astra.rules.context import Context

CODES = frozenset(
    {"DECLARATION_OUTSIDE_REPOSITORY", "MISSING_DECLARED_ANALYSIS", "CLASHING_RESULT_NAME"}
)


def check(context: Context) -> Iterator[Diagnostic]:
    for member, analysis in context.stack.determined():
        for declaration in member.declarations.values():
            path, commit = declaration.declared.path, declaration.declared.commit
            field = "url" if path is None else "path"
            at = context.at(member.identity, ("analyses", declaration.id, field))
            if path is not None and declaration.folder is None:
                top = "working tree" if commit is None else f"tree at `{commit}`"
                message = (
                    f"`{path}` goes above the top of the repository's {top}: declare an "
                    "analysis of another repository by its `url` and a `commit`"
                )
                yield context.diagnostic("DECLARATION_OUTSIDE_REPOSITORY", message, at)
            elif declaration.outcome == "missing":
                url = declaration.declared.url
                folder = (
                    f"the folder `{declaration.folder or '.'}`" if path else f"the top of `{url}`"
                )
                message = (
                    f"{folder}{'' if commit is None else f' at `{commit}`'} holds no astra.yaml "
                    "file (a symlink, or a path through one, is never followed)"
                )
                yield context.diagnostic("MISSING_DECLARED_ANALYSIS", message, at)
        for id_ in analysis.outputs:
            if id_ in analysis.analyses:
                message = (
                    f"the output `{id_}` shares its id with a declaration, so their results' "
                    "places could be the same: rename one"
                )
                output = context.at(member.identity, ("outputs",), id_)
                declared = context.at(member.identity, ("analyses",), id_)
                yield context.diagnostic("CLASHING_RESULT_NAME", message, output, [declared])
