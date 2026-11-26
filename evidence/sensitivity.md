# Where does resuming stop helping?

The original A/B run placed the disconnect at 70%. The following secondary **paired transport** check changes two conditions independently. Every cell contains four generated files per strategy, each 512 KiB on a 600 KiB/s paced link. Entries show **whole-file / resume** successes out of four, within the same 1.25 s deadline. Each pair used identical bytes. All 72 transfers are included.

| Request delay | No interruption | Drop at 20% of the file | Drop at 70% of the file |
|---|---:|---:|---:|
| 6 ms | 4 / 4 | 4 / 4 | 0 / 4 |
| 35 ms | 4 / 4 | **4 / 0** | 0 / 0 |
| 90 ms | **4 / 0** | 0 / 0 | 0 / 0 |

A late interruption on the fast-acknowledging link rewarded checkpoints. Just changing the same file's fault to an early interruption and setting request delay to 35 ms let all four whole-file retries finish and caused all four resumable transfers to time out. At 90 ms a stable transfer completed more reliably with the whole-file strategy. Several cells timed out under both strategies. A connection's history of dropping out alone is insufficient to choose a transfer policy from these data.

This was a post-experiment engineering check on the same host and implementation. It supplies no extra Flagsmith identities, independent customers or basis to claim a validated optimum. The table's 20% is **file position**; the browser's traffic-mix slider measures **the fraction of visitors on one network profile**. [Design](sensitivity-protocol.md) · [72 measured transfers](sensitivity.csv) · [Main A/B results](report.md)
