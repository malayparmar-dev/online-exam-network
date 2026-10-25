#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if [[ ! -f ".venv-sdn/bin/activate" ]]; then
    echo "Error: Python virtual environment not found."
    exit 1
fi

source .venv-sdn/bin/activate

exec osken-manager \
    --ofp-tcp-listen-port "${EXAM_OPENFLOW_PORT:-6653}" \
    sdn/exam_controller.py
