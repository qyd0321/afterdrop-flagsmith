# Afterdrop experiment 3

**Release decision: keep whole-file retry as the default.** Resume raised on-time verified completion by **42.5 percentage points** across this synthetic workload. On a stable link with 200 ms of request latency, every resumable upload missed its deadline. The prespecified guardrail rules out a global release.

| Network profile | Whole-file retry | 64 KiB resume | Difference |
|---|---:|---:|---:|
| All assigned visitors | 38/83 (45.8%) | 68/77 (88.3%) | +42.5 pp |
| One disconnect at 70% | 0/45 | 35/35 | +100 pp |
| Stable link | 17/17 | 23/23 | 0 pp |
| Stable, 200 ms per request | 11/11 | 0/9 | −100 pp |
| Small file | 10/10 | 10/10 | 0 pp |

**What Flagsmith measured.** A 50/50 multivariate flag assigned each of 160 stable simulated identities once. Each identity sent one file under its assigned strategy. A conversion required an acknowledgement of the final SHA-256 match within 1.25 seconds. Flagsmith reported a relative lift of **92.9%**, a **95% interval of +44.8% to +141.0%** on relative lift, and **99.992% chance to win**. The interval and probability apply to this traffic mix. The platform returned a null sample-ratio-mismatch statistic. See the [raw platform response](platform.json) and [reconciliation](reconciliation.json).

**Why the rankings reverse.** The interrupted link gives a whole-file retry too little time to retransmit the acknowledged prefix. With 64 KiB checkpoints the receiver can keep the complete chunks. On the stable high-latency link the 512 KiB file takes eight serial requests: eight 200 ms request delays already exceed the 1.25 s budget before any file bytes move. That effect follows from this implementation's serial acknowledgements and deadline. A different chunk size or pipelining policy deserves a separate experiment.

**Case mix matters.** Chance placed 45 interrupted transfers in control and 35 in resume. Standardizing both arms to the frozen 50% interrupted, 25% stable, 12.5% latency and 12.5% small mix yields 50.0% versus 87.5%, or +37.5 points. This descriptive sensitivity check keeps the high-latency finding intact. These are four intentionally selected stress profiles, with a single shared machine and a known deterministic disconnect. The experiment measures implementational behavior under those conditions and does not estimate how often customers experience them.

**What shipped.** The completed experiment retained control with weight zero for resume in the competition environment. Both choices are inspectable in the [release record](release.json). A next experiment could measure a larger chunk size or select a strategy using pre-upload link measurements. No production targeting policy has been validated.

## Trace one upload

**Protocol provenance.** The original study used the written decision rule in [the protocol](../PROTOCOL.md). The earliest Git commit containing that document postdates the end of experiment 3. We have no independently timestamped public preregistration for the original run. The subsequent clean-instance reproduction reused the archived protocol.

A follow-up crossed request delay with interruption point on a fixed-rate link. At 35 ms per request with an interruption at 20% of the file, whole-file retry finished 4/4 while resume finished 0/4. This post-experiment bench run uses the same transfer implementations and does not contribute to the platform totals. [All nine cells](sensitivity.md)

1. Choose an identity in the [session ledger](../results/official/sessions.csv). Its row contains the assigned strategy, scenario, sent bytes, client completion time and expected digest.
2. Find the same identity in the [receiver log](../results/official/server-receipts.jsonl). A short request returns 409 and cannot advance the acknowledged offset. A completed file has the digest computed over the received bytes.
3. Inspect the [enrolment journal](../results/official/enrollment.jsonl) for the exposure request and conversion. The independent audit recomputes the input hash, matches received payload bytes, checks elapsed time, and compares the resulting arm totals to the official occurrence metric.

The smoke run reconciled four exposures and two successes. A larger first attempt exposed a one-event SDK buffer losing telemetry under concurrency. We rejected its result, closed that experiment, and documented the [instrumentation amendment](telemetry-amendment.md) before the fresh run. Experiment 3 used the original workload, metric, sample size and decision thresholds. The final audit reconciled all **160 assigned identities and 106 verified successes**. The [paired engineering benchmark](../results/local/summary.json) used no platform assignments and is reported separately.
