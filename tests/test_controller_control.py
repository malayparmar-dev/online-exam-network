#!/usr/bin/env python3
"""Exercise the OS-Ken controller's local control protocol without Mininet."""

import os
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / ".venv-sdn" / "bin" / "osken-manager"


def free_ports(count):
    sockets = [socket.socket() for _ in range(count)]
    try:
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


class ControllerControlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CONTROLLER.is_file():
            raise unittest.SkipTest(
                "OS-Ken environment is missing; install requirements-sdn.txt first"
            )
        cls.control_port, cls.openflow_port = free_ports(2)
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="exam-controller-test-")
        cls.log_path = Path(cls.temp_dir.name) / "controller.log"
        cls.log = open(cls.log_path, "w")
        env = os.environ.copy()
        env.update({
            "EXAM_CONTROL_PORT": str(cls.control_port),
            "EXAM_AUTO_BLOCK_PPS": "321",
            "EXAM_STATS_INTERVAL": "0.5",
        })
        cls.process = subprocess.Popen(
            [str(CONTROLLER), "--ofp-tcp-listen-port", str(cls.openflow_port),
             "sdn/exam_controller.py"],
            cwd=ROOT,
            env=env,
            stdout=cls.log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if cls.process.poll() is not None:
                    raise RuntimeError(f"controller exited; see {cls.log_path}")
                try:
                    cls.request("STATUS")
                    break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"controller did not start; see {cls.log_path}")
        except Exception:
            cls.process.terminate()
            try:
                cls.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                cls.process.kill()
                cls.process.wait(timeout=3)
            cls.log.close()
            cls.temp_dir.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        process = getattr(cls, "process", None)
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if getattr(cls, "log", None) is not None:
            cls.log.close()
        if getattr(cls, "temp_dir", None) is not None:
            cls.temp_dir.cleanup()

    @classmethod
    def request(cls, command, fragmented=False):
        with socket.create_connection(
            ("127.0.0.1", cls.control_port), timeout=2
        ) as sock:
            sock.settimeout(2)
            if fragmented:
                sock.sendall(command[:3].encode())
                time.sleep(0.02)
                sock.sendall((command[3:] + "\n").encode())
            else:
                sock.sendall((command + "\n").encode())
            sock.shutdown(socket.SHUT_WR)
            response = bytearray()
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response.extend(chunk)
            return response.decode(errors="replace").strip()

    def test_status_refuses_server_and_handles_block_unblock(self):
        status = self.request("STATUS", fragmented=True)
        self.assertIn("Connected switches: 0", status)
        self.assertIn("Statistics interval: 0.5s", status)
        self.assertIn("Packet-rate threshold: 321.0 packets/s", status)
        self.assertTrue(self.request("BLOCK invalid").startswith("ERROR: Invalid IPv4"))
        self.assertTrue(self.request("BLOCK 10.0.0.10").startswith("ERROR: Could not block"))
        self.assertEqual(self.request("BLOCK 10.0.0.1"), "OK: Blocked 10.0.0.1")
        self.assertIn("Blocked IPs: 10.0.0.1", self.request("STATUS"))
        self.assertEqual(self.request("UNBLOCK 10.0.0.1"), "OK: Unblocked 10.0.0.1")
        final_status = self.request("STATUS")
        self.assertIn("Blocked IPs: none", final_status)
        self.assertIn("Automatically blocked IPs: none", final_status)


if __name__ == "__main__":
    unittest.main(verbosity=2)
