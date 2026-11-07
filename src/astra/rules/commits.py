"""§17 Analyses from another commit or repository: a declaration's `commit` is one the repository
that holds the declaring file has (`COMMIT_NOT_FOUND`), and should be an ancestor of the commit
the declaration is in or, in the working tree, of HEAD (`COMMIT_NOT_ANCESTOR`); every commit the
stack gets from a remote can be got (`REMOTE_UNREACHABLE`); and an analysis from a commit, with
everything it declares, is valid at its commit (`DECLARED_ANALYSIS_INVALID`).

Binding has followed each declaration and kept what it reached (`astra.stack.Outcome`), and the
URL and commit that couldn't be got. A commit that can't be got is reported on the declaration
of the outermost analysis from a commit on the way to it, in a file of the root's own tree,
which the author can edit, once for each such declaration (§17 *Getting a commit from a
remote*). Annex D case 3: a declaration that breaks `COMMIT_NOT_FOUND`, or whose own commit
can't be got, isn't checked by `COMMIT_NOT_ANCESTOR`; one whose analysis can't be got, or on
the way through which a commit can't be got, isn't checked by `DECLARED_ANALYSIS_INVALID`, nor
is an analysis from a commit whose file breaks `UNSUPPORTED_SPEC_VERSION`.

A `MUST` that makes an analysis from a commit invalid is reported twice (§17 *What is read, and
validity*): `DECLARED_ANALYSIS_INVALID` on the declaration, and the rule's own code at its place
in the commit's file. Where the rule is one this root's pass finds too, `validate` reports it
once.
"""

from __future__ import annotations

import importlib.metadata
import json
from collections.abc import Iterator
from typing import Any

from astra import cache
from astra.diagnostics import Diagnostic, Location
from astra.rules.context import Context
from astra.sources.reader import CommitReader
from astra.stack import Declaration, Identity, Member, Stack

CODES = frozenset(
    {"COMMIT_NOT_FOUND", "COMMIT_NOT_ANCESTOR", "REMOTE_UNREACHABLE", "DECLARED_ANALYSIS_INVALID"}
)


def check(context: Context) -> Iterator[Diagnostic]:
    stack = context.stack
    for member, _ in stack.determined():
        editable = member.identity.commit == stack.root.commit  # the root's own tree
        for declaration in member.declarations.values():
            declared, id_ = declaration.declared, declaration.id
            if declared.commit is None:
                continue
            if declaration.outcome == "absent":
                message = (
                    f"the repository that holds this file has no commit `{declared.commit}`: "
                    "give a full id of one of its commits, or fetch the commit into it"
                )
                at = context.at(member.identity, ("analyses", id_, "commit"))
                yield context.diagnostic("COMMIT_NOT_FOUND", message, at)
                continue
            got = declaration.unreachable is None or declaration.unreachable[1] != declared.commit
            if declared.path is not None and got:  # its own commit was got
                yield from _ancestor(context, member, declaration)
            unreachable = _unreachable(stack, declaration)
            for url, commit in unreachable if editable else ():
                what = (
                    f"the commit `{commit}`"
                    if (url, commit) == declaration.unreachable
                    else f"`{id_}` leads to the commit `{commit}`, which"
                )
                where = f"from `{url}`" if url else "(`.gitmodules` gives its submodule no URL)"
                message = (
                    f"{what} can't be fetched {where}, and no earlier fetch kept it: check the "
                    "URL and the commit, and that git can reach the remote (with --offline, "
                    "nothing is fetched)"
                )
                at = context.at(member.identity, ("analyses", id_))
                yield context.diagnostic("REMOTE_UNREACHABLE", message, at)
            if not unreachable and declaration.reached is not None:
                yield from _invalid(context, member, declaration, declaration.reached)


def _ancestor(context: Context, member: Member, declaration: Declaration) -> Iterator[Diagnostic]:
    """`COMMIT_NOT_ANCESTOR`, in the repository that holds the declaring file: the declared
    commit is an ancestor of the one the declaration is in, or in the working tree of HEAD
    (Annex B *The repository that holds a file*)."""
    commit = declaration.declared.commit
    assert commit is not None
    holder, _ = member.reader.holding(member.identity.folder)
    descendant = member.identity.commit or holder.head()
    if descendant is None or holder.is_ancestor(commit, descendant):
        return
    where = "HEAD" if member.identity.commit is None else "the commit this file is in"
    message = (
        f"`{commit}` isn't an ancestor of {where}, `{descendant}`: declare a commit of this "
        "file's history, so that it can't be lost with another branch"
    )
    at = context.at(member.identity, ("analyses", declaration.id, "commit"))
    yield context.diagnostic("COMMIT_NOT_ANCESTOR", message, at)


def _unreachable(stack: Stack, declaration: Declaration) -> list[tuple[str | None, str]]:
    """The URLs and commits that can't be got on the way through `declaration`: its own
    analysis's, and those of the declarations of every analysis it leads to."""
    found = [] if declaration.unreachable is None else [declaration.unreachable]
    seen: set[Identity] = set()
    todo = [] if declaration.reached is None else [declaration.reached]
    while todo:
        identity = todo.pop()
        if identity not in seen:
            seen.add(identity)
            for inner in stack.analyses[identity].declarations.values():
                if inner.unreachable is not None and inner.unreachable not in found:
                    found.append(inner.unreachable)
                if inner.reached is not None:
                    todo.append(inner.reached)
    return found


def _invalid(
    context: Context, member: Member, declaration: Declaration, reached: Identity
) -> Iterator[Diagnostic]:
    """`DECLARED_ANALYSIS_INVALID` on `declaration`, with each `MUST` broken at its commit as a
    related place, and each of those `MUST`s at its place (§17). OPEN(O26): a `MUST` only this
    root's pass finds in the analysis's files adds no `DECLARED_ANALYSIS_INVALID`."""
    broken = _judged(context, context.stack.analyses[reached])
    if broken:
        codes = ", ".join(sorted({diagnostic.code for diagnostic in broken}))
        message = (
            f"`{declaration.id}` names an analysis that isn't valid at its commit: it breaks "
            f"{codes}, each reported at its place in that commit's files"
        )
        at = context.at(member.identity, ("analyses", declaration.id))
        related = [diagnostic.location for diagnostic in broken]
        yield context.diagnostic("DECLARED_ANALYSIS_INVALID", message, at, related)
        yield from broken


def _judged(context: Context, member: Member) -> tuple[Diagnostic, ...] | None:
    """The `MUST`s broken in the analysis from a commit `member`, with everything it declares,
    validated as its own root at its commit (§17 *What is read, and validity*). None where that
    isn't checked: where its file breaks `UNSUPPORTED_SPEC_VERSION` (Annex D case 3).

    Kept in the cache by the commit, unless the verdict rests on more than the files of the
    commits read: on a `COMMIT_NOT_FOUND`, which the local repository can come to have, or on a
    commit that couldn't be got, which a later fetch can get."""
    # OPEN(O1): judged as its own root, not by the MUSTs broken in its files under this root.
    from astra.validate import validate  # it runs these rules, so it is imported when used

    identity = member.identity
    version = importlib.metadata.version("astra-tools")
    key = json.dumps([version, context.catalogue.version, identity.folder, identity.commit])
    kept = cache.get("validity", key)
    if kept is not None:
        return tuple(_diagnostic(data) for data in json.loads(kept))
    reader = member.reader
    assert isinstance(reader, CommitReader)
    report = validate(reader, identity.folder, reader.remotes)
    if any(
        d.code == "UNSUPPORTED_SPEC_VERSION"
        and (d.location.file, d.location.commit) == (member.file, identity.commit)
        for d in report.diagnostics
    ):
        return None
    broken = tuple(d for d in report.diagnostics if d.level == "error")
    fixed = not reader.remotes.missed and all(d.code != "COMMIT_NOT_FOUND" for d in broken)
    if fixed:
        cache.put("validity", key, json.dumps([d.to_json() for d in broken]).encode())
    return broken


def _diagnostic(data: dict[str, Any]) -> Diagnostic:
    """A diagnostic kept in the cache, as `Diagnostic.to_json` gave it."""
    related = tuple(Location(**location) for location in data["related"])
    location = Location(**data["location"])
    return Diagnostic(data["code"], data["level"], data["message"], location, related)
