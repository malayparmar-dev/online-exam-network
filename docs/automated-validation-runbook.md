# Automated Setup and Validation Runbook

This guide takes a clean Ubuntu checkout from system prerequisites through the automated application, controller, and Mininet validation commands. It describes automated checks only; for person-operated demonstrations, use the [manual demo runbook](manual-demo-runbook.md).

The official project requirements and marks are mapped to implementation and evidence in the [rubric traceability matrix](rubric-traceability.md).

## 1. Choose the validation level

| Level | What it checks | Mininet / sudo needed? |
|---|---|---|
| Build and application tests | C build, protocol framing, exam behavior, concurrency, timer, metrics, and performance-metric helpers | No |
| Controller control test | Starts a temporary OS-Ken controller and tests its local control interface | No Mininet or sudo; OS-Ken environment required |
| Full network validation | Mininet topology, OpenFlow connectivity, exam TCP, SDN policy, automatic blocking, recovery, throughput, RTT, and fairness | Yes; Mininet, Open vSwitch, OS-Ken, `iperf3`, and sudo authorization required |
| GitHub Actions | Build/application tests, Python syntax, pinned OS-Ken setup, and controller test on Ubuntu 24.04 | No Mininet; the workflow does not run the privileged full network validation |

## 2. Install Ubuntu system prerequisites

Use Ubuntu with Python 3.12 or newer. Install the system packages from an administrator account:

```bash
sudo apt update
sudo apt install build-essential mininet openvswitch-switch python3 python3-venv iperf3
sudo systemctl start openvswitch-switch
```

Check that the tools are available:

```bash
gcc --version
make --version
python3 --version
mn --version
ovs-vsctl --version
iperf3 --version
systemctl is-active openvswitch-switch
```

The application/controller checks do not need a graphical desktop. The manual xterm demonstration is described separately and requires `xterm` and a working desktop display.

## 3. Clone or enter the project

For a fresh checkout, choose a directory name that does not already exist:

```bash
git clone https://github.com/malayparmar-dev/online-exam-network.git ~/online-exam-network-clean-check
cd ~/online-exam-network-clean-check
```

If you already have the project, skip the clone and enter that checkout instead:

```bash
cd ~/online-exam-network
```

Confirm the branch and revision before recording results:

```bash
git status --short --branch
git rev-parse HEAD
```

The project scripts locate their own repository root, so the checkout does not need to be in a fixed path.

## 4. Create the controller environment and build

From the repository root, create the pinned OS-Ken environment and compile the client/server:

```bash
python3 -m venv .venv-sdn
.venv-sdn/bin/python -m pip install --upgrade pip
.venv-sdn/bin/python -m pip install -r requirements-sdn.txt
make
```

The application uses system C tools. OS-Ken is installed into `.venv-sdn`; the Mininet topology is launched with the system Python so it can import Ubuntu's Mininet packages.

## 5. Run non-privileged automated checks

Run the C protocol, application, and performance-metric tests:

```bash
make test
```

This builds the C programs and checks protocol framing, exam questions and scoring, navigation and answer replacement, invalid input, quit, concurrent sessions, duplicate IDs, slow handshakes, timer finalization, application metrics, RTT parsing, and Jain fairness calculation.

Run the controller control-interface test:

```bash
make test-controller
```

This launches a temporary OS-Ken controller, checks status and configuration, tests fragmented and invalid requests, verifies server-IP protection, and exercises block/unblock. It uses ephemeral localhost ports and does not start Mininet.

Check Python syntax:

```bash
python3 -m py_compile src/topology.py src/performance_metrics.py sdn/exam_controller.py scripts/*.py tests/*.py
```

To run those application/controller checks through the project orchestrator without the network experiment:

```bash
./scripts/run_all.sh --app-only
```

## 6. Run full Mininet, SDN, and performance validation

Ensure Open vSwitch is active and no manual Mininet topology is currently running. In one terminal, authenticate sudo and start the run:

```bash
sudo -v
./scripts/run_network_validation.sh
```

The runner starts its own controller when both controller ports are free. If both ports already have a controller, it reuses that controller and leaves it running. If only one port is occupied, it stops rather than altering the partial setup. It creates and cleans up its own Mininet topology.

The full run checks:

1. Controller startup and two connected OpenFlow switches.
2. Automated controller-policy checks.
3. Mininet host connectivity and concurrent C exam clients.
4. Baseline cross-switch and same-switch throughput.
5. Concurrent shared-link throughput, RTT, and Jain fairness trials.
6. Traffic-triggered source blocking, blocked exam TCP denial, unaffected-client operation, and recovery after unblock.

Expected success evidence includes `BATCH TESTS PASSED`, an `Automatic block detected for h1` line, a `PERFORMANCE_JSON` record, and `Result: NETWORK VALIDATION PASSED`.

The run creates a dated summary such as `results/network_validation_YYYYMMDD_HHMMSS.txt` and a detailed raw log named with `_raw.log`. The summary includes the checkout revision and measurements; inspect the report itself before citing any results.

## 7. Run all automated checks in one command

After completing setup and ensuring no manual topology is running, authenticate sudo in the same terminal and run:

```bash
sudo -v
./scripts/run_all.sh
```

This runs `make test`, Python syntax checks, the controller test when `.venv-sdn` is present, and then the full network validation. For application/controller checks only, use `./scripts/run_all.sh --app-only` as shown above; it does not need sudo or Mininet.

## 8. Read and preserve results

Use [`results/README.md`](../results/README.md) to identify the latest successful tracked network report and distinguish it from historical, failed, or partial runs. The current authoritative saved run is [`network_validation_20261025_150625.txt`](../results/network_validation_20261025_150625.txt). Its measurements apply to the recorded Mininet topology only, not to physical production networks.

New timestamped reports and raw logs are generated locally. Check their Git status before assuming they are part of GitHub; `.gitignore` excludes most generated reports and all raw logs. Preserve a new report in Git only if it is a selected result worth retaining, and update `results/README.md` so the repository identifies its provenance and status.

## 9. GitHub Actions scope

The workflow at `.github/workflows/application-tests.yml` runs on pushes and pull requests. It installs the C build tools, runs `make test`, checks Python syntax, installs `requirements-sdn.txt` into `.venv-sdn`, and runs `make test-controller` on Ubuntu 24.04. It does not run the full Mininet test because that requires a privileged network environment. A green workflow therefore verifies the application/controller checks, not the full SDN traffic experiment.

## 10. Diagnose a failed network run

- If the report says sudo authorization is unavailable, run `sudo -v` in the same terminal and retry.
- If OS-Ken is missing, repeat Section 4 and confirm `.venv-sdn/bin/osken-manager` exists.
- If only one controller port is occupied, inspect the running controller before retrying; the runner intentionally refuses to change a partial controller setup.
- On failure, the summary names the raw log and includes its final output lines. Keep both files locally while diagnosing the failure.
- Do not combine measurements from different run dates or topology settings. Compare the Git revision, environment, topology configuration, and report status first.

