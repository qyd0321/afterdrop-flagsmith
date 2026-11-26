# Afterdrop

**Track** — Test Something Real

**Tagline** — Break a file upload at 70%. Watch it recover. Then discover when recovery makes things worse.

## Project description

Should a team enable resumable uploads by default? Afterdrop puts that release decision behind a Flagsmith multivariate flag. It compares whole-file retry with serial 64 KiB checkpoints. The upload server hashes the assembled file, and a visitor converts only if the verified acknowledgement arrives within 1.25 seconds.

We ran a real Flagsmith experiment with 160 simulated visitors across four network profiles. Resume improved verified on-time completion from 38/83 to 68/77. On a stable high-latency link, whole-file retry completed 11/11 and resume completed 0/9. We ended the experiment and kept control as the default under the guardrail in our written protocol.

Judges can break the connection, inspect receipt hashes, vary the assumed traffic mix and check the actual released flag through the SDK. A separate transport check finds that even an interrupted file can favor whole-file retry. We retained the instrumentation failure from our first full run and reconciled every conversion in the final one.

## Quick review

Start with the [short working demo](afterdrop-demo.mp4), the [results](../evidence/report.md) and the [one-command interactive lab](../README.md). The README includes instructions for a fresh self-hosted experiment. The repository uses synthetic identities and generated files. No customer data or commercial service account is required.
