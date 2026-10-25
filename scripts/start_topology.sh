#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v mn >/dev/null 2>&1; then
    echo "Error: Mininet (mn) is not installed or not in PATH."
    exit 1
fi

exec sudo --preserve-env=EXAM_OPENFLOW_PORT,EXAM_CONTROL_PORT python3 src/topology.py
