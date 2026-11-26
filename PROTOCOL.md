# Upload experiment protocol v1

Frozen before measurement. The question is whether 64 KiB resumable chunks should replace whole-file retry by default in this explicitly synthetic workload. The unit of assignment and analysis is one simulated visitor, uploading one file once. Retries keep that visitor's ID.

| Scenario | Sessions | File | Link rate | Request latency | Interruption |
|---|---:|---:|---:|---:|---|
| Interrupted | 80 | 512 KiB | 600 KiB/s | 6 ms | Once at 70% logical file progress |
| Stable | 40 | 512 KiB | 2 MiB/s | 6 ms | None |
| Latency | 20 | 512 KiB | 2 MiB/s | 200 ms | None |
| Small | 20 | 32 KiB | 2 MiB/s | 6 ms | None |

The scenario list is shuffled with seed 52611 and assigned to identities after-disconnect-v1-000 through after-disconnect-v1-159 in order. Files are deterministic per identity. The advertised workload mix is a stress test, not an estimate of production traffic. Local engineering mode runs each identity once per strategy in alternating order without calling Flagsmith. Official mode instead evaluates the Flagsmith experiment flag once per identity with 50/50 allocation and executes only the assigned strategy. The four-identity smoke uses another identity namespace and a separate experiment. Demo clicks never emit experiment events.

Both strategies have a 1.25 s wall-clock deadline from strategy start until the client receives the final server verification, two additional attempts after failures, and 35 ms fixed retry delay. Rate and latency are emulated using paced writes on a real loopback HTTP connection. A planned outage truncates one request body; the server discards partial requests, keeping only complete acknowledged chunks. Transfer bytes refer to application payload bytes sent, excluding HTTP headers. SHA-256 is recomputed by the server over the assembled bytes. Each server-completed, matching digest that returns within the deadline produces one upload_verified_on_time conversion. Expiry, exhausted retries and digest mismatch score zero. Client setup and experiment network calls are outside the transfer timer.

Primary endpoint: proportion of assigned identities with a verified upload by the deadline. Report counts, denominators and absolute percentage-point difference. Read the Flagsmith win probability and credible interval when available. Secondary observations are payload bytes and latency. For latency comparisons disclose completion and censoring. The stricter rollout rule is an observed improvement of at least 5 percentage points overall, a positive lower bound on the overall difference interval and no more than 5 percentage points observed harm in any no-interruption scenario. Otherwise hold the global flag. Report the predeclared scenarios as diagnostics with their sample sizes. A targeted rollout is a follow-up when estimates are uncertain. No benchmark is restarted or extended to improve its result.

Run eight independent uploads at most concurrently (default four). If infrastructure fails after enrollment, retain the partial ledger and enrollment journal; keep any fresh attempt on a separate experiment. Independently reconcile local successes against official conversion and exposure counts. Report discrepancies before making a rollout claim.
