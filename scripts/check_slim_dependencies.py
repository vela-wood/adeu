#!/usr/bin/env python3
"""Fail if this slim fork can install a forbidden agent framework."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(r"(?i)(?:fastmcp(?:-slim)?|langchain(?:[-_.][a-z0-9_.-]+)?)")
DEPENDENCY_FILES = (
    ROOT / "python" / "pyproject.toml",
    ROOT / "python" / "uv.lock",
    ROOT / "node" / "package.json",
    ROOT / "node" / "package-lock.json",
    *(ROOT / "node" / "packages").glob("*/package.json"),
)


def main() -> int:
    failures: list[str] = []
    if (ROOT / "langchain").exists():
        failures.append("langchain/ workspace exists")

    for path in DEPENDENCY_FILES:
        if not path.is_file():
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                failures.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")

    if failures:
        print("Forbidden slim-fork dependencies found:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1

    print("Slim dependency boundary passed: no forbidden packages in manifests or locks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
