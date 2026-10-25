#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

make test
python3 -m py_compile src/topology.py sdn/exam_controller.py scripts/*.py

if [[ -x .venv-sdn/bin/osken-manager ]]; then
    make test-controller
else
    printf '%s\n' "OS-Ken controller smoke test skipped; install requirements-sdn.txt to enable it."
fi

if [[ "${1:-}" == "--app-only" ]]; then
    printf '%s\n' "Application acceptance checks passed; network experiment skipped by request."
    exit 0
fi

exec ./scripts/run_network_validation.sh
