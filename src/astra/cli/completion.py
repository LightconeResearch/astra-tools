"""`astra completion SHELL`: the script with which a shell completes astra's commands."""

from __future__ import annotations

import click
from click.shell_completion import get_completion_class


@click.command("completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
@click.pass_context
def command(ctx: click.Context, shell: str) -> None:
    """Print the shell completion script.

    Load the script for SHELL from the shell's startup file:

    \b
      bash, in ~/.bashrc:                  eval "$(astra completion bash)"
      zsh, in ~/.zshrc:                    eval "$(astra completion zsh)"
      fish, in ~/.config/fish/config.fish: astra completion fish | source
    """
    root = ctx.find_root()
    completion = get_completion_class(shell)
    assert completion is not None  # click has each of the three
    click.echo(completion(root.command, {}, "astra", "_ASTRA_COMPLETE").source())
