from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version


def _tool_version() -> str:
    """This build's version, or 'unknown' from a source checkout.

    Read from the installed distribution rather than a constant here, so
    semantic-release owns the one copy in `pyproject.toml` and this cannot drift
    behind it. It had: `pyproject.toml` reached 1.0.0 while this said 0.1.0.

    A checkout that was never installed has no metadata and says so rather than
    inventing a number.
    """
    try:
        return installed_version('typos')
    except PackageNotFoundError:
        return 'unknown'


__version__ = _tool_version()
