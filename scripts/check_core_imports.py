#!/usr/bin/env python3
"""
Fail if core imports transport-specific modules.
Checks all Python files under src/openproject_mcp/core/.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = REPO_ROOT / "src" / "openproject_mcp" / "core"

FORBIDDEN_PREFIXES = (
    "fastapi",
    "starlette",
    "uvicorn",
    "mcp.server.fastmcp",
    "mcp.server",
    "fastmcp",
    "openproject_mcp.transports",
)


def is_forbidden(module: str) -> bool:
    return any(
        module == prefix or module.startswith(prefix + ".")
        for prefix in FORBIDDEN_PREFIXES
    )


def scan_file(path: Path) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if is_forbidden(mod):
                    errors.append(f"{path}: forbidden import '{mod}'")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod and is_forbidden(mod):
                errors.append(f"{path}: forbidden import '{mod}'")
    return errors


def main() -> int:
    violations: list[str] = []
    for py_file in CORE_DIR.rglob("*.py"):
        violations.extend(scan_file(py_file))

    if violations:
        for v in violations:
            print(v, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
