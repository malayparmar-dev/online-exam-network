#!/usr/bin/env bash

set -e

PROJECT_DIR="$HOME/online-exam-network"
cd "$PROJECT_DIR"

if [[ ! -f ".venv-sdn/bin/activate" ]]; then
    echo "Error: Python virtual environment not found."
    exit 1
fi

source .venv-sdn/bin/activate

exec osken-manager \
    --ofp-tcp-listen-port 6653 \
    sdn/exam_controller.py
