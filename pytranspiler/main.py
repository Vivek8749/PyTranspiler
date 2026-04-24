"""
CLI entry point for the transpiler.

Usage::

    python -m pytranspiler input.py [-o output.cpp]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import parse_file, parse_source
from .analyzer import analyze
from .codegen import generate
from .errors import TranspilerError


def build_cli() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="pytranspiler",
        description="Transpile a subset of Python into compilable C++17 code.",
    )
    parser.add_argument(
        "input",
        help="Path to the Python source file to transpile.",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Path to write the generated C++ file (default: stdout).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print extra diagnostic information.",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute the transpilation pipeline and return an exit code."""
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 1

    if not input_path.suffix == ".py":
        print(f"Warning: input file does not have .py extension", file=sys.stderr)

    try:
        # 1. Parse
        if args.verbose:
            print(f"[1/3] Parsing {input_path}...", file=sys.stderr)
        result = parse_file(input_path)

        # 2. Analyze
        if args.verbose:
            print("[2/3] Analyzing types and scopes...", file=sys.stderr)
        analysis = analyze(result.tree)

        # 3. Generate
        if args.verbose:
            print("[3/3] Generating C++ code...", file=sys.stderr)
        cpp_code = generate(result.tree, analysis)

    except TranspilerError as exc:
        print(f"Transpiler Error: {exc}", file=sys.stderr)
        return 1
    except SyntaxError as exc:
        print(f"Python Syntax Error: {exc}", file=sys.stderr)
        return 1

    # Output
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(cpp_code, encoding="utf-8")
        if args.verbose:
            print(f"Wrote {out_path}", file=sys.stderr)
    else:
        print(cpp_code)

    return 0


def main() -> None:
    """CLI entrypoint."""
    parser = build_cli()
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
