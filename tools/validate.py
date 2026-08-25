#!/usr/bin/env python3
"""Validate the i18n catalog, locales, and uniqueness/token/structure contracts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from i18nlib import validate_catalog


def default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def is_dialogue_authoring_release_blocker(error: str) -> bool:
    """Return true for dialogue states that are valid while authoring, but not for release."""
    _, separator, message = error.partition(": ")
    return bool(separator) and (
        message.startswith("draft dialogue candidate ")
        or (
            message.startswith("stale dialogue turn ")
            and not message.startswith("stale dialogue turn exception ")
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate oni-ai-social-i18n catalog")
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument(
        "--allow-dialogue-authoring",
        action="store_true",
        help="allow draft/stale dialogue entries while retaining all structural checks",
    )
    args = parser.parse_args()
    errors = validate_catalog(args.root.resolve())
    if args.allow_dialogue_authoring:
        errors = [error for error in errors if not is_dialogue_authoring_release_blocker(error)]
    if errors:
        for error in errors:
            print("i18n validate:", error, file=sys.stderr)
        return 1
    print("i18n catalog ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
