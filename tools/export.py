#!/usr/bin/env python3
"""Deterministic exporter: catalog + locales → dist/."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from i18nlib import export_dist, validate_catalog, write_dist


def default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export i18n catalog into dist/")
    parser.add_argument("--root", type=Path, default=default_root())
    parser.add_argument(
        "--check",
        action="store_true",
        help="export in memory and require dist/ to already match byte-for-byte",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    errors = validate_catalog(root)
    if errors:
        for error in errors:
            print("i18n validate:", error, file=sys.stderr)
        return 1
    files = export_dist(root)
    if args.check:
        mismatched = []
        for relative, data in files.items():
            path = root / "dist" / relative
            if not path.is_file() or path.read_bytes() != data:
                mismatched.append(relative)
        extra = []
        dist = root / "dist"
        if dist.exists():
            for existing in dist.rglob("*"):
                if existing.is_file():
                    rel = existing.relative_to(dist).as_posix()
                    if rel.startswith(("generated/", "translations/", "dialogue/", "chronicle/")) and rel not in files:
                        extra.append(rel)
        if mismatched or extra:
            for item in mismatched:
                print(f"dist drift: {item}", file=sys.stderr)
            for item in extra:
                print(f"dist extra: {item}", file=sys.stderr)
            return 1
        print(f"dist is clean ({len(files)} files)")
        return 0
    written = write_dist(root)
    print(f"exported {len(written)} dist files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
