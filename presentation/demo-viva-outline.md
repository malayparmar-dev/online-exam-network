# Final Demonstration and Viva Outline

Use the [standalone demo and verification playbook](../docs/demo-and-verification-playbook.md) for setup, exact manual commands, automated counterparts, and validation status. The [README live-demo walkthrough](../README.md#step-by-step-live-demonstration) is a shorter version. The order below separates interactive behavior from the automated network experiment.

## Interactive live demo

1. **Introduce the design:** Explain the C TCP client/server, thread-per-client sessions, newline-framed protocol, two-switch/four-host Mininet topology, and the controller's OpenFlow role.
2. **Build and run basic checks:** From the repository root, run `make` and `make test`.
3. **Start the controller and topology:** In separate terminals, run `./scripts/start_controller.sh` and `./scripts/start_topology.sh`. In Mininet, run `pingall` and point out the hosts, switches, and shared 5 Mbps inter-switch link.
4. **Start the exam server:** At `mininet>`, run `server ./server > /tmp/exam-server-demo.log 2>&1 &`.
5. **Show simultaneous student sessions:** At `mininet>`, run `xterm h1 h2`. In both host terminals, run `./client 10.0.0.10`, enter different student IDs, start, answer, navigate, and submit. Show each independent result. An optional `xterm h3` demonstrates an additional client.
6. **Show controller status:** In an ordinary host terminal, run `printf 'STATUS\n' | nc 127.0.0.1 8765`. Identify the connected switches, threshold, and active block list.
7. **Show manual policy and recovery:** Send `BLOCK 10.0.0.1`, run pings from h1 and h2 in Mininet, then send `UNBLOCK 10.0.0.1` and repeat h1's ping. Explain that the full automated test also checks exam TCP denial, unaffected h2 exam completion, and h1 exam recovery.
8. **Cleanly end the interactive demo:** Close the xterm clients, type `exit` at `mininet>`, and stop the controller with Ctrl+C.

## Automated network demonstration

After the manual topology has exited, authenticate sudo in the terminal used to run the test and launch:

```bash
sudo -v
./scripts/run_network_validation.sh
```

This runs scripted connectivity, exam TCP policy, automatic blocking, recovery, and performance checks. It prints a summary and saves a report; it does not display a person interactively answering exam questions. The latest run reports h1 baseline RTT of 19.572 ms and loaded average RTT of 302.447 ms, plus three simultaneous h1/h2 throughput trials with Jain fairness of 1.0000 each. These measurements describe the configured Mininet topology only; the report records source hashes for the tested working tree.

For a short non-network demo, use two terminals with `./scripts/run_app.sh server` and `./scripts/run_app.sh client 127.0.0.1`.

## Explain and qualify the evidence

- The server owns the authoritative exam deadline and final score. The client does not display a live countdown; timeout is enforced by the server.
- The controller collects flow statistics, applies a configurable source packet-rate rule, and allows manual blocking and recovery.
- Student IDs are not authentication. Rate-based blocking may flag legitimate traffic, metrics are local CSV, and the prototype is not production exam software.
- Cite the latest successful `results/network_validation_*.txt` report and its recorded environment. Mininet results are not physical-network performance claims.

## Likely viva questions

- Why does TCP require explicit message framing?
- How does the server keep each student's answers and timer independent?
- Why is the deadline measured with a monotonic clock?
- Which OpenFlow entries are installed, and how do flow counters become packet rates?
- What distinguishes the shared cross-switch path from h3's same-switch path?
- What evidence demonstrates recovery and that another client is unaffected?
- Why can the threshold classify valid traffic incorrectly?
- What would be needed for persistent exam records, authentication, and deployment security?
