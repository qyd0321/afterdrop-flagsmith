"""Create a private, local Flagsmith lab for the Afterdrop experiment."""

import argparse
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path(os.environ.get("AFTERDROP_STATE_DIR", ROOT / ".local" / "flagsmith-host"))
PORT = int(os.environ.get("AFTERDROP_PORT", "18711"))
if not 1 <= PORT <= 65535:
    raise ValueError("AFTERDROP_PORT must be a valid local TCP port.")
ORIGIN = f"http://127.0.0.1:{PORT}"


def write_private(path, value):
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as stream:
        stream.write(value)
    os.replace(stream.name, path)


def compose_secrets():
    path = PRIVATE / "local.env"
    if not path.exists():
        names = ("DB_PASSWORD", "SIGNING_SECRET", "WAREHOUSE_SECRET")
        write_private(path, "".join(f"AFTERDROP_{name}={secrets.token_hex(32)}\n" for name in names))
    print(f"Ready: {path}")


def connect():
    state = PRIVATE / "context.json"
    context = json.loads(state.read_text()) if state.exists() else {"base_url": ORIGIN}
    if context["base_url"] != ORIGIN:
        raise SystemExit("This helper supports the local Compose lab only.")
    opener = build_opener(ProxyHandler({}))

    def api(path, data=None):
        headers = {"Content-Type": "application/json"}
        if "admin_token" in context:
            headers["Authorization"] = "Token " + context["admin_token"]
        body = json.dumps(data).encode() if data is not None else None
        with opener.open(Request(ORIGIN + path, headers=headers, data=body), timeout=30) as res:
            return json.load(res)

    def checkpoint(**values):
        context.update(values)
        write_private(state, json.dumps(context, indent=2) + "\n")

    until = time.monotonic() + 240
    while True:
        try:
            version = api("/version/")
            break
        except (OSError, ValueError):
            if time.monotonic() >= until:
                raise SystemExit("The local API did not start. Check docker compose logs.")
            time.sleep(2)
    if "admin_token" not in context:
        if version.get("self_hosted_data", {}).get("has_users") is not False:
            raise SystemExit("The instance already has users or did not report a fresh database.")
        email = "demo-admin@example.invalid"
        password = secrets.token_urlsafe(32)
        user = api("/api/v1/auth/users/", {"email": email, "password": password, "re_password": password,
                   "first_name": "Demo", "last_name": "Operator", "superuser": True})
        checkpoint(admin_token=user["key"], email=email, password=password)
    if "organisation_id" not in context:
        checkpoint(organisation_id=api("/api/v1/organisations/", {"name": "Afterdrop"})["id"])
    if "project_id" not in context:
        project = api("/api/v1/projects/", {"name": "Afterdrop", "organisation": context["organisation_id"]})
        checkpoint(project_id=project["id"])
    if "environment_key" not in context:
        env = api("/api/v1/environments/", {"name": "Experiment Lab", "project": context["project_id"]})
        checkpoint(environment_id=env["id"], environment_key=env["api_key"])
    if "admin_api_key" not in context:
        keys = f"/api/v1/organisations/{context['organisation_id']}/master-api-keys/"
        checkpoint(admin_api_key=api(keys, {"name": "Experiment CLI", "is_admin": True})["key"])
    warehouses = f"/api/v1/environments/{context['environment_key']}/warehouse-connections/"
    page = api(warehouses)
    rows = page if isinstance(page, list) else page["results"]
    connection = rows[0] if rows else api(warehouses, {"warehouse_type": "postgres",
                                                      "config": {"source": "flagsmith_database"}})
    if connection["status"] != "connected":
        raise SystemExit(f"Warehouse status: {connection['status']}")
    checkpoint(warehouse_status="connected")
    settings = {
        "FLAGSMITH_API_URL": ORIGIN,
        "FLAGSMITH_SDK_API_URL": ORIGIN,
        f"FLAGSMITH_API_KEY_127_0_0_1_{PORT}": context["admin_api_key"],
        "FLAGSMITH_PROJECT": str(context["project_id"]),
        "FLAGSMITH_ORGANISATION": str(context["organisation_id"]),
        "FLAGSMITH_ENVIRONMENT": context["environment_key"],
    }
    write_private(PRIVATE / "experiment.env", "".join(f"{k}={v}\n" for k, v in settings.items()))
    print(f"Warehouse connected. Set AFTERDROP_ENV_FILE to {PRIVATE / 'experiment.env'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["secrets", "connect"])
    args = parser.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    if args.action == "secrets":
        compose_secrets()
    else:
        connect()
