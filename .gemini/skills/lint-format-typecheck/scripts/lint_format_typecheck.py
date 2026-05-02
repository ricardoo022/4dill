#!/usr/bin/env python3
"""
Comprehensive Python linting, formatting, and type-checking runner.

Follows .github/workflows/ci.yml pattern:
1. Ruff check (lint)
2. Ruff format (check)
3. Mypy (type check)

Usage:
    python scripts/lint_format_typecheck.py              # Check all
    python scripts/lint_format_typecheck.py --fix        # Auto-fix all
    python scripts/lint_format_typecheck.py --format     # Only format
    python scripts/lint_format_typecheck.py --check      # Only check
    python scripts/lint_format_typecheck.py --types      # Only type check
"""

import subprocess
import sys

# Configuration matching CI/CD
RUFF_PATHS = ["src/", "tests/"]
MYPY_PATHS = ["src/pentest/"]


def run_command(cmd: list[str], description: str) -> tuple[int, str]:
    """Execute command and return exit code and output."""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print(f"{'='*60}")
    print(f"$ {' '.join(cmd)}\n")

    result = subprocess.run(
        cmd,
        capture_output=False,
        text=True,
    )

    return result.returncode, description


def main() -> int:
    """Run linting, formatting, and type checking."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Python linting, formatting, and type checking",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix issues where possible",
    )
    parser.add_argument(
        "--format",
        action="store_true",
        help="Only run ruff format",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only run ruff check",
    )
    parser.add_argument(
        "--types",
        action="store_true",
        help="Only run mypy type checking",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show formatting diff without applying",
    )

    args = parser.parse_args()

    # Determine which checks to run
    run_check = not (args.format or args.types)
    run_format = not (args.check or args.types)
    run_types = not (args.check or args.format)

    results = {}
    failed = False

    # Phase 1: Ruff check (linting)
    if run_check:
        cmd = ["ruff", "check"] + RUFF_PATHS
        if args.fix:
            cmd.append("--fix")
        exit_code, desc = run_command(cmd, "Ruff Check (Linting)")
        results["Ruff Check"] = "✅ PASS" if exit_code == 0 else "❌ FAIL"
        if exit_code != 0:
            failed = True

    # Phase 2: Ruff format (code formatting)
    if run_format:
        cmd = ["ruff", "format"]
        if not args.fix:
            cmd.append("--check")
        if args.diff:
            cmd.append("--diff")
        cmd.extend(RUFF_PATHS)
        exit_code, desc = run_command(cmd, "Ruff Format (Code Formatting)")
        results["Ruff Format"] = "✅ PASS" if exit_code == 0 else "❌ FAIL"
        if exit_code != 0:
            failed = True

    # Phase 3: Mypy type checking
    if run_types:
        cmd = ["mypy"] + MYPY_PATHS + ["--ignore-missing-imports"]
        exit_code, desc = run_command(cmd, "Mypy Type Checking")
        results["Mypy Type Check"] = "✅ PASS" if exit_code == 0 else "❌ FAIL"
        if exit_code != 0:
            failed = True

    # Summary
    print(f"\n{'='*60}")
    print("📊 Summary")
    print(f"{'='*60}")
    for tool, status in results.items():
        print(f"{tool:25} {status}")
    print(f"{'='*60}")

    if failed:
        print("\n❌ Some checks failed. See details above.")
        if not args.fix:
            print("\n💡 Tip: Run with --fix to auto-fix issues:")
            print("   python scripts/lint_format_typecheck.py --fix")
        return 1
    else:
        print("\n✅ All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
