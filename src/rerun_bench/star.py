"""A one-time line asking for a GitHub star, shown once per machine and never in automation.

The line is printed to stderr after the first successful report a person sees in a terminal.
Whether it was shown is stored as a marker file in the user state directory. Nothing is sent
anywhere. It is never shown when:

- ``RERUN_BENCH_NO_STAR_PROMPT`` is set to anything but ``""``, ``0`` or ``false``;
- a CI environment variable is set (``CI``, ``GITHUB_ACTIONS``, ``GITLAB_CI`` and others);
- stdout or stderr is not a terminal (piped, redirected, or run by a tool);
- the output is JSON (``report --format json``) or ``run --quiet``;
- the marker file exists, or cannot be created (so it can never repeat).
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import __version__

MESSAGE = (
    "If rerun-bench was useful, a star on GitHub helps others find it: "
    "https://github.com/Abelo9996/rerun-bench"
)
OPT_OUT_ENV = "RERUN_BENCH_NO_STAR_PROMPT"
STATE_DIR_ENV = "RERUN_BENCH_STATE_DIR"
MARKER = "star-prompt-shown"

# Set by the CI systems that use them. Any non-empty value other than "0" or "false" counts.
CI_ENV_VARS = (
    "CI",
    "CONTINUOUS_INTEGRATION",
    "GITHUB_ACTIONS",
    "GITLAB_CI",
    "BUILDKITE",
    "CIRCLECI",
    "TRAVIS",
    "JENKINS_URL",
    "TEAMCITY_VERSION",
    "TF_BUILD",
    "BITBUCKET_BUILD_NUMBER",
    "CODEBUILD_BUILD_ID",
    "APPVEYOR",
    "DRONE",
    "SEMAPHORE",
)


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() not in ("", "0", "false", "no")


def state_dir() -> Path:
    """Per-user state directory, following the platformdirs ``user_state_dir`` layout."""
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "rerun-bench"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "rerun-bench"
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "rerun-bench"


def in_ci(environ=None) -> bool:
    env = os.environ if environ is None else environ
    return any(_truthy(env.get(name)) for name in CI_ENV_VARS)


def _interactive() -> bool:
    try:
        return sys.stdout.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def suppressed() -> bool:
    return _truthy(os.environ.get(OPT_OUT_ENV)) or in_ci() or not _interactive()


def maybe_show() -> bool:
    """Print the line once per machine if allowed. Returns whether it was printed."""
    if suppressed():
        return False
    marker = state_dir() / MARKER
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        # "x" fails if the file exists, so two processes cannot both show it.
        with open(marker, "x", encoding="utf-8") as fh:
            stamp = datetime.now(UTC).strftime("%Y-%m-%d")
            fh.write(f"shown {stamp} by rerun-bench {__version__}\n")
    except OSError:
        return False
    print(f"\n{MESSAGE}", file=sys.stderr)
    return True
