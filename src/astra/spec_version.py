"""The installed astra-spec version.

Its own module, importing stdlib only, so callers that just need the
version string are not forced through the validation stack — see
:mod:`astra.scaffold`. Re-exported from :mod:`astra.validation` for
backward compatibility.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version


def installed_spec_version() -> str | None:
    """Return the installed ``astra-spec`` package version, or None if unknown."""
    try:
        return _pkg_version("astra-spec")
    except PackageNotFoundError:
        return None
