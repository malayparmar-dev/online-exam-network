#!/usr/bin/env python3

"""Mininet topology and repeatable SDN/network validation experiment."""

import argparse
import json
import os
import statistics
import subprocess
import time

from performance_metrics import average_ping_ms, jain_fairness_index

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo


OPENFLOW_PORT = int(os.getenv("EXAM_OPENFLOW_PORT", "6653"))
CONTROL_PORT = int(os.getenv("EXAM_CONTROL_PORT", "8765"))
SERVER_IP = "10.0.0.10"


class ExamTopology(Topo):
    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")

        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        h3 = self.addHost("h3", ip="10.0.0.3/24")
        server = self.addHost("server", ip=f"{SERVER_IP}/24")

        self.addLink(h1, s1, cls=TCLink, bw=10, delay="2ms")
        self.addLink(h2, s1, cls=TCLink, bw=10, delay="2ms")
        self.addLink(h3, s2, cls=TCLink, bw=10, delay="2ms")
        self.addLink(server, s2, cls=TCLink, bw=10, delay="2ms")
        self.addLink(s1, s2, cls=TCLink, bw=5, delay="5ms")


def controller_request(command):
    import socket

    with socket.create_connection(("127.0.0.1", CONTROL_PORT), timeout=2) as sock:
        sock.settimeout(2)
        sock.sendall((command + "\n").encode())
        sock.shutdown(socket.SHUT_WR)
        response = bytearray()
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
        return response.decode(errors="replace").strip()


def receiver_mbps(output, label):
    try:
        result = json.loads(output)
        summary = result["end"].get("sum_received") or result["end"]["sum"]
        return summary["bits_per_second"] / 1_000_000
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Could not parse {label} iperf3 JSON output: {output[-500:]}"
        ) from exc


def wait_process(process, label, timeout=3):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)
    info(f"*** Stopped experiment process: {label}\n")


def run(batch=False):
    topo = ExamTopology()
    net = Mininet(
        topo=topo,
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
        build=False,
    )

    net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=OPENFLOW_PORT,
    )
    net.build()
    net.start()

    info("\n*** Examination SDN network started\n")
    info(f"*** Controller: 127.0.0.1:{OPENFLOW_PORT}\n")
    info("*** Host links: 10 Mbps, 2 ms delay\n")
    info("*** Inter-switch link: 5 Mbps, 5 ms delay\n")
    info("*** Hosts: h1, h2, h3, server\n")
    info("*** Switches: s1, s2\n\n")

    try:
        if not batch:
            CLI(net)
            return

        info("*** Running automated batch tests\n")
        controller_ready = False
        for _ in range(20):
            try:
                status = controller_request("STATUS")
                if "Connected switches: 2" in status:
                    controller_ready = True
                    break
            except OSError:
                pass
            time.sleep(1)
        if not controller_ready:
            raise RuntimeError("Controller did not report two connected switches")

        info("*** Running SDN policy test\n")
        policy = subprocess.run(
            ["python3", "scripts/test_sdn_policy.py"],
            capture_output=True,
            text=True,
            timeout=35,
            check=False,
        )
        info(policy.stdout)
        if policy.stderr:
            info(policy.stderr)
        if policy.returncode != 0:
            raise RuntimeError("SDN policy test failed")

        dropped = net.pingAll()
        info(f"*** Connectivity packet loss: {dropped:.1f}%\n")
        server = net.get("server")
        h1 = net.get("h1")
        h2 = net.get("h2")
        h3 = net.get("h3")

        # Exercise the actual C exam application across the OpenFlow topology,
        # not only synthetic iperf traffic. Both client processes are started
        # before either result is collected to cover concurrent TCP sessions.
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_metrics = f"/tmp/exam-mininet-metrics-{time.time_ns()}.csv"
        exam_server = server.popen(
            [os.path.join(project_root, "server")],
            env={
                **os.environ,
                "EXAM_PORT": "8080",
                "EXAM_DURATION_SECONDS": "30",
                "EXAM_METRICS_FILE": app_metrics,
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            time.sleep(0.5)
            if exam_server.poll() is not None:
                server_output = exam_server.stdout.read()
                raise RuntimeError(
                    "Mininet exam server exited during startup: "
                    + server_output[-500:]
                )

            app_attempts = [
                (h1, f"net_h1_{time.time_ns() % 1000000000}",
                 "START\n1\nB\nS\nYES\n", "Score=1/5"),
                (h2, f"net_h2_{time.time_ns() % 1000000000}",
                 "START\nS\nYES\n", "Score=0/5"),
            ]
            app_clients = []
            for host, student_id, answers, expected_score in app_attempts:
                client = host.popen(
                    [os.path.join(project_root, "client"), SERVER_IP, "8080"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                app_clients.append(
                    (client, student_id, answers, expected_score, host.name)
                )

            for client, student_id, answers, _, _ in app_clients:
                client.stdin.write(student_id + "\n" + answers)
                client.stdin.close()

            for client, student_id, _, expected_score, host_name in app_clients:
                try:
                    client.wait(timeout=10)
                except subprocess.TimeoutExpired as exc:
                    wait_process(client, f"{host_name} exam client")
                    raise RuntimeError(
                        f"Mininet exam client on {host_name} timed out"
                    ) from exc
                output = client.stdout.read()
                if client.returncode != 0 or (
                    f"RESULT: Student={student_id}" not in output
                    or expected_score not in output
                ):
                    raise RuntimeError(
                        f"Mininet exam client on {host_name} failed: "
                        + output[-700:]
                    )
                info(
                    f"*** Mininet exam result {host_name}: "
                    f"{student_id} {expected_score}\n"
                )
            info("*** Mininet exam application passed for two TCP clients\n")
        finally:
            wait_process(exam_server, "Mininet examination server")

        iperf_server = server.popen(
            ["iperf3", "-s", "-p", "5202"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)

        def run_iperf(host, label, duration=3, port=5202):
            output = host.cmd(
                "iperf3 -c " + SERVER_IP + " -p " + str(port) +
                " -t " + str(duration) + " -J"
            )
            value = receiver_mbps(output, label)
            info(f"*** {label}: receiver {value:.3f} Mbps\n")
            return value

        def run_exam_client(host, student_id, answers, timeout=8):
            client = host.popen(
                ["timeout", str(timeout - 1),
                 os.path.join(project_root, "client"), SERVER_IP, "8080"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                output, _ = client.communicate(
                    input=student_id + "\n" + answers,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                wait_process(client, f"{host.name} exam client")
                raise RuntimeError(
                    f"Exam client on {host.name} did not exit"
                ) from exc
            return client.returncode, output

        cross_samples = [
            run_iperf(h1, f"h1 baseline run {i + 1}") for i in range(3)
        ]
        local_samples = [
            run_iperf(h3, f"h3 baseline run {i + 1}") for i in range(3)
        ]
        baseline_rtt_ms = average_ping_ms(
            h1.cmd(
                "ping -n -q -i 0.2 -c 10 " + SERVER_IP
            ),
            "h1 baseline",
        )
        info(f"*** h1 baseline average RTT: {baseline_rtt_ms:.3f} ms\n")

        # iperf3's server accepts only one test at a time. Use a second server
        # port so h1 and h2 can generate concurrent, comparable shared-link load.
        concurrent_server = server.popen(
            ["iperf3", "-s", "-p", "5204"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            time.sleep(1)
            fairness_samples = []
            congested_cross_samples = []
            concurrent_load_samples = []
            loaded_rtt_samples = []
            for trial in range(3):
                ping = h1.popen(
                    ["ping", "-n", "-q", "-i", "0.2", "-c", "30", SERVER_IP],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                h1_load = None
                h2_load = None
                try:
                    h1_load = h1.popen(
                        ["iperf3", "-c", SERVER_IP, "-p", "5202",
                         "-t", "6", "-J"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    h2_load = h2.popen(
                        ["iperf3", "-c", SERVER_IP, "-p", "5204",
                         "-t", "6", "-J"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    h1_output, _ = h1_load.communicate(timeout=9)
                    h2_output, _ = h2_load.communicate(timeout=9)
                    ping_output, _ = ping.communicate(timeout=9)
                    if h1_load.returncode != 0:
                        raise RuntimeError(
                            "Concurrent h1 traffic failed: " + h1_output[-500:]
                        )
                    if h2_load.returncode != 0:
                        raise RuntimeError(
                            "Concurrent h2 traffic failed: " + h2_output[-500:]
                        )
                    h1_mbps = receiver_mbps(
                        h1_output, f"h1 concurrent trial {trial + 1}"
                    )
                    h2_mbps = receiver_mbps(
                        h2_output, f"h2 concurrent trial {trial + 1}"
                    )
                    if h1_mbps <= 0 or h2_mbps <= 0:
                        raise RuntimeError(
                            "A concurrent TCP flow reported no receiver traffic"
                        )
                    fairness = jain_fairness_index([h1_mbps, h2_mbps])
                    rtt_ms = average_ping_ms(
                        ping_output, f"concurrent trial {trial + 1}"
                    )
                    congested_cross_samples.append(h1_mbps)
                    concurrent_load_samples.append(h2_mbps)
                    fairness_samples.append(fairness)
                    loaded_rtt_samples.append(rtt_ms)
                    info(
                        f"*** Concurrent trial {trial + 1}: "
                        f"h1={h1_mbps:.3f} Mbps, h2={h2_mbps:.3f} Mbps, "
                        f"Jain fairness={fairness:.4f}, "
                        f"h1 average RTT={rtt_ms:.3f} ms\n"
                    )
                finally:
                    wait_process(h1_load, "concurrent h1 TCP client")
                    wait_process(h2_load, "concurrent h2 TCP client")
                    wait_process(ping, "concurrent h1 ping probe")

            congested_cross = statistics.mean(congested_cross_samples)
            congestion_load = statistics.mean(concurrent_load_samples)
            fairness_mean = statistics.mean(fairness_samples)
            loaded_rtt_mean_ms = statistics.mean(loaded_rtt_samples)
        finally:
            wait_process(concurrent_server, "concurrent h2 iperf3 server")

        baseline_cross = statistics.mean(cross_samples)
        baseline_local = statistics.mean(local_samples)
        info(
            "*** Measured Mbps: "
            f"cross-switch baseline mean={baseline_cross:.3f}, "
            f"same-switch baseline mean={baseline_local:.3f}, "
            f"cross-switch under load={congested_cross:.3f}\n"
        )

        udp_server = server.popen(
            ["iperf3", "-s", "-1", "-p", "5203"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        flood = None
        policy_exam_server = None
        try:
            policy_exam_server = server.popen(
                [os.path.join(project_root, "server")],
                env={
                    **os.environ,
                    "EXAM_PORT": "8080",
                    "EXAM_DURATION_SECONDS": "30",
                    "EXAM_METRICS_FILE": (
                        f"/tmp/exam-mininet-policy-{time.time_ns()}.csv"
                    ),
                },
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            time.sleep(0.5)
            if policy_exam_server.poll() is not None:
                raise RuntimeError("Mininet exam server failed before policy test")

            time.sleep(0.5)
            flood = h1.popen(
                ["iperf3", "-c", SERVER_IP, "-p", "5203", "-u",
                 "-b", "20M", "-l", "64", "-t", "12"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            auto_block_detected = False
            for _ in range(50):
                status = controller_request("STATUS")
                if "Automatically blocked IPs: 10.0.0.1" in status:
                    auto_block_detected = True
                    break
                if flood.poll() is not None:
                    break
                time.sleep(0.25)

            if not auto_block_detected:
                raise RuntimeError(
                    "Automatic block did not trigger; controller status:\n" +
                    controller_request("STATUS")
                )
            info("*** Automatic block detected for h1\n")

            # Stop the high-rate source before testing recovery. Otherwise its
            # still-running packets can immediately trigger a second block
            # after UNBLOCK and make the application recovery check ambiguous.
            wait_process(flood, "high-rate UDP client")
            flood = None
            wait_process(udp_server, "UDP iperf3 server")
            udp_server = None
            time.sleep(2.5)

            unaffected = h2.cmd("ping -c 2 -W 1 10.0.0.10")
            if "0% packet loss" not in unaffected:
                raise RuntimeError(
                    "Unaffected h2 lost connectivity while h1 was blocked"
                )
            blocked_client = h1.cmd("ping -c 2 -W 1 10.0.0.10")
            if "100% packet loss" not in blocked_client:
                raise RuntimeError("Blocked h1 still reached the examination server")

            blocked_status, blocked_output = run_exam_client(
                h1,
                f"blocked_h1_{time.time_ns() % 1000000000}",
                "START\nS\nYES\n",
                timeout=5,
            )
            if blocked_status == 0 or "RESULT:" in blocked_output:
                raise RuntimeError(
                    "SDN block did not deny h1's exam TCP connection"
                )
            info("*** SDN block denied h1 exam TCP connection\n")

            unaffected_status, unaffected_output = run_exam_client(
                h2,
                f"unaffected_h2_{time.time_ns() % 1000000000}",
                "START\nS\nYES\n",
            )
            if unaffected_status != 0 or "Score=0/5" not in unaffected_output:
                raise RuntimeError(
                    "h2 could not complete an exam while h1 was blocked: "
                    + unaffected_output[-500:]
                )
            info("*** h2 exam TCP session succeeded while h1 was blocked\n")

            unblock_response = controller_request("UNBLOCK 10.0.0.1")
            if not unblock_response.startswith("OK: Unblocked 10.0.0.1"):
                raise RuntimeError(
                    "Could not remove automatic block: " + unblock_response
                )
            time.sleep(0.5)
            recovered = h1.cmd("ping -c 2 -W 1 10.0.0.10")
            if "0% packet loss" not in recovered:
                raise RuntimeError("h1 did not recover connectivity after unblocking")
            recovered_status, recovered_output = run_exam_client(
                h1,
                f"recovered_h1_{time.time_ns() % 1000000000}",
                "START\n1\nB\nS\nYES\n",
            )
            if recovered_status != 0 or "Score=1/5" not in recovered_output:
                raise RuntimeError(
                    "h1 could not complete an exam after unblock: "
                    + recovered_output[-500:]
                )
            info(
                "*** Automatic block isolated h1's exam TCP traffic; "
                "h2 unaffected; h1 recovered\n"
            )
        finally:
            if flood is not None:
                wait_process(flood, "high-rate UDP client")
            wait_process(udp_server, "UDP iperf3 server")
            if policy_exam_server is not None:
                wait_process(policy_exam_server, "policy exam server")

        if dropped > 0:
            raise RuntimeError("Connectivity test reported packet loss")

        performance = {
            "baseline_cross_switch_mbps": round(baseline_cross, 3),
            "baseline_same_switch_mbps": round(baseline_local, 3),
            "congested_cross_switch_mbps": round(congested_cross, 3),
            "concurrent_h2_load_mbps": round(congestion_load, 3),
            "response_time_baseline_avg_ms": round(baseline_rtt_ms, 3),
            "response_time_under_load_avg_ms": round(loaded_rtt_mean_ms, 3),
            "response_time_under_load_samples_ms": [
                round(v, 3) for v in loaded_rtt_samples
            ],
            "concurrent_h1_samples_mbps": [
                round(v, 3) for v in congested_cross_samples
            ],
            "concurrent_h2_samples_mbps": [
                round(v, 3) for v in concurrent_load_samples
            ],
            "jain_fairness_samples": [round(v, 4) for v in fairness_samples],
            "jain_fairness_mean": round(fairness_mean, 4),
            "baseline_cross_samples_mbps": [round(v, 3) for v in cross_samples],
            "baseline_same_samples_mbps": [round(v, 3) for v in local_samples],
            "automatic_block_detected": auto_block_detected,
            "unaffected_client_connected": "0% packet loss" in unaffected,
            "recovery_confirmed": "0% packet loss" in recovered,
            "blocked_exam_tcp_denied": blocked_status != 0,
            "unaffected_exam_tcp_succeeded": unaffected_status == 0,
            "recovered_exam_tcp_succeeded": recovered_status == 0,
        }
        info("PERFORMANCE_JSON " + json.dumps(performance, sort_keys=True) + "\n")
        info("*** BATCH TESTS PASSED\n")
        wait_process(iperf_server, "TCP iperf3 server")
    finally:
        net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Online examination SDN topology")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="run automated policy, connectivity, performance and recovery tests",
    )
    arguments = parser.parse_args()
    setLogLevel("info")
    run(batch=arguments.batch)
