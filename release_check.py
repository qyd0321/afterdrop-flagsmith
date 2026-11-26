"""Read the environment's current upload flag using the official Flagsmith SDK."""

import os
from pathlib import Path


class ReleaseUnavailable(Exception):
    """A message safe to show to the local reviewer."""


def released_strategy():
    """Read a fresh environment default. No identity, exposure or conversion is sent."""
    try:
        from flagsmith import Flagsmith
        from flagsmith.exceptions import FlagsmithClientError
        from requests import RequestException
        from urllib3.util.retry import Retry
    except ImportError as exc:
        raise ReleaseUnavailable("Install the project requirements to check the live flag.") from exc

    names = ("FLAGSMITH_ENVIRONMENT", "FLAGSMITH_ENVIRONMENT_KEY", "FLAGSMITH_API_URL",
             "AFTERDROP_RELEASE_FLAG")
    settings = {k: os.environ[k] for k in names if k in os.environ}
    env_file = os.environ.get("AFTERDROP_ENV_FILE")
    if env_file:
        try:
            for line in Path(env_file).read_text(encoding="utf-8-sig").splitlines():
                key, separator, value = line.strip().removeprefix("export ").partition("=")
                if separator and key.strip() in names:
                    settings.setdefault(key.strip(), value.strip().strip("\"'"))
        except (OSError, UnicodeError) as exc:
            raise ReleaseUnavailable("The local Flagsmith settings file could not be read.") from exc
    environment = settings.get("FLAGSMITH_ENVIRONMENT") or settings.get("FLAGSMITH_ENVIRONMENT_KEY")
    if not environment:
        raise ReleaseUnavailable("Set AFTERDROP_ENV_FILE or FLAGSMITH_ENVIRONMENT on the lab server.")
    name = settings.get("AFTERDROP_RELEASE_FLAG", "afterdrop_upload_v2")
    origin = settings.get("FLAGSMITH_API_URL", "").rstrip("/")
    options = {"api_url": origin + "/api/v1/"} if origin and origin != "https://api.flagsmith.com" else {}
    sdk = Flagsmith(environment_key=environment, enable_events=False, enable_analytics=False,
                    retries=Retry(total=0), request_timeout_seconds=3, **options)
    try:
        flag = sdk.get_environment_flags().get_flag(name)
    except (FlagsmithClientError, RequestException, ValueError) as exc:
        raise ReleaseUnavailable("Flagsmith could not return the configured release flag. Check the instance and environment.") from exc
    finally:
        sdk.close()
        sdk.session.close()
    if not flag.enabled:
        return {"status": "disabled", "flag": name, "strategy": None, "receipt": None}
    if flag.value not in ("control", "resume"):
        raise ReleaseUnavailable("The release flag has an unsupported value. Use control or resume.")
    return {"status": "executed", "flag": name, "value": flag.value,
            "strategy": "whole" if flag.value == "control" else "resume"}
