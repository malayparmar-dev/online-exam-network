#!/usr/bin/env python3
"""Compatibility entry point for the complete Mininet network experiment."""

import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_DIR / "scripts" / "run_network_validation.sh"


if __name__ == "__main__":
    raise SystemExit(subprocess.call([str(RUNNER)], cwd=PROJECT_DIR))
