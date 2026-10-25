#!/usr/bin/env python3
import socket
import sys
import time
import os

CONTROL_HOST = "127.0.0.1"
CONTROL_PORT = int(os.getenv("EXAM_CONTROL_PORT", "8765"))
TEST_IP = "10.0.0.1"

def request(command):
    with socket.create_connection(
        (CONTROL_HOST, CONTROL_PORT), timeout=5
    ) as sock:
        sock.settimeout(5)
        sock.sendall((command + "\n").encode())
        sock.shutdown(socket.SHUT_WR)
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        return response.decode(errors="replace").strip()

def check(condition, message):
    print(f"[{'PASS' if condition else 'FAIL'}] {message}")
    return condition

def main():
    passed = True

    try:
        status = request("STATUS")
        print("\n--- Initial controller status ---")
        print(status)

        if not check("Connected switches: 2" in status,
                     "Both switches are connected"):
            passed = False

        # Ensure our test IP starts unblocked.
        response = request(f"UNBLOCK {TEST_IP}")
        print("\nInitial cleanup:", response)
        if response.startswith("ERROR:"):
            passed = check(False, "Could not ensure test IP is unblocked") and passed
            return 1

        # Test rejection of invalid IPv4 addresses.
        response = request("BLOCK invalid-ip")
        if not check(response.startswith("ERROR: Invalid IPv4 address"),
                     "Invalid IP address is rejected"):
            passed = False

        # Test blocking.
        response = request(f"BLOCK {TEST_IP}")
        print("\nBlock response:", response)
        if not check(response == f"OK: Blocked {TEST_IP}",
                     "Controller accepts the block request"):
            passed = False

        time.sleep(0.5)
        status = request("STATUS")
        if not check(TEST_IP in status.split("Automatically blocked IPs:")[0],
                     "Blocked IP appears in controller status"):
            passed = False

    except Exception as exc:
        print(f"[FAIL] Control interface error: {exc}")
        passed = False

    finally:
        # Always try to restore the test host.
        try:
            response = request(f"UNBLOCK {TEST_IP}")
            print("\nCleanup:", response)
            if not response.startswith(f"OK: Unblocked {TEST_IP}"):
                # It may already be unblocked; confirm with STATUS.
                status = request("STATUS")
                if TEST_IP in status.split("Automatically blocked IPs:")[0]:
                    print("[FAIL] Test IP remains blocked!")
                    passed = False
                else:
                    print("[PASS] Test IP is unblocked")
        except Exception as exc:
            print(f"[FAIL] Could not verify cleanup: {exc}")
            passed = False

    print("\nFinal status:")
    try:
        print(request("STATUS"))
    except Exception as exc:
        print(exc)
        passed = False

    print("\nSDN POLICY TEST:", "PASS" if passed else "FAIL")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
