#!/usr/bin/env bash
set -uo pipefail

PROJECT_DIR="$HOME/online-exam-network"
cd "$PROJECT_DIR" || exit 1

STAMP="$(date +%Y%m%d_%H%M%S)"
REPORT="results/full_run_${STAMP}.txt"
LOGDIR="results/full_run_${STAMP}_logs"
mkdir -p results "$LOGDIR"

PASS=0
FAIL=0
SKIP=0
STARTED_CONTROLLER=0
STARTED_SERVER=0
CONTROLLER_PID=""
SERVER_PID=""

log() { printf '%s\n' "$*" | tee -a "$REPORT"; }
pass() { PASS=$((PASS+1)); log "[PASS] $*"; }
fail() { FAIL=$((FAIL+1)); log "[FAIL] $*"; }
skip() { SKIP=$((SKIP+1)); log "[SKIP] $*"; }

port_open() {
    timeout 1 bash -c "exec 3<>/dev/tcp/127.0.0.1/$1" 2>/dev/null
}

cleanup() {
    log ""
    log "---- CLEANUP ----"

    if [[ "$STARTED_SERVER" -eq 1 && -n "$SERVER_PID" ]]; then
        kill "$SERVER_PID" 2>/dev/null || true
        log "Stopped application server started by this run."
    else
        log "Left pre-existing application server untouched."
    fi

    if [[ "$STARTED_CONTROLLER" -eq 1 && -n "$CONTROLLER_PID" ]]; then
        kill "$CONTROLLER_PID" 2>/dev/null || true
        log "Stopped controller process started by this run."
    else
        log "Left pre-existing controller untouched."
    fi

    log "Cleanup complete."
}
trap cleanup EXIT

log "=================================================="
log "ONLINE EXAM NETWORK - AUTOMATED VALIDATION"
log "Started: $(date)"
log "Project: $PROJECT_DIR"
log "=================================================="

log ""
log "---- 1. PREFLIGHT ----"
for f in Makefile src/server.c src/client.c src/protocol.c \
         src/protocol.h src/topology.py sdn/exam_controller.py \
         scripts/test_sdn_policy.py; do
    if [[ -f "$f" ]]; then pass "Found $f"; else fail "Missing $f"; fi
done

for cmd in gcc make python3 mn ovs-vsctl; do
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "Dependency available: $cmd"
    else
        fail "Missing dependency: $cmd"
    fi
done

if ! sudo -n true 2>/dev/null; then
    fail "Passwordless sudo unavailable; Mininet batch test cannot run unattended"
fi

log ""
log "---- 2. BUILD ----"
if make clean all >"$LOGDIR/build.log" 2>&1; then
    pass "C application builds successfully"
else
    fail "Build failed; see $LOGDIR/build.log"
    cat "$LOGDIR/build.log" | tee -a "$REPORT"
fi

log ""
log "---- 3. SDN CONTROLLER ----"
if port_open 8765 && port_open 6653; then
    pass "Reusing existing SDN controller"
else
    if [[ -x .venv-sdn/bin/osken-manager ]]; then
        nohup ./scripts/start_controller.sh >"$LOGDIR/controller.log" 2>&1 &
        CONTROLLER_PID=$!
        STARTED_CONTROLLER=1
        for _ in $(seq 1 30); do
            if port_open 8765 && port_open 6653; then break; fi
            sleep 1
        done
        if port_open 8765 && port_open 6653; then
            pass "Started SDN controller"
        else
            fail "Controller did not become ready; see $LOGDIR/controller.log"
        fi
    else
        fail "OS-Ken executable missing from .venv-sdn"
    fi
fi

log ""
log "---- 4. APPLICATION SERVER ----"
if port_open 8080; then
    pass "Reusing existing TCP application server"
else
    if [[ -x ./server ]]; then
        ./server >"$LOGDIR/server.log" 2>&1 &
        SERVER_PID=$!
        STARTED_SERVER=1
        for _ in $(seq 1 20); do
            if port_open 8080; then break; fi
            sleep 0.5
        done
        if port_open 8080; then
            pass "Started TCP application server"
        else
            fail "Application server did not start; see $LOGDIR/server.log"
        fi
    else
        fail "Server executable unavailable"
    fi
fi

log ""
log "---- 5. CONCURRENT EXAM TEST ----"
RUN_ID="$(date +%H%M%S)_$$"
if timeout 120 python3 - "$RUN_ID" >"$LOGDIR/concurrent_exams.log" 2>&1 <<'PY'
import re, socket, sys, threading
from concurrent.futures import ThreadPoolExecutor

HOST, PORT, N = "127.0.0.1", 8080, 10
RUN_ID = sys.argv[1]
ANSWERS = ["B", "C", "C", "A", "B"]
barrier = threading.Barrier(N)

def recvline(sock, buf):
    while b"\n" not in buf:
        data = sock.recv(4096)
        if not data:
            raise ConnectionError("server closed connection")
        buf += data
    line, buf = buf.split(b"\n", 1)
    return line.decode(errors="replace").strip(), buf

def cmd(sock, text, buf):
    sock.sendall((text + "\n").encode())
    return recvline(sock, buf)

def student(i):
    sid = f"AUTO_{RUN_ID}_{i:02d}"
    try:
        with socket.create_connection((HOST, PORT), timeout=10) as s:
            s.settimeout(10)
            buf = b""
            barrier.wait(timeout=15)
            s.sendall(f"STUDENT {sid}\n".encode())
            line, buf = recvline(s, buf)
            line, buf = recvline(s, buf)
            if "Enter START" not in line:
                raise RuntimeError("unexpected welcome: " + line)
            line, buf = cmd(s, "START", buf)
            if not line.startswith("STARTED:"):
                raise RuntimeError("start failed: " + line)
            for q, ans in enumerate(ANSWERS, 1):
                line, buf = cmd(s, f"GET {q}", buf)
                if not line.startswith("QUESTION "):
                    raise RuntimeError(f"GET {q}: {line}")
                line, buf = cmd(s, f"ANSWER {q} {ans}", buf)
                if not line.startswith("OK:"):
                    raise RuntimeError(f"ANSWER {q}: {line}")
            line, buf = cmd(s, "SUBMIT", buf)
            m = re.search(r"\bScore\s*=\s*(\d+)\s*/\s*(\d+)", line)
            if not line.startswith("RESULT:") or not m or m.groups() != ("5", "5"):
                raise RuntimeError("unexpected result: " + line)
            return i, True, line
    except Exception as e:
        return i, False, f"{type(e).__name__}: {e}"

with ThreadPoolExecutor(max_workers=N) as pool:
    results = sorted(pool.map(student, range(1, N+1)))
for i, ok, detail in results:
    print(f"Student {i:02d}: {'PASS' if ok else 'FAIL'} | {detail}")
passed = sum(ok for _, ok, _ in results)
print(f"SUMMARY: {passed}/{N} passed")
sys.exit(0 if passed == N else 1)
PY
then
    cat "$LOGDIR/concurrent_exams.log" | tee -a "$REPORT"
    pass "10-client concurrent exam test passed"
else
    cat "$LOGDIR/concurrent_exams.log" 2>/dev/null | tee -a "$REPORT"
    fail "Concurrent exam test failed"
fi

log ""
log "---- 6. SDN + CONNECTIVITY + THROUGHPUT BATCH ----"
if pgrep -af '[s]rc/topology.py' >/dev/null 2>&1; then
    skip "A Mininet topology was already active; batch topology test not started to avoid disrupting it"
elif ! sudo -n true 2>/dev/null; then
    skip "Mininet batch test requires passwordless sudo"
elif ! port_open 8765 || ! port_open 6653; then
    fail "Controller is not available; cannot run Mininet batch test"
else
    if timeout 120 sudo -n python3 src/topology.py --batch >"$LOGDIR/mininet_batch.log" 2>&1; then
        cat "$LOGDIR/mininet_batch.log" | tee -a "$REPORT"
        if grep -q 'BATCH TESTS PASSED' "$LOGDIR/mininet_batch.log" &&
           grep -q 'SDN POLICY TEST: PASS' "$LOGDIR/mininet_batch.log" &&
           grep -q 'Results: 0% dropped' "$LOGDIR/mininet_batch.log" &&
           grep -qE 'receiver' "$LOGDIR/mininet_batch.log"; then
            pass "SDN policy, connectivity and throughput batch passed"
        else
            fail "Batch command exited successfully but expected test evidence is missing"
        fi
    else
        cat "$LOGDIR/mininet_batch.log" 2>/dev/null | tee -a "$REPORT"
        fail "Mininet batch experiment failed; see $LOGDIR/mininet_batch.log"
    fi
fi

log ""
log "---- 7. SUMMARY ----"
log "Passed: $PASS"
log "Failed: $FAIL"
log "Skipped / not verified: $SKIP"
log "Finished: $(date)"
log "Report: $REPORT"
log "Logs: $LOGDIR"
if [[ "$FAIL" -eq 0 ]]; then
    log "Overall: NO FAILURES IN EXECUTED CHECKS"
else
    log "Overall: FAILURES DETECTED"
fi
log "=================================================="

printf '%s\n' "$REPORT" > results/latest_full_run_report.txt
[[ "$FAIL" -eq 0 ]]
