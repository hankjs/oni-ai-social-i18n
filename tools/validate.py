#!/usr/bin/env python3
"""Validate the i18n catalog, locales, and uniqueness/token/structure contracts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from i18nlib import validate_catalog


def default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate oni-ai-social-i18n catalog")
    parser.add_argument("--root", type=Path, default=default_root())
    args = parser.parse_args()
    errors = validate_catalog(args.root.resolve())
    if errors:
        for error in errors:
            print("i18n validate:", error, file=sys.stderr)
        return 1
    print("i18n catalog ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
