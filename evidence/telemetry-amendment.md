# Instrumentation amendment before experiment 3

Experiment 2 enrolled the prespecified 160 visitors, but the SDK reported dropping buffered events. The upload ledger has 75 control and 85 resume assignments. Flagsmith counted 63 and 81 exposures, respectively. The results from that experiment are ineligible for the release decision.

Keep the complete experiment 2 evidence. End it before opening a separate experiment. Use the same sample size, identity plan, workload, timing, endpoint, transfer code and release thresholds. Change only telemetry delivery: allocate room for 128 buffered events and wait for the official SDK flush after each exposure and conversion, outside the transfer timer. Use the next complete experiment only if its warehouse counts reconcile with the upload and server records. No past events are backfilled.
