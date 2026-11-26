"""HTTP contract for the release demo. SDK tests use a local read-only flag feed."""

import contextlib
import http.client
import importlib.util
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from unittest.mock import patch

from upload_lab import Gallery, LocalServer, receiver


@contextlib.contextmanager
def serve(server):
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    try:
        yield server.server_address
    finally:
        server.shutdown()
        thread.join()


def post(address, body):
    connection = http.client.HTTPConnection(*address, timeout=5)
    try:
        connection.request("POST", "/api/release-check", json.dumps(body),
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


class FlagFeed(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.calls.append((self.command, self.path))
        data = json.dumps([{"feature": {"id": 1, "name": "lab_flag"},
                            "feature_state_value": self.server.value,
                            "enabled": self.server.enabled}]).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.server.calls.append((self.command, self.path))
        self.send_error(405)

    def log_message(self, *_):
        pass


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.resources = contextlib.ExitStack()
        self.addCleanup(self.resources.close)
        self.requests = []
        backend = self.resources.enter_context(receiver(self.requests.append))
        gallery = self.resources.enter_context(LocalServer(("127.0.0.1", 0), Gallery))
        gallery.receiver = backend
        gallery.demo_slots = threading.BoundedSemaphore(4)
        self.address = self.resources.enter_context(serve(gallery))

    def test_unconfigured_and_invalid(self):
        with patch.dict(os.environ, {}, clear=True):
            status, data = post(self.address, {"scenario": "stable"})
        self.assertEqual((status, data["status"]), (503, "unavailable"))
        self.assertEqual(post(self.address, {"scenario": "unknown"})[0], 400)
        self.assertEqual(self.requests, [])

    @unittest.skipUnless(importlib.util.find_spec("flagsmith"), "install requirements.txt for SDK wire test")
    def test_every_check_reads_environment_and_executes_only_selected_strategy(self):
        feed = self.resources.enter_context(LocalServer(("127.0.0.1", 0), FlagFeed))
        feed.calls = []
        host, port = self.resources.enter_context(serve(feed))
        settings = {"FLAGSMITH_ENVIRONMENT": "test-environment-key",
                    "FLAGSMITH_API_URL": f"http://{host}:{port}", "AFTERDROP_RELEASE_FLAG": "lab_flag"}
        with patch.dict(os.environ, settings, clear=True):
            expected_hash = None
            for value, strategy, count in [("control", "whole", 1), ("resume", "resume", 8)]:
                feed.value, feed.enabled = value, True
                start = len(self.requests)
                status, data = post(self.address, {"scenario": "stable"})
                self.assertEqual((status, data["strategy"]), (200, strategy))
                receipt = data["receipt"]
                self.assertTrue(receipt["success"])
                self.assertEqual(receipt["sha256"], receipt["expected_sha256"])
                self.assertEqual(len(self.requests) - start, count)
                self.assertEqual(receipt["sha256"], self.requests[-1]["sha256"])
                if expected_hash:
                    self.assertEqual(receipt["sha256"], expected_hash)
                expected_hash = receipt["sha256"]

            start = len(self.requests)
            feed.enabled = False
            status, data = post(self.address, {"scenario": "stable"})
            self.assertEqual((status, data["status"], data["receipt"]), (200, "disabled", None))
            feed.value, feed.enabled = "unexpected", True
            status, data = post(self.address, {"scenario": "stable"})
            self.assertEqual((status, data["status"]), (503, "unavailable"))
            self.assertEqual(len(self.requests), start)
        self.assertEqual(feed.calls, [("GET", "/api/v1/flags/")] * 4)
