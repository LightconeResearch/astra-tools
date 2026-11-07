"""Paths, tidied as text, never through the file system (Annex B).

A path is measured from the top of the root's working tree or, at a commit, from the top of the
repository read: segments joined by `/`, and "" for the top itself.
"""

from __future__ import annotations


def join(folder: str, path: str) -> str | None:
    """`path`, written in the `astra.yaml` of `folder`, joined to it and tidied: empty and `.`
    segments dropped, and each `..` removing the segment before it. None where a `..` goes
    above the top."""
    segments: list[str] = []
    for segment in [*folder.split("/"), *path.split("/")]:
        if segment == "..":
            if not segments:
                return None
            segments.pop()
        elif segment not in ("", "."):
            segments.append(segment)
    return "/".join(segments)


def lies_inside(path: str, folder: str) -> bool:
    """Whether the tidied `path` lies inside the tidied `folder`: the folder's segments begin
    the path's, and the path has more. `results/u1/output1.csv` lies inside `results`, and
    `results2/x.csv` doesn't."""
    return path.startswith(folder + "/") if folder else path != ""
