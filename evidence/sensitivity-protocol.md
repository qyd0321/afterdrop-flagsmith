# Transport sensitivity check

This secondary bench check was designed after reading experiment 3. It tests whether the release story survives earlier disconnections and intermediate round-trip costs. No identities or events enter Flagsmith. Its data does not change experiment 3 or its release rule.

Hold file size at 512 KiB, payload rate at 600 KiB/s, checkpoint size at 64 KiB, client deadline at 1.25 seconds and retry delay at 35 ms. Cross request delay (6, 35, 90 ms) with interruption (none, once at 20%, once at 70%). Each cell has four matched, deterministic files. Run profiles in seeded shuffled order (314159), sequentially, alternating which strategy goes first within each cell. Retain all 72 transfers, whether they succeed or time out. Count on-time, hash-verified acknowledgements in each cell. These replicates expose local timing variability and do not estimate customer demand.

Reproduce with `python sensitivity.py .local/sensitivity-repeat.csv`. The supplied input to the public result is [the original ledger](sensitivity.csv).
