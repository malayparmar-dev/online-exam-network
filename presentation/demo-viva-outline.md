# Final Demonstration and Viva Outline

Use this as a short live-demo sequence; fill in performance values from the latest successful network-validation report before presenting.

1. **Problem and design:** Explain the TCP exam service, thread-per-client model, newline-framed protocol, Mininet topology, and separation between the application server and SDN controller.
2. **Reproducible setup:** Show the Ubuntu prerequisites, pinned OS-Ken requirements, `make`, and `make test` from a clean checkout.
3. **Application flow:** Start the controller and Mininet, launch the server on the `server` host, then run clients on h1/h2 with separate IDs. Demonstrate question navigation, changing an answer, submitting, and receiving the score.
4. **Concurrency and timer:** Show the recorded application metrics and the acceptance checks for concurrent isolated sessions and automatic timer finalization.
5. **SDN monitoring and action:** Show controller `STATUS`, the flow-rate threshold, controlled high-rate traffic, the automatic source-IP block, continued h2 connectivity, and h1 recovery after `UNBLOCK`.
6. **Congestion and results:** Show repeated cross-switch/same-switch baseline values and the cross-switch value under concurrent shared-link load. State the test duration, configured rates/delays, number of samples, and that the results are from Mininet.
7. **Limitations:** Explain that student IDs are not authentication, the traffic threshold is a lab policy with possible false positives, metrics are local CSV, and the prototype is not production exam software.

## Likely viva questions

- Why does TCP require explicit message framing?
- How does the server keep each student's answers and timer independent?
- Why is the deadline measured with a monotonic clock?
- Which OpenFlow entries are installed, and how do flow counters become packet rates?
- What distinguishes the shared cross-switch path from h3's same-switch path?
- What evidence demonstrates recovery and that another client is unaffected?
- Why can the threshold classify valid traffic incorrectly?
- What would be needed for persistent exam records, authentication, and deployment security?
