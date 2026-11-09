"""`docs/cli.md`, the CLI reference that astra-spec.org shows, against the commands themselves:
a section for each command and none for any other, and in each section every subcommand and
every option the command takes."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import click
import pytest

from astra.cli import COMMANDS, main

CLI_MD = Path(__file__).parents[1] / "docs" / "cli.md"


def sections() -> dict[str, str]:
    """The text of each section headed ``## `astra <command>` ``, by command."""
    found: dict[str, str] = {}
    name: str | None = None
    for line in CLI_MD.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            match = re.fullmatch(r"## `astra ([a-z]+)`", line)
            name = match[1] if match else None
            if name is not None:
                found[name] = ""
        elif name is not None:
            found[name] += line + "\n"
    return found


def walk(path: str, command: click.Command) -> Iterator[tuple[str, click.Command]]:
    """`command`, named `path`, and each of its subcommands, each with its whole name."""
    yield path, command
    if isinstance(command, click.Group):
        context = click.Context(command)
        for name in command.list_commands(context):
            subcommand = command.get_command(context, name)
            assert subcommand is not None
            yield from walk(f"{path} {name}", subcommand)


def options(command: click.Command) -> list[str]:
    """The long options `command` takes, `--help` aside."""
    return [
        opt
        for param in command.params
        if isinstance(param, click.Option)
        for opt in param.opts
        if opt.startswith("--")
    ]


def test_a_section_for_each_command_and_no_other() -> None:
    assert set(sections()) == set(COMMANDS)


@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_each_section_names_its_subcommands_and_options(name: str) -> None:
    text = sections()[name]
    command = main.get_command(click.Context(main), name)
    assert command is not None
    for path, each in walk(name, command):
        assert f"astra {path}" in text, f"`astra {path}` isn't in the section of `astra {name}`"
        for option in options(each):
            assert option in text, f"`astra {path} {option}` isn't in the section of `astra {name}`"
