#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test runner for the wf2wf package.

This script checks for dependencies (pytest, etc) and then
executes the test suite using pytest.
"""

# Standard library imports
import subprocess
import sys
from pathlib import Path


def check_dependency(package_name):
    """Check if a Python package is installed."""
    try:
        __import__(package_name)
        print(f"✓ {package_name} is installed.")
        return True
    except ImportError:
        print(f"✗ ERROR: '{package_name}' is not installed.")
        return False


def main():
    """Run the wf2wf test suite."""
    print("=" * 60)
    print("Running wf2wf Test Suite")
    print("=" * 60)

    # Get the project root directory (where this script is located)
    project_root = Path(__file__).parent

    # --- Dependency Check ---
    print("\n1. Checking dependencies...")
    dependencies = ["pytest"]
    all_deps_installed = all(check_dependency(dep) for dep in dependencies)

    if not all_deps_installed:
        print("\nPlease install the missing testing dependencies:")
        print("   pip install pytest")
        sys.exit(1)

    # --- Running Pytest ---
    print("\n2. Executing pytest...")

    # Construct the pytest command
    # We run pytest as a module to ensure it uses the correct Python environment
    cmd = [sys.executable, "-m", "pytest"]

    print(f"   Command: {' '.join(cmd)}")
    print("-" * 60)

    # Execute the command from the project root directory
    result = subprocess.run(cmd, cwd=project_root)

    print("-" * 60)

    # --- Summary ---
    print("\n3. Test Summary")
    if result.returncode == 0:
        print("✅ All tests passed successfully!")
    else:
        print("❌ Some tests failed.")
        print(f"   Pytest exited with code: {result.returncode}")

    print("=" * 60)

    # Exit with the same code as pytest
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
