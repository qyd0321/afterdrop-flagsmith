"""Independently check the upload ledger against its design, receipts and events."""

import argparse
import csv
import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


def records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]


def require(condition, description):
    if not condition:
        raise ValueError(description)


def validate(directory):
    with (directory / "sessions.csv").open(encoding="utf8", newline="") as file:
        sessions = list(csv.DictReader(file))
    journal = records(directory / "enrollment.jsonl")
    metadata = json.loads((directory / "summary.json").read_text(encoding="utf8"))
    official = metadata["mode"] == "flagsmith"
    require(metadata["mode"] in ("flagsmith", "local") and type(metadata["smoke"]) is bool,
            "unknown run mode or smoke status")
    scenarios = ["interrupted"] * 80 + ["stable"] * 40 + ["latency"] * 20 + ["small"] * 20
    random.Random(52611).shuffle(scenarios)
    prefix = "after-disconnect-v1"
    if metadata["smoke"]:
        prefix = "after-disconnect-smoke"
        scenarios = ["interrupted", "stable", "latency", "small"]
    design = {f"{prefix}-{i:03d}": scenario for i, scenario in enumerate(scenarios)}
    expected_ids = Counter({key: 1 if official else 2 for key in design})
    require(Counter(s["identity"] for s in sessions) == expected_ids, "cohort size/identity mismatch")
    require(len({(s["identity"], s["strategy"]) for s in sessions}) == len(sessions), "duplicate assignment")
    conversions = Counter()
    totals = Counter()
    successes = Counter()
    digests = {}
    by_assignment = {(s["identity"], s["strategy"]): s for s in sessions}
    for session in sessions:
        uid, arm = session["identity"], session["strategy"]
        require(arm in {"whole", "resume"} and design[uid] == session["scenario"], uid + " assignment")
        size = 32768 if design[uid] == "small" else 524288
        expected = hashlib.sha256(random.Random(uid).randbytes(size)).hexdigest()
        require(expected == session["expected_sha256"] and int(session["size_bytes"]) == size, uid + " file mismatch")
        require(float(session["deadline_ms"]) == 1250, uid + " deadline")
        verified = int(session["confirmed_bytes"]) == size and session["sha256"] == expected
        require((session["verified"] == "True") == verified, uid + " digest")
        elapsed = float(session.get("elapsed_ms_exact") or session["elapsed_ms"])
        require(math.isfinite(elapsed) and elapsed >= 0 and abs(elapsed - float(session["elapsed_ms"])) <= 0.006,
                uid + " inconsistent elapsed time")
        success = verified and elapsed <= 1250
        require(success == (session["success"] == "True"), uid + " endpoint")
        totals[arm] += 1
        if success:
            successes[arm] += 1
            conversions[uid] += 1
        if verified:
            digests[(uid, arm)] = expected
    observed = [r for r in journal if r["event"] == "observed"]
    require(Counter((r["identity"], r["strategy"]) for r in observed) == Counter(by_assignment.keys()),
            "journal and CSV assignments disagree")
    for record in observed:
        session = by_assignment[record["identity"], record["strategy"]]
        require(all(field in record and value == ("" if record[field] is None else str(record[field]))
                    for field, value in session.items()), "journal observation and CSV disagree")
    if official:
        events_by_identity = defaultdict(list)
        for entry in journal:
            require(entry["identity"] in design, "unknown identity in enrolment journal")
            if "scenario" in entry:
                require(entry["scenario"] == design[entry["identity"]], "journal scenario differs")
            events_by_identity[entry["identity"]].append(entry["event"])
        for uid in design:
            expected_sequence = ["assigning", "assigned", "observed"]
            if conversions[uid]:
                expected_sequence.append("converted")
            require(events_by_identity[uid] == expected_sequence, f"event sequence differs for {uid}")
        require(Counter((r["identity"], r["strategy"]) for r in journal if r["event"] == "assigned")
                == Counter((s["identity"], s["strategy"]) for s in sessions), "assignment journal mismatch")
        require(Counter(r["identity"] for r in journal if r["event"] == "converted") == conversions,
                "SDK conversion calls disagree with verified receipts")
    receipts_path = directory / "server-receipts.jsonl"
    if official or receipts_path.is_file():
        receipts = records(receipts_path)
        wire_by_session = Counter()
        offsets = Counter()
        for receipt in receipts:
            key = receipt["identity"], receipt["strategy"]
            require(key in by_assignment, "receipt for unknown assignment")
            session = by_assignment[key]
            offset, declared, received = receipt["offset"], receipt["declared_bytes"], receipt["received_bytes"]
            capacity = int(session["size_bytes"])
            require(0 <= received <= declared and 0 < declared <= capacity - offset and offset >= 0,
                    f"invalid request bounds for {key}")
            old = offsets[key]
            if receipt["status"] == 200:
                require(received == declared and (offset == old or offset + declared <= old),
                        f"invalid accepted range for {key}")
                offsets[key] = max(old, offset + declared)
            else:
                require(receipt["status"] == 409, f"unexpected receiver response for {key}")
            require(receipt["confirmed"] == offsets[key], f"acknowledgement differs for {key}")
            expected_digest = session["expected_sha256"] if offsets[key] == capacity else None
            require(receipt["sha256"] == expected_digest and receipt["verified"] is (expected_digest is not None),
                    f"receiver digest or verdict differs for {key}")
            wire_by_session[key] += receipt["received_bytes"]
        for s in sessions:
            key = s["identity"], s["strategy"]
            require(wire_by_session[key] == int(s["wire_bytes"]), f"receiver byte count differs for {key}")
        acknowledged = {(r["identity"], r["strategy"]): r["sha256"] for r in receipts if r["sha256"]}
        for key, digest in digests.items():
            require(acknowledged.get(key) == digest, f"missing server digest for {key}")
        require(all(r["status"] != 200 or r["received_bytes"] == r["declared_bytes"] for r in receipts),
                "a short request was accepted")
        acknowledged_counts = len(acknowledged)
    else:
        acknowledged_counts = None
    for scenario in ("overall", *set(scenarios)):
        for arm in ("whole", "resume"):
            rows = [s for s in sessions if s["strategy"] == arm and
                    (scenario == "overall" or s["scenario"] == scenario)]
            times = [float(s["elapsed_ms"]) for s in rows if s["success"] == "True"]
            group = metadata["groups"][scenario][arm]
            expected_group = {"n": len(rows), "successes": len(times),
                              "success_rate": len(times) / len(rows) if rows else None,
                              "median_elapsed_success_only_ms": median(times) if times else None,
                              "payload_bytes_sent": sum(int(s["wire_bytes"]) for s in rows)}
            require(group == expected_group, f"saved summary differs for {scenario}/{arm}")
    return {"mode": metadata["mode"], "sessions_checked": len(sessions), "assigned": dict(totals),
            "on_time_and_verified": dict(successes), "server_assembled_files": acknowledged_counts,
            "sdk_conversions_requested": sum(conversions.values()) if official else 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path)
    print(json.dumps(validate(parser.parse_args().results_dir), indent=2))
