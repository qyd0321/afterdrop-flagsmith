"""Compare the Flagsmith occurrence metric to independently audited transfers."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from audit_run import validate


def reconcile(folder, snapshot, release=None):
    audit = validate(folder)
    if audit["mode"] != "flagsmith":
        raise ValueError("Platform reconciliation requires a Flagsmith-assigned run.")
    platform = json.loads(snapshot.read_text(encoding="utf-8-sig"))
    results = platform["results"]
    if not results or not results["as_of"] or results["last_error_at"]:
        raise ValueError("No successful Flagsmith results snapshot.")
    metric, = results["payload"]["metrics"]
    stats = metric["variants"]
    if set(stats) - {"control", "resume"}:
        raise ValueError("Unexpected variation in the occurrence metric.")
    for variant, strategy in [("control", "whole"), ("resume", "resume")]:
        group = stats.get(variant, {"n": 0, "sum": 0})
        if (group["n"] != audit["assigned"].get(strategy, 0) or
                group["sum"] != audit["on_time_and_verified"].get(strategy, 0)):
            raise ValueError(f"{variant} platform counts disagree with independently verified receipts")
    report = {**audit, "experiment_id": platform["experiment_id"],
              "platform_as_of": results["as_of"], "platform_agrees": True}
    if release is not None:
        state = json.loads(release.read_text(encoding="utf-8-sig"))
        flag = state["flag"]
        if not (results["is_final"] is True and state["status"] == "completed"
                and platform["experiment_id"] == state["id"]
                and platform["name"] == "Afterdrop / " + flag["feature"]
                and datetime.fromisoformat(results["as_of"].replace("Z", "+00:00"))
                >= datetime.fromisoformat(state["ended_at"].replace("Z", "+00:00"))):
            raise ValueError("Snapshot is not final or does not match the completed release.")
        if not (state["rollout_decision"] == "control" and flag["value"] == "control"
                and flag["enabled"] is True and flag["segment_overrides"] == flag["identity_overrides"] == 0
                and flag["variants"] and all(v["weight"] == 0 for v in flag["variants"])):
            raise ValueError("Release does not retain global control as recorded.")
        report["verified_rollout"] = "control"
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("platform", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--release", type=Path, help="also verify the completed hold-control deployment")
    args = parser.parse_args()
    text = json.dumps(reconcile(args.folder, args.platform, args.release), indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
