"""
Integration tests for the Python-to-C++ transpiler.

Each test transpiles a sample .py file and verifies the generated C++
contains expected constructs.
"""

import sys
import os
from pathlib import Path

# Ensure the project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pytranspiler.parser import parse_file, parse_source
from pytranspiler.analyzer import analyze
from pytranspiler.codegen import generate


SAMPLES_DIR = Path(__file__).resolve().parent / "samples"


def transpile_file(filename: str) -> str:
    """Helper: transpile a sample file and return the C++ source."""
    filepath = SAMPLES_DIR / filename
    result = parse_file(filepath)
    analysis = analyze(result.tree)
    return generate(result.tree, analysis)


def transpile_string(source: str) -> str:
    """Helper: transpile a Python source string and return C++ source."""
    result = parse_source(source)
    analysis = analyze(result.tree)
    return generate(result.tree, analysis)


# ── Hello World ────────────────────────────────────────────────────────────

class TestHelloWorld:
    def test_hello_output(self):
        cpp = transpile_file("hello.py")
        assert '#include <iostream>' in cpp
        assert 'cout << "Hello, World!" << endl;' in cpp
        assert 'int main()' in cpp
        assert 'return 0;' in cpp


# ── Variables ──────────────────────────────────────────────────────────────

class TestVariables:
    def test_int_declaration(self):
        cpp = transpile_string("x: int = 10")
        assert "int x = 10;" in cpp

    def test_float_declaration(self):
        cpp = transpile_string("y: float = 3.14")
        assert "double y = 3.14;" in cpp

    def test_string_declaration(self):
        cpp = transpile_string('name: str = "Alice"')
        assert 'string name = "Alice";' in cpp

    def test_bool_declaration(self):
        cpp = transpile_string("flag: bool = True")
        assert "bool flag = true;" in cpp

    def test_inferred_int(self):
        cpp = transpile_string("x = 42")
        assert "int x = 42;" in cpp

    def test_augmented_assign(self):
        cpp = transpile_string("x = 5\nx += 1")
        assert "x += 1;" in cpp

    def test_tuple_unpacking(self):
        cpp = transpile_string("a, b = 1, 2")
        assert "int a = 1;" in cpp
        assert "int b = 2;" in cpp

    def test_variables_sample(self):
        cpp = transpile_file("variables.py")
        assert "int x = 10;" in cpp
        assert "double y = 3.14;" in cpp
        assert 'string name = "Alice";' in cpp
        assert "bool flag = true;" in cpp


# ── Control Flow ──────────────────────────────────────────────────────────

class TestControlFlow:
    def test_if_elif_else(self):
        src = 'x = 15\nif x > 20:\n    print("big")\nelif x > 10:\n    print("medium")\nelse:\n    print("small")'
        cpp = transpile_string(src)
        assert "if (x > 20)" in cpp
        assert "else if (x > 10)" in cpp
        assert "} else {" in cpp

    def test_while_loop(self):
        src = "x = 0\nwhile x < 5:\n    x += 1"
        cpp = transpile_string(src)
        assert "while (x < 5)" in cpp

    def test_for_range_one_arg(self):
        src = "for i in range(10):\n    print(i)"
        cpp = transpile_string(src)
        assert "for (int i = 0; i < 10; i++)" in cpp

    def test_for_range_two_args(self):
        src = "for i in range(5, 10):\n    print(i)"
        cpp = transpile_string(src)
        assert "for (int i = 5; i < 10; i++)" in cpp

    def test_for_range_three_args(self):
        src = "for i in range(0, 20, 3):\n    print(i)"
        cpp = transpile_string(src)
        assert "for (int i = 0; i < 20; i += 3)" in cpp

    def test_control_flow_sample(self):
        cpp = transpile_file("control_flow.py")
        assert "if (x > 20)" in cpp
        assert "while (count < 5)" in cpp
        assert "for (int i = 0; i < 10; i++)" in cpp


# ── Functions ─────────────────────────────────────────────────────────────

class TestFunctions:
    def test_simple_function(self):
        src = "def add(a: int, b: int) -> int:\n    return a + b\nresult = add(3, 7)"
        cpp = transpile_string(src)
        assert "int add(int a, int b)" in cpp
        assert "return (a + b);" in cpp

    def test_string_function(self):
        src = 'def greet(name: str) -> str:\n    return "Hello, " + name\nmsg = greet("World")'
        cpp = transpile_string(src)
        assert "std::string greet(std::string name)" in cpp

    def test_recursive_function(self):
        cpp = transpile_file("fibonacci.py")
        assert "int fibonacci(int n)" in cpp
        assert "fibonacci((n - 1))" in cpp
        assert "fibonacci((n - 2))" in cpp

    def test_bool_return(self):
        src = "def is_even(n: int) -> bool:\n    return n % 2 == 0\nresult = is_even(4)"
        cpp = transpile_string(src)
        assert "bool is_even(int n)" in cpp

    def test_functions_sample(self):
        cpp = transpile_file("functions.py")
        assert "int add(int a, int b)" in cpp
        assert "int factorial(int n)" in cpp
        assert "int fibonacci(int n)" in cpp


# ── Lists ─────────────────────────────────────────────────────────────────

class TestLists:
    def test_list_declaration(self):
        src = "nums: list[int] = [1, 2, 3]"
        cpp = transpile_string(src)
        assert "vector<int> nums = {1, 2, 3};" in cpp

    def test_list_append(self):
        src = "nums: list[int] = [1, 2, 3]\nnums.append(4)"
        cpp = transpile_string(src)
        assert "nums.push_back(4);" in cpp

    def test_list_len(self):
        src = "nums: list[int] = [1, 2, 3]\nsize = len(nums)"
        cpp = transpile_string(src)
        assert "nums.size()" in cpp

    def test_list_iteration(self):
        src = "nums: list[int] = [1, 2, 3]\nfor n in nums:\n    print(n)"
        cpp = transpile_string(src)
        assert "for (int n : nums)" in cpp

    def test_lists_sample(self):
        cpp = transpile_file("lists.py")
        assert "vector<int>" in cpp
        assert "push_back" in cpp


# ── Print ─────────────────────────────────────────────────────────────────

class TestPrint:
    def test_print_string(self):
        cpp = transpile_string('print("hello")')
        assert 'cout << "hello" << endl;' in cpp

    def test_print_multiple_args(self):
        cpp = transpile_string('x = 5\nprint("x =", x)')
        assert 'cout << "x =" << " " << x << endl;' in cpp


# ── Expressions ──────────────────────────────────────────────────────────

class TestExpressions:
    def test_arithmetic(self):
        cpp = transpile_string("x = 3 + 4 * 2")
        assert "int x = (3 + (4 * 2));" in cpp

    def test_boolean_ops(self):
        cpp = transpile_string("x = True\ny = False\nz = x and y")
        assert "&&" in cpp

    def test_comparison(self):
        cpp = transpile_string("x = 5\nresult = x > 3")
        assert "x > 3" in cpp

    def test_type_cast(self):
        cpp = transpile_string("x = 3.14\ny = int(x)")
        assert "(int)" in cpp

    def test_floor_division(self):
        cpp = transpile_string("x = 7\ny = x // 2")
        assert "(int)(x / 2)" in cpp


# ── Full pipeline tests (transpile files) ─────────────────────────────────

class TestFullPipeline:
    def test_all_samples_transpile(self):
        """Every sample file should transpile without errors."""
        samples = ["hello.py", "variables.py", "control_flow.py",
                    "functions.py", "lists.py", "fibonacci.py"]
        for sample in samples:
            cpp = transpile_file(sample)
            assert "#include <iostream>" in cpp
            assert "int main()" in cpp
            assert "return 0;" in cpp

    def test_output_is_nonempty(self):
        """Transpiled output should have meaningful content."""
        for sample in SAMPLES_DIR.glob("*.py"):
            cpp = transpile_file(sample.name)
            lines = [l for l in cpp.splitlines() if l.strip()]
            assert len(lines) > 5, f"{sample.name} produced too few lines"


if __name__ == "__main__":
    # Simple runner without pytest
    import traceback

    test_classes = [
        TestHelloWorld, TestVariables, TestControlFlow,
        TestFunctions, TestLists, TestPrint, TestExpressions,
        TestFullPipeline,
    ]

    passed = 0
    failed = 0

    for cls in test_classes:
        instance = cls()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    getattr(instance, method_name)()
                    print(f"  PASS {cls.__name__}.{method_name}")
                    passed += 1
                except Exception as e:
                    print(f"  FAIL {cls.__name__}.{method_name}: {e}")
                    traceback.print_exc()
                    failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
