# Official Project Statement and Rubric Traceability

This matrix follows the project statement and detailed evaluation rubric supplied by the student. It does not adopt requirements from the older v2 blueprint.

| Official criterion | Project evidence | Verification |
|---|---|---|
| Problem understanding and architecture (2) | `README.md`, `docs/architecture.md` | Architecture and demo walkthrough |
| TCP/UDP socket implementation (4) | `src/client.c`, `src/server.c`, `src/protocol.c` | `make test`; UDP is used only to generate controlled network load, while the exam application uses TCP as specified |
| Mininet + SDN implementation (4) | `src/topology.py`, `sdn/exam_controller.py`, startup scripts | `scripts/run_network_validation.sh` |
| Socket–SDN integration (3) | TCP exam traffic traverses OVS; controller observes flow counters and can block the source host | Latest validation run: h1 exam TCP denied while auto-blocked, h2 completed an exam, and h1 completed an exam again after unblock |
| Initial testing and demo (2) | `tests/`, GitHub Actions, this repository's README | `make test`, then interactive Mininet procedure in README |
| Complete application functionality (4) | Multi-threaded server, independent answer arrays/deadlines, five questions, answer changes, scoring, result and timeout finalization | `make test` covers protocol, concurrency, identity isolation, answer replacement, scoring, deadline, and metrics |
| Dynamic SDN functionality (6) | Flow statistics, configurable rate threshold, manual block/unblock, automatic source block, unaffected client and recovery | `scripts/run_network_validation.sh` |
| Challenging scenario / robustness (4) | Shared-link congestion experiment, malformed protocol input, slow handshake, per-source blocking and recovery | App acceptance tests plus Mininet batch |
| Performance evaluation and comparison (5) | Repeated baseline cross-switch and same-switch throughput samples; synchronized h1/h2 shared-link trials; baseline and loaded ICMP RTT; Jain throughput fairness index | Metric unit tests and successful Mininet run in `results/network_validation_20261025_150625.txt`; report records source-file hashes because the run used uncommitted working-tree changes |
| Documentation, final demo and viva (6) | README setup/runbook, architecture, reproducibility, this matrix, demo outline, and `docs/demo-and-verification-playbook.md` | Fresh-clone setup, step-by-step manual demonstration, feature-to-test mapping, and automated commands |

## Evidence rules

- Application verification is the unprivileged `make test` suite, which runs from a fresh source checkout with GCC, Make, and Python 3.
- SDN, congestion, and automatic-block requirements are not verified by the application suite. They require Mininet, Open vSwitch, OS-Ken, `iperf3`, and sudo permission.
- A network result is evidence only when the report says `BATCH TESTS PASSED` and contains a `PERFORMANCE_JSON` record. Failed or skipped runs must remain identified as such. The latest successful result, including response-time and fairness measurements, is `results/network_validation_20261025_150625.txt`.
- Record the Git revision, OS/Python/Mininet/Open vSwitch/OS-Ken versions, topology settings, and all measured values. Do not present Mininet values as physical-network results.
