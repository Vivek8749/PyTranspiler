"""
C++ code generator — the core visitor that emits C++ source code.

Traverses the Python AST using the Visitor pattern, consulting the
``AnalysisResult`` produced by the analyzer for type information.
Outputs a complete, compilable C++17 source file.
"""

from __future__ import annotations

import ast
from typing import Optional

from .type_system import (
    PyType, BaseType,
    INT, FLOAT, STRING, BOOL, VOID, UNKNOWN, LIST_OF,
    to_cpp_type, headers_for_type,
    BINOP_MAP, UNARYOP_MAP, BOOLOP_MAP, CMPOP_MAP, AUGASSIGN_MAP,
)
from .analyzer import AnalysisResult
from .errors import UnsupportedFeatureError


class CppCodeGenerator(ast.NodeVisitor):
    """
    Walks a Python AST and emits equivalent C++17 source code.

    Usage::

        gen = CppCodeGenerator(analysis_result)
        cpp_source = gen.generate(tree)
    """

    def __init__(self, analysis: AnalysisResult) -> None:
        self.analysis = analysis
        self._indent = 0                 # current indentation level
        self._lines: list[str] = []      # accumulated output lines
        self._headers: set[str] = set()  # required #include headers
        self._in_main = False            # whether we are inside main()
        self._declared_vars: set[str] = set()  # track declared variables per scope
        self._scope_stack: list[set[str]] = []  # stack of declared var sets

    # ── public API ─────────────────────────────────────────────────────────

    def generate(self, tree: ast.Module) -> str:
        """Generate the complete C++ source for *tree*."""
        # Always need iostream for cout/cin
        self._headers.add("<iostream>")

        # First pass: collect functions and global statements
        functions: list[ast.FunctionDef] = []
        global_stmts: list[ast.stmt] = []

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.append(node)
            else:
                global_stmts.append(node)

        # Generate functions first (before main)
        func_lines: list[str] = []
        for func in functions:
            self._lines = []
            self.visit_FunctionDef(func)
            func_lines.extend(self._lines)
            func_lines.append("")

        # Generate main body
        self._lines = []
        self._in_main = True
        self._declared_vars = set()
        for stmt in global_stmts:
            self.visit(stmt)
        self._in_main = False
        main_body_lines = list(self._lines)

        # Assemble final output
        output: list[str] = []

        # Headers
        for header in sorted(self._headers):
            output.append(f"#include {header}")
        output.append("")
        output.append("using namespace std;")
        output.append("")

        # Function definitions
        if func_lines:
            output.extend(func_lines)

        # Main function
        output.append("int main() {")
        for line in main_body_lines:
            output.append("    " + line if line.strip() else "")
        output.append("    return 0;")
        output.append("}")
        output.append("")

        return "\n".join(output)

    # ── indentation helpers ────────────────────────────────────────────────

    def _emit(self, line: str) -> None:
        """Append *line* at the current indentation level."""
        prefix = "    " * self._indent
        self._lines.append(f"{prefix}{line}")

    def _emit_raw(self, line: str) -> None:
        """Append *line* without any indentation."""
        self._lines.append(line)

    def _push_scope(self) -> None:
        self._scope_stack.append(self._declared_vars.copy())
        self._declared_vars = self._declared_vars.copy()

    def _pop_scope(self) -> None:
        self._declared_vars = self._scope_stack.pop()

    # ── type helpers ───────────────────────────────────────────────────────

    def _get_type(self, node: ast.AST) -> PyType:
        """Look up the inferred type of *node*."""
        return self.analysis.node_types.get(id(node), UNKNOWN)

    def _track_type(self, py_type: PyType) -> None:
        """Register the headers required by *py_type*."""
        self._headers |= headers_for_type(py_type)

    # ── expression rendering ──────────────────────────────────────────────

    def _render_expr(self, node: ast.expr) -> str:
        """Render an expression node as a C++ expression string."""

        # --- Constants ---
        if isinstance(node, ast.Constant):
            return self._render_constant(node)

        # --- Variable reference ---
        if isinstance(node, ast.Name):
            return node.id

        # --- Binary operator ---
        if isinstance(node, ast.BinOp):
            left = self._render_expr(node.left)
            right = self._render_expr(node.right)
            if isinstance(node.op, ast.Pow):
                self._headers.add("<cmath>")
                return f"pow({left}, {right})"
            if isinstance(node.op, ast.FloorDiv):
                return f"(int)({left} / {right})"
            op = BINOP_MAP.get(type(node.op), "?")
            return f"({left} {op} {right})"

        # --- Unary operator ---
        if isinstance(node, ast.UnaryOp):
            operand = self._render_expr(node.operand)
            op = UNARYOP_MAP.get(type(node.op), "?")
            return f"{op}({operand})"

        # --- Boolean operator ---
        if isinstance(node, ast.BoolOp):
            op = BOOLOP_MAP.get(type(node.op), "?")
            parts = [self._render_expr(v) for v in node.values]
            return f" {op} ".join(parts)

        # --- Comparison ---
        if isinstance(node, ast.Compare):
            result = self._render_expr(node.left)
            for op, comp in zip(node.ops, node.comparators):
                cpp_op = CMPOP_MAP.get(type(op), "?")
                result += f" {cpp_op} {self._render_expr(comp)}"
            return result

        # --- Function call ---
        if isinstance(node, ast.Call):
            return self._render_call(node)

        # --- List literal ---
        if isinstance(node, ast.List):
            elts = ", ".join(self._render_expr(e) for e in node.elts)
            return "{" + elts + "}"

        # --- Subscript (indexing) ---
        if isinstance(node, ast.Subscript):
            value = self._render_expr(node.value)
            idx = self._render_expr(node.slice)
            return f"{value}[{idx}]"

        # --- Attribute (method — handled in call) ---
        if isinstance(node, ast.Attribute):
            return f"{self._render_expr(node.value)}.{node.attr}"

        # --- If expression (ternary) ---
        if isinstance(node, ast.IfExp):
            test = self._render_expr(node.test)
            body = self._render_expr(node.body)
            orelse = self._render_expr(node.orelse)
            return f"({test} ? {body} : {orelse})"

        return f"/* unsupported expr: {ast.dump(node)} */"

    def _render_constant(self, node: ast.Constant) -> str:
        """Render a literal constant as C++."""
        v = node.value
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            return repr(v)
        if isinstance(v, str):
            # Escape special characters and wrap in quotes
            escaped = (
                v.replace("\\", "\\\\")
                 .replace('"', '\\"')
                 .replace("\n", "\\n")
                 .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        if v is None:
            return ""
        return str(v)

    def _render_call(self, node: ast.Call) -> str:
        """Render a function/method call as C++."""

        # --- Built-in function calls ---
        if isinstance(node.func, ast.Name):
            name = node.func.id
            args = [self._render_expr(a) for a in node.args]

            # print(...)  →  cout << a << " " << b << ... << endl
            if name == "print":
                return self._render_print(node)

            # input()  →  handled at statement level
            if name == "input":
                return "/* input */"

            # len(x)
            if name == "len":
                if args:
                    return f"{args[0]}.size()"
                return "0"

            # range() — handled specially in for-loop visitor
            if name == "range":
                return "/* range */"

            # Type casts
            if name == "int":
                return f"(int)({args[0]})" if args else "0"
            if name == "float":
                return f"(double)({args[0]})" if args else "0.0"
            if name == "str":
                self._headers.add("<string>")
                if args:
                    return f"to_string({args[0]})"
                return '""'
            if name == "bool":
                return f"(bool)({args[0]})" if args else "false"

            # abs()
            if name == "abs":
                self._headers.add("<cmath>")
                return f"abs({args[0]})" if args else "0"

            # max / min
            if name in ("max", "min"):
                self._headers.add("<algorithm>")
                return f"{name}({', '.join(args)})"

            # User-defined function
            return f"{name}({', '.join(args)})"

        # --- Method calls ---
        if isinstance(node.func, ast.Attribute):
            obj = self._render_expr(node.func.value)
            method = node.func.attr
            args = [self._render_expr(a) for a in node.args]

            # List methods
            if method == "append":
                return f"{obj}.push_back({args[0]})" if args else f"{obj}.push_back()"
            if method == "pop":
                if args:
                    return f"{obj}.erase({obj}.begin() + {args[0]})"
                return f"({obj}.pop_back(), {obj}.back())"
            if method == "sort":
                self._headers.add("<algorithm>")
                return f"sort({obj}.begin(), {obj}.end())"
            if method == "reverse":
                self._headers.add("<algorithm>")
                return f"reverse({obj}.begin(), {obj}.end())"

            # String methods
            if method == "upper":
                self._headers.add("<algorithm>")
                self._headers.add("<cctype>")
                # We'll generate a helper — for now inline transform
                return (f"[&]() {{ string s = {obj}; "
                        f"transform(s.begin(), s.end(), s.begin(), ::toupper); "
                        f"return s; }}()")
            if method == "lower":
                self._headers.add("<algorithm>")
                self._headers.add("<cctype>")
                return (f"[&]() {{ string s = {obj}; "
                        f"transform(s.begin(), s.end(), s.begin(), ::tolower); "
                        f"return s; }}()")
            if method == "find":
                return f"{obj}.find({args[0]})" if args else f"{obj}.find()"
            if method == "replace":
                # Simple replace — only first occurrence
                if len(args) >= 2:
                    return (f"[&]() {{ string s = {obj}; "
                            f"auto pos = s.find({args[0]}); "
                            f"if (pos != string::npos) s.replace(pos, string({args[0]}).length(), {args[1]}); "
                            f"return s; }}()")
            if method == "strip":
                # C++ doesn't have strip — generate inline
                return (f"[&]() {{ string s = {obj}; "
                        f"s.erase(0, s.find_first_not_of(\" \\t\\n\\r\")); "
                        f"s.erase(s.find_last_not_of(\" \\t\\n\\r\") + 1); "
                        f"return s; }}()")
            if method == "split":
                self._headers.add("<sstream>")
                self._headers.add("<vector>")
                return (f"[&]() {{ vector<string> tokens; string token; "
                        f"istringstream ss({obj}); "
                        f"while (ss >> token) tokens.push_back(token); "
                        f"return tokens; }}()")
            if method == "join":
                # separator.join(list)
                if args:
                    return (f"[&]() {{ string result; "
                            f"for (size_t i = 0; i < {args[0]}.size(); i++) {{ "
                            f"if (i > 0) result += {obj}; "
                            f"result += {args[0]}[i]; }} "
                            f"return result; }}()")
            if method == "startswith":
                return f"{obj}.substr(0, string({args[0]}).length()) == {args[0]}" if args else "false"
            if method == "endswith":
                if args:
                    return (f"({obj}.length() >= string({args[0]}).length() && "
                            f"{obj}.substr({obj}.length() - string({args[0]}).length()) == {args[0]})")
                return "false"

            # Generic method call
            return f"{obj}.{method}({', '.join(args)})"

        return f"/* unsupported call: {ast.dump(node)} */"

    def _render_print(self, node: ast.Call) -> str:
        """Render a print() call as std::cout << ... << endl;"""
        parts: list[str] = []
        for i, arg in enumerate(node.args):
            if i > 0:
                parts.append('" "')
            parts.append(self._render_expr(arg))

        # Check for end= keyword
        endl = "endl"
        for kw in node.keywords:
            if kw.arg == "end":
                if isinstance(kw.value, ast.Constant) and kw.value.value == "":
                    endl = ""
                elif isinstance(kw.value, ast.Constant):
                    escaped = kw.value.value.replace("\n", "\\n").replace("\t", "\\t")
                    endl = f'"{escaped}"'

        chain = " << ".join(parts) if parts else '""'
        if endl:
            return f"cout << {chain} << {endl}"
        return f"cout << {chain}"

    # ── statement visitors ────────────────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        sig = self.analysis.functions.get(node.name)
        if not sig:
            return

        # Build parameter list
        params_str = ", ".join(
            f"{to_cpp_type(ptype)} {pname}" for pname, ptype in sig.params
        )
        self._track_type(sig.return_type)
        for _, ptype in sig.params:
            self._track_type(ptype)

        ret_type = to_cpp_type(sig.return_type)
        self._emit(f"{ret_type} {node.name}({params_str}) {{")

        self._indent += 1
        self._push_scope()
        # Params are already declared
        for pname, _ in sig.params:
            self._declared_vars.add(pname)

        for stmt in node.body:
            self.visit(stmt)

        self._pop_scope()
        self._indent -= 1
        self._emit("}")

    def visit_Assign(self, node: ast.Assign) -> None:
        # Handle tuple unpacking: a, b = 1, 2
        if (
            len(node.targets) == 1
            and isinstance(node.targets[0], ast.Tuple)
            and isinstance(node.value, ast.Tuple)
        ):
            for target, val in zip(node.targets[0].elts, node.value.elts):
                if isinstance(target, ast.Name):
                    val_type = self._get_type(target)
                    val_str = self._render_expr(val)
                    if target.id not in self._declared_vars:
                        self._track_type(val_type)
                        cpp_type = to_cpp_type(val_type)
                        self._emit(f"{cpp_type} {target.id} = {val_str};")
                        self._declared_vars.add(target.id)
                    else:
                        self._emit(f"{target.id} = {val_str};")
            return

        # Handle input():  x = int(input())  →  int x; cin >> x;
        if self._is_input_assignment(node):
            self._emit_input_assignment(node)
            return

        val_str = self._render_expr(node.value)
        val_type = self._get_type(node)

        for target in node.targets:
            if isinstance(target, ast.Name):
                if target.id not in self._declared_vars:
                    self._track_type(val_type)
                    cpp_type = to_cpp_type(val_type)
                    self._emit(f"{cpp_type} {target.id} = {val_str};")
                    self._declared_vars.add(target.id)
                else:
                    self._emit(f"{target.id} = {val_str};")
            elif isinstance(target, ast.Subscript):
                container = self._render_expr(target.value)
                idx = self._render_expr(target.slice)
                self._emit(f"{container}[{idx}] = {val_str};")

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        ann_type = self._get_type(node)
        self._track_type(ann_type)
        cpp_type = to_cpp_type(ann_type)

        if isinstance(node.target, ast.Name):
            name = node.target.id
            if node.value is not None:
                val_str = self._render_expr(node.value)
                self._emit(f"{cpp_type} {name} = {val_str};")
            else:
                self._emit(f"{cpp_type} {name};")
            self._declared_vars.add(name)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        target = self._render_expr(node.target)
        value = self._render_expr(node.value)
        op = AUGASSIGN_MAP.get(type(node.op))
        if op:
            self._emit(f"{target} {op} {value};")
        else:
            # Fallback for unsupported augmented ops (like **=)
            bin_op = BINOP_MAP.get(type(node.op), "?")
            self._emit(f"{target} = {target} {bin_op} {value};")

    def visit_If(self, node: ast.If) -> None:
        test = self._render_expr(node.test)
        self._emit(f"if ({test}) {{")
        self._indent += 1
        self._push_scope()
        for stmt in node.body:
            self.visit(stmt)
        self._pop_scope()
        self._indent -= 1

        # Handle elif chain
        orelse = node.orelse
        while orelse:
            if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                elif_node = orelse[0]
                test = self._render_expr(elif_node.test)
                self._emit(f"}} else if ({test}) {{")
                self._indent += 1
                self._push_scope()
                for stmt in elif_node.body:
                    self.visit(stmt)
                self._pop_scope()
                self._indent -= 1
                orelse = elif_node.orelse
            else:
                self._emit("} else {")
                self._indent += 1
                self._push_scope()
                for stmt in orelse:
                    self.visit(stmt)
                self._pop_scope()
                self._indent -= 1
                orelse = []

        self._emit("}")

    def visit_While(self, node: ast.While) -> None:
        test = self._render_expr(node.test)
        self._emit(f"while ({test}) {{")
        self._indent += 1
        self._push_scope()
        for stmt in node.body:
            self.visit(stmt)
        self._pop_scope()
        self._indent -= 1
        self._emit("}")

    def visit_For(self, node: ast.For) -> None:
        # Handle: for i in range(...)
        if (
            isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
            and isinstance(node.target, ast.Name)
        ):
            self._emit_range_for(node)
            return

        # Handle: for item in iterable
        if isinstance(node.target, ast.Name):
            iterable = self._render_expr(node.iter)
            var = node.target.id

            # Get the type of the loop variable
            iter_type = self.analysis.node_types.get(id(node.iter), UNKNOWN)
            if iter_type.base == BaseType.LIST and iter_type.inner:
                elem_cpp = to_cpp_type(iter_type.inner)
            elif iter_type.base == BaseType.STRING:
                elem_cpp = "char"
            else:
                elem_cpp = "auto"

            self._emit(f"for ({elem_cpp} {var} : {iterable}) {{")
            self._indent += 1
            self._push_scope()
            self._declared_vars.add(var)
            for stmt in node.body:
                self.visit(stmt)
            self._pop_scope()
            self._indent -= 1
            self._emit("}")

    def _emit_range_for(self, node: ast.For) -> None:
        """Emit a C-style for loop for ``for i in range(...)``."""
        args = node.iter.args  # type: ignore[attr-defined]
        var = node.target.id   # type: ignore[attr-defined]

        if len(args) == 1:
            # range(stop)
            stop = self._render_expr(args[0])
            self._emit(f"for (int {var} = 0; {var} < {stop}; {var}++) {{")
        elif len(args) == 2:
            # range(start, stop)
            start = self._render_expr(args[0])
            stop = self._render_expr(args[1])
            self._emit(f"for (int {var} = {start}; {var} < {stop}; {var}++) {{")
        elif len(args) == 3:
            # range(start, stop, step)
            start = self._render_expr(args[0])
            stop = self._render_expr(args[1])
            step = self._render_expr(args[2])
            # Determine direction
            self._emit(f"for (int {var} = {start}; {var} < {stop}; {var} += {step}) {{")
        else:
            self._emit(f"// unsupported range() call")
            return

        self._indent += 1
        self._push_scope()
        self._declared_vars.add(var)
        for stmt in node.body:
            self.visit(stmt)
        self._pop_scope()
        self._indent -= 1
        self._emit("}")

    def visit_Return(self, node: ast.Return) -> None:
        if node.value:
            val = self._render_expr(node.value)
            self._emit(f"return {val};")
        else:
            self._emit("return;")

    def visit_Expr(self, node: ast.Expr) -> None:
        """A bare expression statement (e.g. print(...), method call)."""
        expr_str = self._render_expr(node.value)
        if expr_str and not expr_str.startswith("/*"):
            self._emit(f"{expr_str};")

    def visit_Pass(self, node: ast.Pass) -> None:
        self._emit("// pass")

    def visit_Break(self, node: ast.Break) -> None:
        self._emit("break;")

    def visit_Continue(self, node: ast.Continue) -> None:
        self._emit("continue;")

    # ── input handling ─────────────────────────────────────────────────────

    def _is_input_assignment(self, node: ast.Assign) -> bool:
        """Check if this is ``x = input()`` or ``x = int(input())`` etc."""
        value = node.value
        # x = input()
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            if value.func.id == "input":
                return True
        # x = int(input()) / float(input())
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            if value.func.id in ("int", "float", "str", "bool"):
                if (value.args
                        and isinstance(value.args[0], ast.Call)
                        and isinstance(value.args[0].func, ast.Name)
                        and value.args[0].func.id == "input"):
                    return True
        return False

    def _emit_input_assignment(self, node: ast.Assign) -> None:
        """Emit a cin >> x; for input() assignments."""
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            return

        name = target.id
        val_type = self._get_type(node)
        self._track_type(val_type)

        # Print the prompt if input() has an argument
        input_call = node.value
        if isinstance(input_call, ast.Call) and isinstance(input_call.func, ast.Name):
            if input_call.func.id in ("int", "float", "str", "bool"):
                # Wrapped: int(input("prompt"))
                inner_call = input_call.args[0] if input_call.args else None
                if (inner_call and isinstance(inner_call, ast.Call)
                        and inner_call.args
                        and isinstance(inner_call.args[0], ast.Constant)):
                    prompt = self._render_constant(inner_call.args[0])
                    self._emit(f"cout << {prompt};")
            elif input_call.func.id == "input":
                if (input_call.args
                        and isinstance(input_call.args[0], ast.Constant)):
                    prompt = self._render_constant(input_call.args[0])
                    self._emit(f"cout << {prompt};")

        cpp_type = to_cpp_type(val_type)
        if name not in self._declared_vars:
            self._emit(f"{cpp_type} {name};")
            self._declared_vars.add(name)
        self._emit(f"cin >> {name};")

    # ── comment extraction (best effort) ──────────────────────────────────

    def visit_Comment(self, node: ast.AST) -> None:
        """Not called by ast, but kept as a placeholder."""
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate(tree: ast.Module, analysis: AnalysisResult) -> str:
    """
    Generate C++17 source code for *tree*, using type info from *analysis*.
    """
    gen = CppCodeGenerator(analysis)
    return gen.generate(tree)
