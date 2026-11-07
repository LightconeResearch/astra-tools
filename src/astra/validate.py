"""validate(): the validator's report on an analysis (§3, design §4.11).

Phase 0 reads the root's `astra.yaml` alone: the parse and schema rules (§5, Annex A, Annex E),
`UNSUPPORTED_SPEC_VERSION`, and `NOT_IN_REPOSITORY`. It follows no declaration. The validator
codes it doesn't check yet are listed in the report as `unchecked`.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Any

from astra import contract, load
from astra.contract import Contract
from astra.diagnostics import Catalogue, Diagnostic, Location
from astra.load import ParseError, load_yaml
from astra.sources.reader import Reader

SHAPE = "astra-validation-report/1"

CODES = frozenset({"NOT_IN_REPOSITORY"})
"""The validator codes checked here, beside those `load` and `contract` report."""


@dataclass(frozen=True)
class ValidationReport:
    """What validating an analysis found."""

    root: str  # the root's astra.yaml, as a Location's `file` names it
    diagnostics: tuple[Diagnostic, ...]
    unchecked: tuple[str, ...]  # the validator codes this build doesn't check yet

    @property
    def valid(self) -> bool:
        """True when no `MUST` is broken: warnings and `unchecked` notwithstanding (§3)."""
        return all(diagnostic.level != "error" for diagnostic in self.diagnostics)

    def to_json(self) -> dict[str, Any]:
        """The report as `astra-validation-report/1` (design §4.11)."""
        # OPEN(O10): the exact JSON form.
        return {
            "shape": SHAPE,
            "root": self.root,
            "valid": self.valid,
            "diagnostics": [diagnostic.to_json() for diagnostic in self.diagnostics],
            "unchecked": list(self.unchecked),
        }


def unchecked(catalogue: Catalogue) -> tuple[str, ...]:
    """The validator codes of the catalogue that no check of this build reports."""
    checked = load.CODES | contract.CODES | CODES
    return tuple(code for code in catalogue.codes("validator") if code not in checked)


def validate(reader: Reader, root: str) -> ValidationReport:
    """The report on the analysis whose folder is `root` in `reader` ("" for its top), which
    holds its `astra.yaml`. Raises OSError if that can't be read."""
    file = posixpath.join(root, "astra.yaml")
    catalogue = Catalogue.load()
    try:
        document = load_yaml(reader.read(file))
    except ParseError as error:
        # Annex D case 1: a file that can't be read is checked no further.
        location = Location(file, "", error.line, error.column)
        found = [catalogue.diagnostic(error.code, error.message, location)]
    else:
        found = list(Contract.load(catalogue).check_analysis(document, file))
        # Annex D case 2: a file that isn't a valid document isn't checked by the validator
        # layer, NOT_IN_REPOSITORY included. OPEN(O6), OPEN(O8)
        if not found and reader.repo is None:
            message = (
                "the analysis's folder isn't in the working tree of a git repository: "
                "make one with `git init`, or move the analysis into one"
            )
            location = Location(file, "", None, None)
            found.append(catalogue.diagnostic("NOT_IN_REPOSITORY", message, location))
    diagnostics = sorted(
        found,
        key=lambda d: (d.location.file, d.location.line or 0, d.location.column or 0, d.code),
    )
    return ValidationReport(file, tuple(diagnostics), unchecked(catalogue))
