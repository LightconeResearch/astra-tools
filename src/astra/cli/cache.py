"""`astra cache path|clear`: where the cache is, and clearing it (design §4.9)."""

from __future__ import annotations

import click

from astra.cli import fail


@click.group("cache")
def command() -> None:
    """Show or clear the cache.

    The cache keeps the commits fetched from remotes, the validity of analyses from a commit,
    the hashes of files and the checkouts runners make for their runs, outside every repository.
    Everything in it is safe to delete.
    ASTRA_CACHE_DIR, an absolute path, moves it.
    """


@command.command("path")
def path() -> None:
    """Print the cache's folder."""
    from astra import cache

    try:
        click.echo(cache.root())
    except cache.CacheError as error:
        fail(str(error))


@command.command("clear")
def clear() -> None:
    """Delete what astra keeps in the cache.

    Only the folders astra keeps there are deleted; anything else in the cache's folder is
    left alone.
    """
    from astra import cache

    try:
        folder = cache.clear()
    except cache.CacheError as error:
        fail(str(error))
    click.echo(f"Cleared the cache in {folder}.")
