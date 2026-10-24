#!/usr/bin/env bash

set -e

PROJECT_DIR="$HOME/online-exam-network"
cd "$PROJECT_DIR"

if ! command -v mn >/dev/null 2>&1; then
    echo "Error: Mininet (mn) is not installed or not in PATH."
    exit 1
fi

exec sudo python3 src/topology.py
