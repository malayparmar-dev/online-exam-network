#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info
import argparse
import re


class ExamTopology(Topo):
    def build(self):
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")

        h1 = self.addHost("h1", ip="10.0.0.1/24")
        h2 = self.addHost("h2", ip="10.0.0.2/24")
        h3 = self.addHost("h3", ip="10.0.0.3/24")
        server = self.addHost("server", ip="10.0.0.10/24")

        # Host-facing links: 10 Mbps, 2 ms delay.
        self.addLink(h1, s1, cls=TCLink, bw=10, delay="2ms")
        self.addLink(h2, s1, cls=TCLink, bw=10, delay="2ms")
        self.addLink(h3, s2, cls=TCLink, bw=10, delay="2ms")
        self.addLink(server, s2, cls=TCLink, bw=10, delay="2ms")

        # Shared inter-switch bottleneck: 5 Mbps, 5 ms delay.
        self.addLink(s1, s2, cls=TCLink, bw=5, delay="5ms")


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
        port=6653,
    )

    net.build()
    net.start()

    info("\n*** Examination SDN network started\n")
    info("*** Controller: 127.0.0.1:6653\n")
    info("*** Host links: 10 Mbps, 2 ms delay\n")
    info("*** Inter-switch link: 5 Mbps, 5 ms delay\n")
    info("*** Hosts: h1, h2, h3, server\n")
    info("*** Switches: s1, s2\n\n")

    try:
        if batch:
            import socket
            import subprocess
            import sys
            import time

            info("*** Running automated batch tests\\n")

            # Wait until the controller confirms both switches are connected.
            controller_ready = False
            for _ in range(20):
                try:
                    with socket.create_connection(("127.0.0.1", 8765), timeout=2) as sock:
                        sock.sendall(b"STATUS\n")
                        status = sock.recv(4096).decode(errors="replace")
                    if "Connected switches: 2" in status:
                        controller_ready = True
                        break
                except OSError:
                    pass
                time.sleep(1)

            if not controller_ready:
                raise RuntimeError("Controller did not report two connected switches")

            # Test SDN policy while Mininet is active.
            info("*** Running SDN policy test\\n")
            policy = subprocess.run(
                [sys.executable, "scripts/test_sdn_policy.py"],
                capture_output=True,
                text=True,
                timeout=35,
            )
            info(policy.stdout)
            if policy.stderr:
                info(policy.stderr)

            if policy.returncode != 0:
                raise RuntimeError("SDN policy test failed")

            # Connectivity test.
            dropped = net.pingAll()
            info(f"*** Connectivity packet loss: {dropped:.1f}%\\n")

            # Run separate throughput tests to the server.
            server = net.get("server")
            h1 = net.get("h1")
            h3 = net.get("h3")

            def run_iperf(host, label):
                server.cmd("pkill -x iperf3 2>/dev/null || true")
                server.cmd("iperf3 -s -1 -p 5202 >/tmp/exam_iperf_server.log 2>&1 &")
                import time
                time.sleep(1)
                output = host.cmd("iperf3 -c 10.0.0.10 -p 5202 -t 5")
                info(f"\\n*** {label} throughput test\\n{output}\\n")
                return output

            out_h1 = run_iperf(h1, "h1 (cross-switch)")
            out_h3 = run_iperf(h3, "h3 (same-switch)")

            if dropped > 0:
                raise RuntimeError("Connectivity test reported packet loss")

            if "receiver" not in out_h1 or "receiver" not in out_h3:
                raise RuntimeError("Could not verify both iperf receiver results")

            info("*** BATCH TESTS PASSED\\n")
        else:
            CLI(net)
    finally:
        net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Online examination SDN topology")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="run automated connectivity and throughput tests, then exit",
    )
    args = parser.parse_args()

    setLogLevel("info")
    run(batch=args.batch)
