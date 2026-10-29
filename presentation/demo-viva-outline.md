# Final Demonstration and Viva Outline

This file is the short presentation outline, not a command reference. For exact terminal commands and expected behavior, use the [manual demo runbook](../docs/manual-demo-runbook.md). The [README](../README.md) is the project entry point; the [final report](../report/final-project-report.md) and [results index](../results/README.md) contain the recorded implementation and experiment evidence.

## Suggested demonstration order

1. **State the problem and design.** Explain that students take an exam through concurrent TCP client/server sessions, while an SDN controller manages the Mininet network.
2. **Show an exam session.** Start an exam, change an answer, navigate questions, submit, and explain the returned score. If time allows, show a second independent client.
3. **Explain robustness.** Describe the server-side deadline, duplicate active-ID handling, and isolated per-client session state. Show the timer or quit behavior if requested.
4. **Show SDN integration.** Identify the hosts and switches, show controller status, block one client, compare it with an unaffected client, then unblock and show recovery.
5. **Show dynamic behavior.** Generate the controlled traffic scenario and explain how the packet-rate rule blocks the source and how recovery works after the traffic stops and the source is unblocked.
6. **Present performance evidence.** Compare the no-competing-traffic baseline with simultaneous shared-link TCP flows. Explain throughput, ping RTT, and Jain fairness results; these are measurements of the emulated Mininet topology.
7. **Close with reproducibility and limits.** Point to the setup, tests, source, configuration, and saved report. State that the measurements do not represent a physical production network and that student IDs are not authentication.

The runbook labels which manual sections have been verified. Do not present a manual step as personally rehearsed until its status is updated with observed results.

## Automated demonstration

If asked for repeatable measurements, point to the automated network validation described in [README Section 10](../README.md#10-testing-and-performance-evaluation). It runs after the interactive topology is closed and produces a saved report; it does not show a person interacting with the exam client. Cite only the latest successful report listed in [`results/README.md`](../results/README.md), and distinguish its batch results from the manual UI walkthrough.

## Likely viva questions

- Why does TCP need application-level message framing?
- How does the server isolate each student's answers and timer?
- Why does the server enforce the deadline?
- How do OpenFlow flow counters inform the traffic-rate rule?
- How do the cross-switch and same-switch paths differ?
- Which evidence shows that a blocked student is isolated and can recover?
- Why can a packet-rate rule block legitimate traffic?
- What would be needed for authentication, persistent records, and production security?
