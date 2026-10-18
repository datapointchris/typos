import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import distribution
from importlib.metadata import version as installed_version


def tool_version() -> str:
    """This build's version, or 'unknown' from a source checkout.

    The git tag is the version. uv-dynamic-versioning stamps it into the build's
    metadata at install time, so it is read back from the installed distribution
    and nothing in the repository holds a copy that could fall behind the tag.

    A checkout that was never installed has no metadata and says so rather than
    inventing a number.
    """
    try:
        return installed_version('typos')
    except PackageNotFoundError:
        return 'unknown'


def installed_commit() -> str | None:
    """The commit a git install was built from, or None for any other install.

    uv records the resolved commit in the distribution's direct_url.json for every
    git install, a pinned tag included. A wheel from an index and an editable
    checkout record none.
    """
    try:
        recorded = distribution('typos').read_text('direct_url.json')
    except PackageNotFoundError:
        return None
    if not recorded:
        return None
    return json.loads(recorded).get('vcs_info', {}).get('commit_id')


__version__ = tool_version()
