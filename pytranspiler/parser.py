"""
Parser module — thin wrapper around Python's built-in ``ast.parse``.

Reads a Python source file (or string), parses it into an AST, and
attaches the original source lines for error reporting.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional


class ParseResult:
    """Bundles the AST together with the original source lines."""

    def __init__(self, tree: ast.Module, source_lines: list[str], filename: str) -> None:
        self.tree = tree
        self.source_lines = source_lines
        self.filename = filename

    def get_line(self, lineno: int) -> Optional[str]:
        """Return the source line at *lineno* (1-indexed), or None."""
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1]
        return None


def parse_source(source: str, filename: str = "<string>") -> ParseResult:
    """Parse a Python source string and return a ``ParseResult``."""
    tree = ast.parse(source, filename=filename)
    source_lines = source.splitlines()
    return ParseResult(tree, source_lines, filename)


def parse_file(filepath: str | Path) -> ParseResult:
    """Read and parse a Python source file, returning a ``ParseResult``."""
    path = Path(filepath)
    source = path.read_text(encoding="utf-8")
    return parse_source(source, filename=str(path))
