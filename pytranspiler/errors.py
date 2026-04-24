"""
Custom error types for the transpiler.

Every error carries the source line number (when available) so that the
CLI can produce developer-friendly diagnostics.
"""

from __future__ import annotations
from typing import Optional


class TranspilerError(Exception):
    """Base error for all transpiler-related failures."""

    def __init__(self, message: str, lineno: Optional[int] = None) -> None:
        self.lineno = lineno
        prefix = f"Line {lineno}: " if lineno else ""
        super().__init__(f"{prefix}{message}")


class TypeInferenceError(TranspilerError):
    """Raised when a variable or expression type cannot be determined."""
    pass


class TypeMismatchError(TranspilerError):
    """Raised when operand types are incompatible."""
    pass


class UnsupportedFeatureError(TranspilerError):
    """Raised when the source uses a Python feature the transpiler cannot handle."""
    pass


class ScopeError(TranspilerError):
    """Raised when a variable or function is referenced out of scope."""
    pass
