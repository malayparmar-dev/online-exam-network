#!/usr/bin/env python3
"""Loopback acceptance tests for the current C examination application."""

import csv
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ExamServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="exam-app-test-")
        cls.metrics_path = Path(cls.temp_dir.name) / "metrics.csv"
        cls.port = free_port()
        env = os.environ.copy()
        env.update({
            "EXAM_PORT": str(cls.port),
            "EXAM_DURATION_SECONDS": "2",
            "EXAM_METRICS_FILE": str(cls.metrics_path),
        })
        cls.server_log = open(Path(cls.temp_dir.name) / "server.log", "w")
        cls.process = subprocess.Popen(
            [str(ROOT / "server")], cwd=ROOT, env=env,
            stdout=cls.server_log, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if cls.process.poll() is not None:
                raise RuntimeError("server exited during startup")
            try:
                with socket.create_connection(("127.0.0.1", cls.port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("server did not start listening")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=3)
        cls.server_log.close()
        cls.temp_dir.cleanup()

    def connect(self, student_id):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=3)
        sock.settimeout(4)
        reader = sock.makefile("rwb", buffering=0)
        reader.write(f"STUDENT {student_id}\n".encode())
        first = reader.readline().decode().strip()
        if first.startswith("ERROR:"):
            return sock, reader, [first]
        second = reader.readline().decode().strip()
        return sock, reader, [first, second]

    @staticmethod
    def start(reader):
        reader.write(b"START\n")
        return reader.readline().decode().strip()

    @staticmethod
    def command(reader, command):
        reader.write((command + "\n").encode())
        return reader.readline().decode().strip()

    def test_question_answer_change_validation_and_score(self):
        sock, reader, welcome = self.connect("answer_change")
        self.assertIn("WELCOME", welcome[0])
        self.assertIn("Enter START", welcome[1])
        self.assertIn("Duration is 2 seconds", self.start(reader))
        self.assertTrue(self.command(reader, "GET 1").startswith("QUESTION 1/5"))
        self.assertTrue(self.command(reader, "ANSWER 1 A").startswith("OK:"))
        self.assertTrue(self.command(reader, "ANSWER 1 B").startswith("OK:"))
        self.assertTrue(self.command(reader, "ANSWER 2 Z").startswith("ERROR:"))

        duplicate, duplicate_reader, duplicate_lines = self.connect("answer_change")
        self.assertTrue(duplicate_lines[0].startswith("ERROR: Student ID already"))
        duplicate_reader.close()
        duplicate.close()

        for number, answer in enumerate(("C", "A", "B"), start=3):
            self.assertTrue(self.command(reader, f"ANSWER {number} {answer}").startswith("OK:"))
        result = self.command(reader, "SUBMIT")
        self.assertIn("Score=4/5", result)
        self.assertIn("Answered=4/5", result)
        sock.close()

    def test_all_five_questions_are_delivered(self):
        sock, reader, _ = self.connect("question_bank")
        self.assertIn("STARTED", self.start(reader))
        for number in range(1, 6):
            self.assertTrue(
                self.command(reader, f"GET {number}").startswith(
                    f"QUESTION {number}/5:"
                )
            )
        self.assertIn("Score=0/5", self.command(reader, "SUBMIT"))
        sock.close()

    def test_sessions_are_isolated_and_accept_concurrently(self):
        clients = 10
        barrier = threading.Barrier(clients)

        def complete_attempt(index):
            sock, reader, welcome = self.connect(f"parallel_{index:02d}")
            try:
                if len(welcome) != 2:
                    raise AssertionError(f"unexpected welcome: {welcome}")
                if not self.start(reader).startswith("STARTED:"):
                    raise AssertionError("exam did not start")
                barrier.wait(timeout=2)
                answer = "B" if index % 2 == 0 else "A"
                if not self.command(reader, f"ANSWER 1 {answer}").startswith("OK:"):
                    raise AssertionError("answer was not accepted")
                return self.command(reader, "SUBMIT")
            finally:
                sock.close()

        with ThreadPoolExecutor(max_workers=clients) as pool:
            results = list(pool.map(complete_attempt, range(clients)))
        for index, result in enumerate(results):
            expected_score = 1 if index % 2 == 0 else 0
            self.assertIn(f"Score={expected_score}/5", result)
            self.assertIn("Answered=1/5", result)

    def test_slow_handshake_does_not_block_other_clients(self):
        stalled = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        started = time.monotonic()
        sock, reader, welcome = self.connect("while_stalled")
        self.assertEqual(len(welcome), 2)
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIn("STARTED", self.start(reader))
        self.assertIn("Score=0/5", self.command(reader, "SUBMIT"))
        stalled.close()
        sock.close()

    def test_client_program_completes_an_exam(self):
        completed = subprocess.run(
            [str(ROOT / "client"), "127.0.0.1", str(self.port)],
            input="cli_student\nSTART\nS\nYES\n",
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("WELCOME: Online Examination System", completed.stdout)
        self.assertIn("RESULT: Student=cli_student", completed.stdout)

    def test_client_navigation_and_invalid_command(self):
        completed = subprocess.run(
            [str(ROOT / "client"), "127.0.0.1", str(self.port)],
            input="navigation_student\nSTART\nN\nP\n5\nX\nS\nYES\n",
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("QUESTION 2/5:", completed.stdout)
        self.assertIn("QUESTION 1/5:", completed.stdout)
        self.assertIn("QUESTION 5/5:", completed.stdout)
        self.assertIn("Invalid command. Enter H", completed.stdout)
        self.assertIn("RESULT: Student=navigation_student Score=0/5", completed.stdout)

    def test_quit_abandons_without_submitting(self):
        sock, reader, welcome = self.connect("quit_student")
        self.assertEqual(len(welcome), 2)
        self.assertIn("STARTED", self.start(reader))
        self.assertEqual(
            self.command(reader, "QUIT"),
            "QUIT: Examination abandoned.",
        )
        self.assertEqual(reader.readline(), b"")
        sock.close()

    def test_oversized_command_is_rejected_without_killing_session(self):
        sock, reader, _ = self.connect("oversized_command")
        self.assertIn("STARTED", self.start(reader))
        reader.write(b"X" * 1100 + b"\n")
        self.assertIn("Command too long", reader.readline().decode())
        self.assertTrue(self.command(reader, "ANSWER 1 B").startswith("OK:"))
        self.assertIn("Score=1/5", self.command(reader, "SUBMIT"))
        sock.close()

    def test_deadline_automatically_finalizes_and_scores_once(self):
        sock, reader, _ = self.connect("timer_student")
        self.assertIn("STARTED", self.start(reader))
        self.assertTrue(self.command(reader, "ANSWER 1 B").startswith("OK:"))
        time.sleep(2.2)
        result = reader.readline().decode().strip()
        self.assertIn("TIMEOUT:", result)
        self.assertIn("RESULT:", result)
        self.assertIn("Score=1/5", result)
        self.assertIn("Answered=1/5", result)
        self.assertEqual(reader.readline(), b"")
        sock.close()

    def test_timestamped_application_metrics_capture_outcomes(self):
        deadline = time.monotonic() + 2
        events = []
        while time.monotonic() < deadline:
            if self.metrics_path.exists():
                with self.metrics_path.open(newline="") as source:
                    events = list(csv.DictReader(source))
                if any(row["event"] == "timeout_finalized" for row in events):
                    break
            time.sleep(0.05)
        self.assertTrue(events)
        self.assertEqual(events[0].keys(), {
            "timestamp_utc", "student", "event", "latency_ms", "detail"
        })
        self.assertIn("answer", {row["event"] for row in events})
        self.assertIn("submitted", {row["event"] for row in events})
        self.assertIn("timeout_finalized", {row["event"] for row in events})
        self.assertTrue(all(row["timestamp_utc"].endswith("Z") for row in events))


if __name__ == "__main__":
    unittest.main(verbosity=2)
