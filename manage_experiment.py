"""Create or inspect the dedicated Afterdrop experiment via the official CLI v2."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from flagsmith_experiment import load_settings


def cli(*args, body=None):
    executable = os.environ.get("FLAGSMITH_CLI") or shutil.which("flagsmith")
    if not executable and Path(".local/tools/flagsmith.exe").exists():
        executable = str(Path(".local/tools/flagsmith.exe").resolve())
    if not executable:
        raise SystemExit("Install Flagsmith CLI v2 or set FLAGSMITH_CLI.")
    command = [executable, *args, "--json", "--no-input"]
    if body is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(command, input=json.dumps(body) if body is not None else None,
                            text=True, encoding="utf-8", capture_output=True, timeout=60)
    if result.returncode:
        # Diagnostics may contain the SDK key in an environment-specific URL.
        message = result.stderr
        for name, value in os.environ.items():
            if name.startswith("FLAGSMITH_") and value:
                message = message.replace(value, "[setting]")
        raise SystemExit(message.strip() or "Flagsmith CLI failed")
    return json.loads(result.stdout) if result.stdout.strip() else None


def items(page):
    if isinstance(page, list):
        return page
    if page.get("next"):
        raise ValueError("Use a dedicated environment with a single page of Afterdrop resources.")
    return page["results"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["setup", "refresh", "read", "hold-control"])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    load_settings()
    env = os.environ.get("FLAGSMITH_ENVIRONMENT") or os.environ["FLAGSMITH_ENVIRONMENT_KEY"]
    os.environ["FLAGSMITH_ENVIRONMENT"] = env
    base = "api/v1/environments/" + env + "/"
    flag = os.environ.get("AFTERDROP_FLAG", "afterdrop_upload_v1")
    title = "Afterdrop / " + flag

    def api(path, method="GET", body=None):
        return cli("api", base + path, "-X", method, body=body)

    experiments = items(api("experiments/"))
    experiment = next((r for r in experiments if r["name"] == title), None)
    if args.operation == "setup":
        if not any(c.get("status") == "connected" for c in items(api("warehouse-connections/"))):
            raise SystemExit("Connect the experiment event warehouse in this environment first.")
        if experiment is None:
            features = items(cli("feature", "list"))
            if not any(f["name"] == flag for f in features):
                cli("feature", "create", flag, "--value", "control", "--enabled")
            feature = cli("feature", "get", flag)
            if not any(v.get("key") == "resume" for v in feature.get("variants", [])):
                cli("feature", "variant", "add", flag, "--value", "resume", "--key", "resume", "--weight", "0")
            feature = cli("feature", "get", flag)
            variant = next(v for v in feature["variants"] if v["key"] == "resume")
            event = "upload_verified_on_time"
            metric = next((m for m in items(api("experiment-metrics/")) if m["name"] == event), None)
            if metric is None:
                metric = api("experiment-metrics/", "POST", {
                    "name": event, "aggregation": "occurrence", "direction": "up",
                    "definition": {"version": 1, "event": event}})
            if (metric["aggregation"] != "occurrence" or metric["direction"] != "up"
                    or metric["definition"].get("event") != event):
                raise SystemExit("Existing same-name metric has a different definition. Use a fresh environment.")
            experiment = api("experiments/", "POST", {
                "feature": feature["id"], "name": title,
                "hypothesis": "Resuming at acknowledged chunks increases verified on-time completion under the fixed workload.",
                "metrics": [{"metric": metric["id"], "expected_direction": "increase"}],
                "experiment_rollout": {"enabled": True, "rollout_percentage": 100,
                    "feature_state_value": {"type": "string", "value": "control"},
                    "multivariate_feature_state_values": [{"multivariate_feature_option": variant["id"],
                                                          "percentage_allocation": 50}]}})
        if experiment["status"] in {"created", "draft"}:
            experiment = api(f"experiments/{experiment['id']}/start/", "POST")
        if experiment["status"] != "running":
            raise SystemExit(f"Cannot reuse experiment in state {experiment['status']}")
        data = {"experiment_id": experiment["id"], "name": title, "status": experiment["status"]}
    else:
        if experiment is None:
            raise SystemExit("No matching experiment. Run setup first.")
        endpoint = f"experiments/{experiment['id']}/"
        if args.operation == "hold-control":
            if experiment["status"] != "completed":
                api(endpoint + "complete/", "POST", {"rollout_decision": "control"})
            state = api(endpoint)
            if state["status"] != "completed" or state["rollout_decision"] != "control":
                raise SystemExit("Flagsmith did not complete this experiment with a control rollout.")
        path = endpoint + "results/"
        if args.operation == "refresh":
            api(path + "refresh/", "POST")
        data = {"experiment_id": experiment["id"], "name": title, **api(path)}
    result = json.dumps(data, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result + "\n", encoding="utf-8")
    print(result)


if __name__ == "__main__":
    main()
