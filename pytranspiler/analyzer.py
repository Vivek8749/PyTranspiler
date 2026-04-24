"""
Semantic analyzer — builds symbol tables and infers types.

Walks the Python AST produced by the parser and:
  1. Builds a scoped symbol table (variable name → PyType).
  2. Infers types from annotations, literals, and expressions.
  3. Validates that all referenced names are in scope.
  4. Rejects unsupported Python constructs early.

The resulting ``AnalysisResult`` is consumed by the code generator.
"""

from __future__ import annotations

import ast
from typing import Optional

from .type_system import (
    PyType, BaseType,
    INT, FLOAT, STRING, BOOL, VOID, UNKNOWN, LIST_OF,
    promote,
)
from .errors import (
    TypeInferenceError,
    TypeMismatchError,
    UnsupportedFeatureError,
    ScopeError,
)


# ---------------------------------------------------------------------------
# Symbol Table (scope stack)
# ---------------------------------------------------------------------------

class SymbolTable:
    """
    A stack of scopes.  Each scope is a ``dict[str, PyType]``.

    The bottom scope is the *global* scope; new scopes are pushed when
    entering a function body and popped on exit.
    """

    def __init__(self) -> None:
        self._scopes: list[dict[str, PyType]] = [{}]  # global scope

    # -- scope management ---------------------------------------------------

    def push_scope(self) -> None:
        self._scopes.append({})

    def pop_scope(self) -> None:
        if len(self._scopes) <= 1:
            raise RuntimeError("Cannot pop the global scope")
        self._scopes.pop()

    # -- variable operations ------------------------------------------------

    def define(self, name: str, py_type: PyType) -> None:
        """Define (or redefine) *name* in the **current** scope."""
        self._scopes[-1][name] = py_type

    def lookup(self, name: str) -> Optional[PyType]:
        """Look up *name* starting from the innermost scope outward."""
        for scope in reversed(self._scopes):
            if name in scope:
                return scope[name]
        return None

    @property
    def current_scope(self) -> dict[str, PyType]:
        return self._scopes[-1]

    @property
    def depth(self) -> int:
        return len(self._scopes)


# ---------------------------------------------------------------------------
# Function signature registry
# ---------------------------------------------------------------------------

class FunctionSignature:
    """Stores a function's parameter types and return type."""

    def __init__(
        self,
        name: str,
        params: list[tuple[str, PyType]],
        return_type: PyType,
    ) -> None:
        self.name = name
        self.params = params           # [(param_name, param_type), …]
        self.return_type = return_type


# ---------------------------------------------------------------------------
# Analysis result (consumed by codegen)
# ---------------------------------------------------------------------------

class AnalysisResult:
    """Bundles everything the code generator needs."""

    def __init__(self) -> None:
        self.global_vars: dict[str, PyType] = {}
        self.functions: dict[str, FunctionSignature] = {}
        # node id → inferred PyType  (for every expression / assignment node)
        self.node_types: dict[int, PyType] = {}
        self.required_headers: set[str] = set()


# ---------------------------------------------------------------------------
# Annotation → PyType resolver
# ---------------------------------------------------------------------------

def _resolve_annotation(node: ast.expr) -> PyType:
    """
    Convert a type-annotation AST node into a ``PyType``.

    Supports: ``int``, ``float``, ``str``, ``bool``, ``list[T]``.
    """
    if isinstance(node, ast.Name):
        mapping = {"int": INT, "float": FLOAT, "str": STRING, "bool": BOOL}
        if node.id in mapping:
            return mapping[node.id]
        raise TypeInferenceError(
            f"Unknown type annotation '{node.id}'",
            lineno=getattr(node, "lineno", None),
        )

    # list[int], list[str], …
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Name) and node.value.id == "list":
            inner = _resolve_annotation(node.slice)
            return LIST_OF(inner)

    raise TypeInferenceError(
        f"Unsupported type annotation: {ast.dump(node)}",
        lineno=getattr(node, "lineno", None),
    )


# ---------------------------------------------------------------------------
# Type inference visitor
# ---------------------------------------------------------------------------

class TypeInferenceVisitor(ast.NodeVisitor):
    """
    Single-pass AST visitor that populates an ``AnalysisResult``.
    """

    def __init__(self) -> None:
        self.symbols = SymbolTable()
        self.functions: dict[str, FunctionSignature] = {}
        self.result = AnalysisResult()
        self._current_function: Optional[str] = None

    # -- helpers ------------------------------------------------------------

    def _record(self, node: ast.AST, py_type: PyType) -> None:
        """Associate *node* with its inferred *py_type*."""
        self.result.node_types[id(node)] = py_type

    def _infer_expr(self, node: ast.expr) -> PyType:
        """Infer and return the type of an arbitrary expression node."""

        # --- Constant literals ---
        if isinstance(node, ast.Constant):
            return self._infer_constant(node)

        # --- Variable reference ---
        if isinstance(node, ast.Name):
            t = self.symbols.lookup(node.id)
            if t is None:
                # Could be a builtin
                if node.id in ("True", "False"):
                    return BOOL
                raise ScopeError(
                    f"Undefined variable '{node.id}'",
                    lineno=getattr(node, "lineno", None),
                )
            return t

        # --- Binary operation ---
        if isinstance(node, ast.BinOp):
            left = self._infer_expr(node.left)
            right = self._infer_expr(node.right)
            result = promote(left, right)
            if result is None:
                raise TypeMismatchError(
                    f"Cannot apply {type(node.op).__name__} to {left} and {right}",
                    lineno=getattr(node, "lineno", None),
                )
            self._record(node, result)
            return result

        # --- Unary operation ---
        if isinstance(node, ast.UnaryOp):
            operand_type = self._infer_expr(node.operand)
            if isinstance(node.op, ast.Not):
                return BOOL
            return operand_type

        # --- Boolean operation ---
        if isinstance(node, ast.BoolOp):
            for val in node.values:
                self._infer_expr(val)
            return BOOL

        # --- Comparison ---
        if isinstance(node, ast.Compare):
            self._infer_expr(node.left)
            for comp in node.comparators:
                self._infer_expr(comp)
            return BOOL

        # --- Function call ---
        if isinstance(node, ast.Call):
            return self._infer_call(node)

        # --- List literal ---
        if isinstance(node, ast.List):
            if not node.elts:
                return LIST_OF(UNKNOWN)
            elem_type = self._infer_expr(node.elts[0])
            for elt in node.elts[1:]:
                t = self._infer_expr(elt)
                if t != elem_type:
                    promoted = promote(elem_type, t)
                    if promoted is not None:
                        elem_type = promoted
            return LIST_OF(elem_type)

        # --- Subscript (indexing) ---
        if isinstance(node, ast.Subscript):
            container_type = self._infer_expr(node.value)
            if container_type.base == BaseType.LIST and container_type.inner:
                return container_type.inner
            if container_type.base == BaseType.STRING:
                return STRING
            return UNKNOWN

        # --- Attribute access (e.g. s.upper) - just return the parent type for now ---
        if isinstance(node, ast.Attribute):
            return self._infer_expr(node.value)

        # --- IfExp (ternary) ---
        if isinstance(node, ast.IfExp):
            body_type = self._infer_expr(node.body)
            self._infer_expr(node.orelse)
            return body_type

        # --- Tuple (for multiple assignment values) ---
        if isinstance(node, ast.Tuple):
            types = [self._infer_expr(elt) for elt in node.elts]
            if types:
                return types[0]
            return UNKNOWN

        return UNKNOWN

    def _infer_constant(self, node: ast.Constant) -> PyType:
        """Map a literal constant to its type."""
        v = node.value
        if isinstance(v, bool):
            return BOOL
        if isinstance(v, int):
            return INT
        if isinstance(v, float):
            return FLOAT
        if isinstance(v, str):
            return STRING
        if v is None:
            return VOID
        return UNKNOWN

    def _infer_call(self, node: ast.Call) -> PyType:
        """Infer the return type of a function call."""

        # --- Built-in type constructors ---
        if isinstance(node.func, ast.Name):
            name = node.func.id

            # Type-casting functions
            if name == "int":
                return INT
            if name == "float":
                return FLOAT
            if name == "str":
                return STRING
            if name == "bool":
                return BOOL

            # Built-in functions
            if name == "len":
                return INT
            if name == "range":
                return INT  # range yields ints
            if name == "input":
                return STRING
            if name == "abs":
                if node.args:
                    return self._infer_expr(node.args[0])
                return INT
            if name == "print":
                return VOID
            if name == "max" or name == "min":
                if node.args:
                    return self._infer_expr(node.args[0])
                return INT

            # User-defined function
            if name in self.functions:
                return self.functions[name].return_type

            # Unknown function — can't infer
            return UNKNOWN

        # --- Method call (e.g. lst.append(x)) ---
        if isinstance(node.func, ast.Attribute):
            obj_type = self._infer_expr(node.func.value)
            method = node.func.attr

            if obj_type.base == BaseType.LIST:
                if method == "append":
                    return VOID
                if method == "pop":
                    return obj_type.inner if obj_type.inner else UNKNOWN
                if method == "sort":
                    return VOID
                if method == "reverse":
                    return VOID

            if obj_type.base == BaseType.STRING:
                if method in ("upper", "lower", "strip", "lstrip", "rstrip",
                              "replace", "join"):
                    return STRING
                if method in ("find", "index", "count"):
                    return INT
                if method == "split":
                    return LIST_OF(STRING)
                if method in ("startswith", "endswith", "isdigit", "isalpha"):
                    return BOOL

            return UNKNOWN

        return UNKNOWN

    # -- top-level visitors -------------------------------------------------

    def visit_Module(self, node: ast.Module) -> None:
        for stmt in node.body:
            self.visit(stmt)
        # Store global variables
        self.result.global_vars = dict(self.symbols.current_scope)
        self.result.functions = dict(self.functions)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Parse parameter types
        params: list[tuple[str, PyType]] = []
        for arg in node.args.args:
            if arg.annotation:
                ptype = _resolve_annotation(arg.annotation)
            else:
                ptype = UNKNOWN
            params.append((arg.arg, ptype))

        # Parse return type
        ret_type = VOID
        if node.returns:
            ret_type = _resolve_annotation(node.returns)

        sig = FunctionSignature(node.name, params, ret_type)
        self.functions[node.name] = sig
        self.symbols.define(node.name, ret_type)  # allow recursion

        # Analyze function body in a new scope
        self.symbols.push_scope()
        prev_func = self._current_function
        self._current_function = node.name

        for param_name, param_type in params:
            self.symbols.define(param_name, param_type)

        for stmt in node.body:
            self.visit(stmt)

        self._current_function = prev_func
        self.symbols.pop_scope()

    def visit_Assign(self, node: ast.Assign) -> None:
        value_type = self._infer_expr(node.value)
        self._record(node, value_type)

        # Handle tuple unpacking:  a, b = 1, 2
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Tuple)
            and isinstance(node.value, ast.Tuple)
        ):
            for target, val in zip(node.targets[0].elts, node.value.elts):
                if isinstance(target, ast.Name):
                    t = self._infer_expr(val)
                    self.symbols.define(target.id, t)
                    self._record(target, t)
            return

        for target in node.targets:
            if isinstance(target, ast.Name):
                self.symbols.define(target.id, value_type)
                self._record(target, value_type)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        ann_type = _resolve_annotation(node.annotation)
        if isinstance(node.target, ast.Name):
            self.symbols.define(node.target.id, ann_type)
            self._record(node, ann_type)
        if node.value:
            self._infer_expr(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            self._infer_expr(node.target)
        self._infer_expr(node.value)

    def visit_If(self, node: ast.If) -> None:
        self._infer_expr(node.test)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_While(self, node: ast.While) -> None:
        self._infer_expr(node.test)
        for stmt in node.body:
            self.visit(stmt)

    def visit_For(self, node: ast.For) -> None:
        # Infer iterator type
        iter_type = self._infer_expr(node.iter)
        self._record(node.iter, iter_type)

        # Register loop variable
        if isinstance(node.target, ast.Name):
            # For range() calls, the variable is int
            if (isinstance(node.iter, ast.Call)
                    and isinstance(node.iter.func, ast.Name)
                    and node.iter.func.id == "range"):
                self.symbols.define(node.target.id, INT)
            elif iter_type.base == BaseType.LIST and iter_type.inner:
                self.symbols.define(node.target.id, iter_type.inner)
            elif iter_type.base == BaseType.STRING:
                self.symbols.define(node.target.id, STRING)
            else:
                self.symbols.define(node.target.id, UNKNOWN)

        for stmt in node.body:
            self.visit(stmt)

    def visit_Return(self, node: ast.Return) -> None:
        if node.value:
            self._infer_expr(node.value)

    def visit_Expr(self, node: ast.Expr) -> None:
        """A bare expression statement (e.g. a function call like print(...))."""
        self._infer_expr(node.value)

    def visit_Pass(self, node: ast.Pass) -> None:
        pass

    def visit_Break(self, node: ast.Break) -> None:
        pass

    def visit_Continue(self, node: ast.Continue) -> None:
        pass

    # -- catch unsupported constructs ---------------------------------------

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        raise UnsupportedFeatureError(
            f"Classes are not supported (class '{node.name}')",
            lineno=node.lineno,
        )

    def visit_Import(self, node: ast.Import) -> None:
        raise UnsupportedFeatureError("Imports are not supported", lineno=node.lineno)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raise UnsupportedFeatureError("Imports are not supported", lineno=node.lineno)

    def visit_Try(self, node: ast.Try) -> None:
        raise UnsupportedFeatureError(
            "Exception handling is not supported", lineno=node.lineno,
        )

    def visit_With(self, node: ast.With) -> None:
        raise UnsupportedFeatureError(
            "Context managers are not supported", lineno=node.lineno,
        )

    def visit_Lambda(self, node: ast.Lambda) -> None:
        raise UnsupportedFeatureError(
            "Lambda expressions are not supported", lineno=node.lineno,
        )

    def visit_ListComp(self, node: ast.ListComp) -> None:
        raise UnsupportedFeatureError(
            "List comprehensions are not supported", lineno=node.lineno,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze(tree: ast.Module) -> AnalysisResult:
    """
    Run type inference and scope analysis on *tree*.

    Returns an ``AnalysisResult`` consumed by the code generator.
    """
    visitor = TypeInferenceVisitor()
    visitor.visit(tree)
    return visitor.result
