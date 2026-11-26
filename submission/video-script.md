# Afterdrop · English video script

Running time: 70 seconds. Spoken narration uses the Windows Microsoft Zira voice. Lab and read-only SDK footage was captured during local HTTP transfers. The two Flagsmith dashboard frames show the completed experiment.

| Time | Picture | Narration |
|---|---|---|
| 0–5 s | Recorded release decision and aggregate rates | Checkpoints nearly doubled timely uploads in our Flagsmith test. We kept them off by default. |
| 5–8 s | Open the paired upload lab | Here's what changed that decision. |
| 8–15 s | Single-drop comparison in progress | Two clients send the same file. At seventy percent, both connections drop at exactly the same byte. |
| 15–19 s | Live deadlines and receipts | The receiver kept the confirmed chunks. Only the resumable upload finished on time. |
| 19–21 s | Select the high-latency profile | Now try a stable link. |
| 21–28 s | Second pair of live uploads | Each request takes two hundred milliseconds to acknowledge. Eight checkpoint requests consume the entire deadline. |
| 28–33 s | Completed high-latency comparison | This time only the whole file passed. Every success requires a matching server digest. |
| 33–40 s | Completed Flagsmith dashboard | For the recorded experiment, Flagsmith assigned each of one hundred sixty simulated visitors to one strategy. |
| 40–47 s | Official arm-level results | Thirty-eight of eighty-three control uploads and sixty-eight of seventy-seven resumable uploads finished on time. |
| 47–54 s | Profile counts and rollout guardrail | But on the high-latency link, whole-file retry won eleven of eleven. Resume won zero of nine. |
| 54–59 s | Live SDK check form | We retained control. Let's check the released flag with a fresh upload. |
| 59–63 s | Run the released strategy | The official SDK reads the current flag from Flagsmith. |
| 63–70 s | New SDK evaluation and verified receiver digest | Control selected whole-file retry. This fresh server receipt verifies that choice without adding a visitor to the experiment. |
