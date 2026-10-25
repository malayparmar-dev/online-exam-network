#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

mkdir -p results
STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="results/network_validation_${STAMP}.txt"
RAW="results/network_validation_${STAMP}_raw.log"
CONTROLLER_LOG="/tmp/exam-controller-${STAMP}-$$.log"
CONTROLLER_PID=""
OPENFLOW_PORT="${EXAM_OPENFLOW_PORT:-6653}"
CONTROL_PORT="${EXAM_CONTROL_PORT:-8765}"

port_open() {
    timeout 1 bash -c "exec 3<>/dev/tcp/127.0.0.1/$1" 2>/dev/null
}

cleanup() {
    if [[ -n "$CONTROLLER_PID" ]]; then
        kill "$CONTROLLER_PID" 2>/dev/null || true
        wait "$CONTROLLER_PID" 2>/dev/null || true
        printf '%s\n' "Stopped controller started by this run." >> "$REPORT"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

{
    printf '%s\n' "Online Examination Network - Network Validation"
    printf 'Date: %s\n' "$(date --iso-8601=seconds)"
    printf 'Checkout: %s\n' "$PROJECT_DIR"
    printf 'Git HEAD: %s\n' "$(git rev-parse HEAD)"
    printf '\n'
} > "$REPORT"

if ! sudo -n true 2>> "$REPORT"; then
    printf '%s\n' "ERROR: Mininet needs sudo access; no non-interactive sudo permission is available." | tee -a "$REPORT"
    exit 1
fi

if port_open "$OPENFLOW_PORT" && port_open "$CONTROL_PORT"; then
    printf '%s\n' "Reusing controller already listening on 6653/8765." | tee -a "$REPORT"
elif port_open "$OPENFLOW_PORT" || port_open "$CONTROL_PORT"; then
    printf '%s\n' "ERROR: only one controller port is occupied; refusing to alter it." | tee -a "$REPORT"
    exit 1
else
    if [[ ! -x .venv-sdn/bin/osken-manager ]]; then
        printf '%s\n' "ERROR: OS-Ken is missing. Follow the README setup steps." | tee -a "$REPORT"
        exit 1
    fi
    ./scripts/start_controller.sh > "$CONTROLLER_LOG" 2>&1 &
    CONTROLLER_PID=$!
    ready=0
    for _ in $(seq 1 30); do
        if port_open "$OPENFLOW_PORT" && port_open "$CONTROL_PORT"; then
            ready=1
            break
        fi
        if ! kill -0 "$CONTROLLER_PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    if [[ "$ready" -ne 1 ]]; then
        printf '%s\n' "ERROR: controller did not become ready; see $CONTROLLER_LOG" | tee -a "$REPORT"
        cat "$CONTROLLER_LOG" >> "$REPORT"
        exit 1
    fi
    printf '%s\n' "Started controller for this run." | tee -a "$REPORT"
fi

printf '%s\n' "Starting Mininet batch tests (sudo privileges required)." | tee -a "$REPORT"
if sudo -n --preserve-env=EXAM_OPENFLOW_PORT,EXAM_CONTROL_PORT \
    python3 src/topology.py --batch > "$RAW" 2>&1; then
    cat "$RAW" | tee -a "$REPORT"
else
    status=$?
    printf '\nNetwork experiment failed (exit %s). Raw output: %s\n' "$status" "$RAW" | tee -a "$REPORT"
    tail -n 80 "$RAW" | tee -a "$REPORT"
    exit "$status"
fi

if ! grep -q 'BATCH TESTS PASSED' "$RAW" ||
   ! grep -q 'Automatic block detected for h1' "$RAW" ||
   ! grep -q 'PERFORMANCE_JSON' "$RAW" ||
   ! grep -q 'jain_fairness_mean' "$RAW" ||
   ! grep -q 'response_time_baseline_avg_ms' "$RAW" ||
   ! grep -q 'response_time_under_load_avg_ms' "$RAW"; then
    printf '%s\n' "ERROR: expected policy, response-time, fairness, or performance evidence was not found." | tee -a "$REPORT"
    exit 1
fi

printf '\nResult: NETWORK VALIDATION PASSED\nReport: %s\nRaw log: %s\n' "$REPORT" "$RAW" | tee -a "$REPORT"
