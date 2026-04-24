# PyTranspiler — Python to C++ Transpiler

A basic transpiler that converts a subset of Python source code into compilable **C++17** code. Built entirely with the Python standard library using the `ast` module.

## Architecture

```
Python Source (.py)
      │
      ▼
┌─────────────┐
│   Parser    │  ast.parse() → Python AST
└──────┬──────┘
       │
       ▼
┌──────────────┐
│  Analyzer    │  Type inference + Symbol table
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Code Gen    │  Visitor pattern → C++ source
└──────┬───────┘
       │
       ▼
  C++ Source (.cpp)
```

## Quick Start

```bash
# Transpile a Python file to C++
python -m pytranspiler input.py -o output.cpp

# Or print to stdout
python -m pytranspiler input.py

# Compile the generated C++
g++ -o program output.cpp -std=c++17
./program
```

## Supported Features

| Feature | Example |
|---------|---------|
| Variables (int, float, str, bool) | `x: int = 5` or `x = 5` |
| Arithmetic (`+`, `-`, `*`, `/`, `//`, `%`, `**`) | `y = x + 2` |
| Comparisons & Booleans | `x > 5 and y < 10` |
| If / elif / else | `if x > 0:` |
| While loops | `while x > 0:` |
| For loops (range) | `for i in range(n):` |
| Functions (typed) | `def add(a: int, b: int) -> int:` |
| Print | `print("hello", x)` |
| Lists | `nums: list[int] = [1, 2, 3]` |
| List operations | `nums.append(4)`, `len(nums)` |
| Input | `x = int(input())` |
| Augmented assignment | `x += 1` |
| Type casting | `int(x)`, `float(x)`, `str(x)` |

## Type Mapping

| Python | C++ |
|--------|-----|
| `int` | `int` |
| `float` | `double` |
| `str` | `std::string` |
| `bool` | `bool` |
| `list[T]` | `std::vector<T>` |

## Running Tests

```bash
python tests/test_integration.py
```

## Project Structure

```
pytranspiler/
├── __init__.py       # Package init
├── __main__.py       # python -m pytranspiler
├── main.py           # CLI entry point
├── parser.py         # AST parsing wrapper
├── analyzer.py       # Type inference + symbol table
├── codegen.py        # C++ code generation
├── type_system.py    # Type definitions and mappings
└── errors.py         # Custom error types
tests/
├── test_integration.py
└── samples/          # Sample Python files
```

## Limitations

- No classes / OOP
- No dictionaries / sets / tuples  
- No lambda, list comprehensions, generators
- No exception handling (try/except)
- No imports / multi-file projects
- Variables must have inferrable types or annotations
