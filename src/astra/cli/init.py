"""`astra init [DIR]`: a minimal analysis, in a new git repository (design §4.12)."""

from __future__ import annotations

from pathlib import Path

import click

from astra.cli import fail


@click.command("init")
@click.argument("folder", metavar="[DIR]", required=False, type=click.Path(path_type=Path))
def command(folder: Path | None) -> None:
    """Make a minimal analysis in DIR.

    DIR is the analysis's folder, the current one by default, made if need be. Its astra.yaml
    has a spec_version and one output. Where no git repository holds DIR, it becomes a new
    one. Exits 2 where DIR has an astra.yaml already.
    """
    from astra import api
    from astra.sources.git import GitError

    try:
        file, made = api.init(folder)
    except (FileExistsError, GitError) as error:
        fail(str(error))
    except OSError as error:
        fail(f"can't write {error.filename}: {error.strerror}")
    where = "in a new git repository" if made else "in the git repository that holds it"
    click.echo(f"Made {file}, {where}.")
    click.echo(f"Check it with: astra validate {file.parent}")
