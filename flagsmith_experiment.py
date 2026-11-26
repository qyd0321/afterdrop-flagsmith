"""Afterdrop's binding to the official Flagsmith Experimentation Python SDK."""

import os
from pathlib import Path

from flagsmith import EventProcessorConfig, Flagsmith


def load_settings():
    """Optionally read a private, local KEY=value file without executing it."""
    path = os.environ.get("AFTERDROP_ENV_FILE")
    if path:
        for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip().removeprefix("export ")
            if line and not line.startswith("#"):
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


class ExperimentClient:
    def __init__(self):
        load_settings()
        key = os.environ.get("FLAGSMITH_ENVIRONMENT") or os.environ["FLAGSMITH_ENVIRONMENT_KEY"]
        self.feature = os.environ.get("AFTERDROP_FLAG", "afterdrop_upload_v1")
        origin = os.environ.get("FLAGSMITH_API_URL", "").rstrip("/")
        options = {}
        events = {"max_buffer_items": 128}
        if origin and origin != "https://api.flagsmith.com":
            options["api_url"] = origin + "/api/v1/"
            events["events_api_url"] = origin + "/api/"
        self.sdk = Flagsmith(environment_key=key, enable_events=True,
                             event_processor_config=EventProcessorConfig(**events), **options)

    def assign(self, identity):
        flag = self.sdk.get_experiment_flag(self.feature, identifier=identity)
        if not flag.enabled or not flag.experiment or not flag.experiment.in_experiment:
            raise RuntimeError("Flagsmith did not enrol this identity. Check the active rollout.")
        if flag.variant != flag.value or flag.variant not in {"control", "resume"}:
            raise RuntimeError("Unexpected Flagsmith variation. Check both variation keys and values.")
        self.sdk.flush_events()
        return {"control": "whole", "resume": "resume"}[flag.variant]

    def convert(self, identity):
        self.sdk.track_event("upload_verified_on_time", identifier=identity)
        self.sdk.flush_events()
