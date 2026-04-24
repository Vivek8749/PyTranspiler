"""
Type system for the Python-to-C++ transpiler.

Defines the internal type representations, Python-to-C++ type mappings,
type promotion rules, and operator mappings.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


# ---------------------------------------------------------------------------
# Internal type representations
# ---------------------------------------------------------------------------

class BaseType(Enum):
    """Primitive type kinds recognised by the transpiler."""
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    BOOL = auto()
    VOID = auto()
    LIST = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class PyType:
    """
    Represents a resolved type in the transpiler's type system.

    For primitive types, `inner` is None.
    For LIST types, `inner` holds the element type (e.g., LIST<INT>).
    """
    base: BaseType
    inner: Optional["PyType"] = None

    # Convenience singletons (constructed after the class body)
    def __repr__(self) -> str:
        if self.base == BaseType.LIST and self.inner is not None:
            return f"list[{self.inner}]"
        return self.base.name.lower()


# Singleton type constants for convenience
INT = PyType(BaseType.INT)
FLOAT = PyType(BaseType.FLOAT)
STRING = PyType(BaseType.STRING)
BOOL = PyType(BaseType.BOOL)
VOID = PyType(BaseType.VOID)
UNKNOWN = PyType(BaseType.UNKNOWN)


def LIST_OF(element_type: PyType) -> PyType:
    """Create a list type with the given element type."""
    return PyType(BaseType.LIST, inner=element_type)


# ---------------------------------------------------------------------------
# Python → C++ type mapping
# ---------------------------------------------------------------------------

CPP_TYPE_MAP: dict[PyType, str] = {
    INT: "int",
    FLOAT: "double",
    STRING: "std::string",
    BOOL: "bool",
    VOID: "void",
}


def to_cpp_type(py_type: PyType) -> str:
    """Convert an internal PyType to its C++ string representation."""
    if py_type.base == BaseType.LIST and py_type.inner is not None:
        return f"std::vector<{to_cpp_type(py_type.inner)}>"
    if py_type in CPP_TYPE_MAP:
        return CPP_TYPE_MAP[py_type]
    raise ValueError(f"Cannot map type {py_type} to C++")


# ---------------------------------------------------------------------------
# Headers required by each type
# ---------------------------------------------------------------------------

REQUIRED_HEADERS: dict[BaseType, str] = {
    BaseType.STRING: "<string>",
    BaseType.LIST: "<vector>",
}


def headers_for_type(py_type: PyType) -> set[str]:
    """Return the set of C++ headers required to use *py_type*."""
    headers: set[str] = set()
    if py_type.base in REQUIRED_HEADERS:
        headers.add(REQUIRED_HEADERS[py_type.base])
    if py_type.base == BaseType.LIST and py_type.inner is not None:
        headers |= headers_for_type(py_type.inner)
    return headers


# ---------------------------------------------------------------------------
# Type promotion rules
# ---------------------------------------------------------------------------

# When two operands are combined, the result is promoted according to this
# table (order matters — first match wins).
_PROMOTION_RULES: list[tuple[tuple[BaseType, BaseType], BaseType]] = [
    # (left, right) → result   (both orderings are checked)
    ((BaseType.INT, BaseType.INT), BaseType.INT),
    ((BaseType.FLOAT, BaseType.FLOAT), BaseType.FLOAT),
    ((BaseType.INT, BaseType.FLOAT), BaseType.FLOAT),
    ((BaseType.FLOAT, BaseType.INT), BaseType.FLOAT),
    ((BaseType.BOOL, BaseType.INT), BaseType.INT),
    ((BaseType.INT, BaseType.BOOL), BaseType.INT),
    ((BaseType.BOOL, BaseType.BOOL), BaseType.INT),
    ((BaseType.STRING, BaseType.STRING), BaseType.STRING),
]


def promote(left: PyType, right: PyType) -> Optional[PyType]:
    """
    Return the promoted type when *left* and *right* are combined in an
    arithmetic or concatenation expression.  Returns None if the combination
    is invalid.
    """
    pair = (left.base, right.base)
    for accepted, result in _PROMOTION_RULES:
        if pair == accepted:
            return PyType(result)
    return None


# ---------------------------------------------------------------------------
# Operator mappings  (Python AST operator → C++ operator string)
# ---------------------------------------------------------------------------

import ast  # noqa: E402  (kept at bottom to avoid circular concerns)

BINOP_MAP: dict[type, str] = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.Mod: "%",
    ast.FloorDiv: "/",   # integer division in C++ for int operands
    ast.Pow: "pow",      # special-cased in codegen (needs <cmath>)
}

UNARYOP_MAP: dict[type, str] = {
    ast.UAdd: "+",
    ast.USub: "-",
    ast.Not: "!",
}

BOOLOP_MAP: dict[type, str] = {
    ast.And: "&&",
    ast.Or: "||",
}

CMPOP_MAP: dict[type, str] = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

AUGASSIGN_MAP: dict[type, str] = {
    ast.Add: "+=",
    ast.Sub: "-=",
    ast.Mult: "*=",
    ast.Div: "/=",
    ast.Mod: "%=",
}
