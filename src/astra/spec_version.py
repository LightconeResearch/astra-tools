"""The installed astra-spec version.

Its own module, importing nothing at all, so callers that just need the
version string are not forced through the validation stack — see
:mod:`astra.scaffold`. Re-exported from :mod:`astra.validation` for
backward compatibility.
"""

from __future__ import annotations


def installed_spec_version() -> str | None:
    """Return the installed ``astra-spec`` package version, or None if unknown."""
    # `importlib.metadata` costs ~13 ms and drags in email, inspect and
    # zipfile behind it. Asking for the version pays that; importing a
    # module that could ask for it does not.
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("astra-spec")
    except PackageNotFoundError:
        return None
