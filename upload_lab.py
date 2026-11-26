"""Real loopback HTTP upload testbed for After Disconnect. Python 3.10+, stdlib."""

import argparse
import contextlib
import csv
import hashlib
import http.client
import json
import queue
import random
import socket
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
KIB = 1024
CHUNK = 64 * KIB
BLOCK = 16 * KIB
DEADLINE = 1.25
BACKOFF = 0.035
MAX_RETRIES = 2
SCENARIOS = {
    "interrupted": (512 * KIB, 600 * KIB, 0.006, 0.70),
    "stable": (512 * KIB, 2048 * KIB, 0.006, None),
    "latency": (512 * KIB, 2048 * KIB, 0.200, None),
    "small": (32 * KIB, 2048 * KIB, 0.006, None),
}


@dataclass
class Upload:
    size: int
    expected: str
    identity: str = ""
    strategy: str = ""
    data: bytearray = field(default_factory=bytearray)
    received: int = 0
    digest: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


class Receiver(BaseHTTPRequestHandler):
    """Internal receiver. A truncated HTTP request can never commit its prefix."""

    def log_message(self, *_):
        pass

    def do_PUT(self):
        key = self.path.strip("/")
        with self.server.upload_lock:
            upload = self.server.uploads.get(key)
        if upload is None:
            return self.send_error(404)
        try:
            length = int(self.headers["Content-Length"])
            offset = int(self.headers["X-Offset"])
        except (TypeError, ValueError):
            return self.send_error(400)
        if not (0 < length <= upload.size and 0 <= offset <= upload.size - length):
            return self.send_error(400)
        self.connection.settimeout(10)
        body = self.rfile.read(length)
        with upload.lock:
            upload.received += len(body)
            if len(body) != length:
                status = 409
            elif offset == len(upload.data):
                upload.data.extend(body)
                status = 200
            elif offset + length <= len(upload.data) and upload.data[offset:offset + length] == body:
                status = 200
            else:
                status = 409
            if len(upload.data) == upload.size and upload.digest is None:
                upload.digest = hashlib.sha256(upload.data).hexdigest()
            response = {"confirmed": len(upload.data), "sha256": upload.digest,
                        "verified": upload.digest == upload.expected}
            if self.server.audit:
                self.server.audit({"identity": upload.identity, "strategy": upload.strategy,
                                   "offset": offset, "declared_bytes": length,
                                   "received_bytes": len(body), "status": status, **response})
        payload = json.dumps(response).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


class LocalServer(ThreadingHTTPServer):
    request_queue_size = 64
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


@contextlib.contextmanager
def receiver(audit=None):
    with LocalServer(("127.0.0.1", 0), Receiver) as server:
        server.daemon_threads = False
        server.uploads = {}
        server.upload_lock = threading.Lock()
        server.audit = audit
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            yield server
        finally:
            server.shutdown()
            worker.join()


class Deadline(Exception):
    pass


def transmit(server, identity, scenario, strategy, emit=None, pace=1, *, link_profile=None):
    size, rate, latency, fault = SCENARIOS[scenario] if link_profile is None else link_profile
    data = random.Random(identity).randbytes(size)
    expected = hashlib.sha256(data).hexdigest()
    key = uuid.uuid4().hex
    upload = Upload(size, expected, identity, strategy)
    with server.upload_lock:
        server.uploads[key] = upload
    confirmed = wire = attempts = failures = 0
    progress = 0
    acknowledged_digest = None
    dropped = False
    started = time.monotonic()
    limit = started + DEADLINE * pace

    def until(target):
        delay = min(target, limit) - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        if time.monotonic() >= limit:
            raise Deadline

    def update(event, **fields):
        if emit:
            emit({"strategy": strategy, "event": event, "confirmed_bytes": confirmed,
                  "progress_bytes": progress, "wire_bytes": wire, "size_bytes": size,
                  "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                  "attempt": attempts, "deadline_ms": round(DEADLINE * pace * 1000),
                  "expected_sha256": expected, **fields})

    reason = "deadline"
    update("start")
    try:
        while confirmed < size:
            length = size - confirmed if strategy == "whole" else min(CHUNK, size - confirmed)
            attempts += 1
            progress = confirmed
            until(time.monotonic() + latency * pace)
            connection = http.client.HTTPConnection(*server.server_address, timeout=max(0.001, limit - time.monotonic()))
            try:
                connection.putrequest("PUT", "/" + key)
                connection.putheader("Content-Length", str(length))
                connection.putheader("X-Offset", str(confirmed))
                connection.endheaders()
                cut = int(size * fault) if fault and not dropped else None
                truncate = cut is not None and confirmed < cut < confirmed + length
                end = cut if truncate else confirmed + length
                transfer_start = time.monotonic()
                while progress < end:
                    next_byte = min(end, progress + BLOCK)
                    until(transfer_start + (next_byte - confirmed) / rate * pace)
                    connection.send(data[progress:next_byte])
                    wire += next_byte - progress
                    progress = next_byte
                    update("progress")
                if truncate:
                    # Half-close at a byte boundary. The receiver sees a genuine short read
                    # against Content-Length and discards the incomplete request.
                    dropped = True
                    connection.sock.shutdown(socket.SHUT_WR)
                response = connection.getresponse()
                ack = json.loads(response.read())
                if truncate:
                    if response.status != 409 or ack["confirmed"] != confirmed:
                        raise RuntimeError("receiver committed a truncated body")
                    failures += 1
                    update("disconnect")
                    if failures > MAX_RETRIES:
                        reason = "retry_limit"
                        break
                    until(time.monotonic() + BACKOFF * pace)
                    continue
                if response.status != 200 or ack["confirmed"] != confirmed + length:
                    raise RuntimeError("invalid server acknowledgement")
                confirmed = ack["confirmed"]
                acknowledged_digest = ack["sha256"]
                if acknowledged_digest is not None and not ack["verified"]:
                    reason = "digest_mismatch"
                    break
                until(time.monotonic())
                update("progress")
            finally:
                connection.close()
        if confirmed == size:
            reason = "verified" if acknowledged_digest == expected else "digest_mismatch"
    except (Deadline, TimeoutError):
        reason = "deadline"
    finally:
        elapsed = (time.monotonic() - started) * 1000
        with server.upload_lock:
            server.uploads.pop(key, None)
    verified = acknowledged_digest == expected
    success = verified and elapsed <= DEADLINE * pace * 1000 and reason == "verified"
    if verified and not success:
        reason = "deadline"
    row = {"identity": identity, "scenario": scenario, "strategy": strategy, "size_bytes": size,
           "wire_bytes": wire, "confirmed_bytes": confirmed, "elapsed_ms": round(elapsed, 2), "elapsed_ms_exact": elapsed,
           "deadline_ms": round(DEADLINE * pace * 1000), "attempts": attempts, "disconnects": failures,
           "expected_sha256": expected, "sha256": acknowledged_digest, "verified": verified,
           "success": success, "reason": reason}
    update("finish", **row)
    return row


def plan(smoke=False):
    if smoke:
        scenarios = list(SCENARIOS)
    else:
        scenarios = ["interrupted"] * 80 + ["stable"] * 40 + ["latency"] * 20 + ["small"] * 20
        random.Random(52611).shuffle(scenarios)
    prefix = "after-disconnect-smoke" if smoke else "after-disconnect-v1"
    return [(f"{prefix}-{i:03d}", case) for i, case in enumerate(scenarios)]


def summarize(rows):
    def group(sample):
        verified = [r["elapsed_ms"] for r in sample if r["success"]]
        return {"n": len(sample), "successes": len(verified),
                "success_rate": len(verified) / len(sample) if sample else None,
                "median_elapsed_success_only_ms": statistics.median(verified) if verified else None,
                "payload_bytes_sent": sum(r["wire_bytes"] for r in sample)}
    return {case: {arm: group([r for r in rows if (case == "overall" or r["scenario"] == case)
                                          and r["strategy"] == arm]) for arm in ("whole", "resume")}
            for case in ("overall", *SCENARIOS)}


def run(args):
    cases = plan(args.smoke)
    args.out.mkdir(exist_ok=True, parents=True)
    # Exclusive reservation protects against accidental replay into an existing output.
    with (args.out / "enrollment.jsonl").open("x", encoding="utf8") as journal:
        official = args.mode == "flagsmith"
        if official:
            from flagsmith_experiment import ExperimentClient
            client = ExperimentClient()
        client_lock = threading.Lock()
        stop = threading.Event()

        def record(event, **fields):
            journal.write(json.dumps({"event": event, **fields}) + "\n")
            journal.flush()

        def work(item):
            i, (identity, scenario) = item
            if stop.is_set():
                return []
            try:
                if official:
                    with client_lock:
                        if stop.is_set():
                            return []
                        record("assigning", identity=identity, scenario=scenario)
                        arm = client.assign(identity)
                        if arm not in ("whole", "resume"):
                            raise ValueError("unexpected Flagsmith strategy")
                        record("assigned", identity=identity, scenario=scenario, strategy=arm)
                    arms = [arm]
                else:
                    arms = ["whole", "resume"] if i % 2 == 0 else ["resume", "whole"]
                results = []
                for arm in arms:
                    row = transmit(server, identity, scenario, arm)
                    with client_lock:
                        record("observed", **row)
                        if official and row["success"]:
                            client.convert(identity)
                            record("converted", identity=identity)
                    results.append(row)
                return results
            except Exception:
                stop.set()
                raise

        rows = []
        audit_lock = threading.Lock()
        with (args.out / "server-receipts.jsonl").open("x", encoding="utf8") as receipts:
            def audit(entry):
                with audit_lock:
                    receipts.write(json.dumps(entry) + "\n")
            with receiver(audit) as server, ThreadPoolExecutor(max_workers=args.workers) as executor:
                for batch in executor.map(work, enumerate(cases)):
                    rows.extend(batch)
    with (args.out / "sessions.csv").open("x", encoding="utf8", newline="") as dest:
        writer = csv.DictWriter(dest, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"mode": args.mode, "smoke": args.smoke, "workers": args.workers, "groups": summarize(rows)}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8")
    print(json.dumps(summary["groups"]["overall"], indent=2))


class Gallery(BaseHTTPRequestHandler):
    def do_GET(self):
        target = urlsplit(self.path).path
        if target == "/":
            target = "/index.html"
        if target.startswith("/web/"):
            target = target[4:]
        base = ROOT / "web"
        file = (base / target.lstrip("/")).resolve()
        evidence = {
            "/data/platform.json": "evidence/platform.json",
            "/data/groups.json": "results/official/summary.json",
            "/data/sessions.csv": "results/official/sessions.csv",
            "/data/release.json": "evidence/release.json",
            "/data/flagsmith-dashboard.png": "evidence/flagsmith-dashboard.png",
            "/data/reconciliation.json": "evidence/reconciliation.json",
            "/data/sensitivity.csv": "evidence/sensitivity.csv",
            "/data/live-release-check.json": "evidence/live-release-check.json",
        }
        if target in evidence:
            base = ROOT
            file = ROOT / evidence[target]
        if not file.is_relative_to(base) or not file.is_file():
            return self.send_error(404)
        mime = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
                ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png",
                ".csv": "text/csv; charset=utf-8", ".woff2": "font/woff2"}.get(file.suffix.lower(), "application/octet-stream")
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json_response(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path not in ("/api/demo", "/api/release-check"):
            return self.send_error(404)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 1024:
                raise ValueError
            options = json.loads(self.rfile.read(size))
            scenario = options["scenario"]
            if scenario not in SCENARIOS:
                raise ValueError
            pace = 1 if options.get("pace") == "normal" else 4
        except (KeyError, ValueError, TypeError, UnicodeError):
            return self.json_response(400, {"status": "invalid", "message": "Unknown scenario or invalid request."})
        if not self.server.demo_slots.acquire(blocking=False):
            return self.json_response(429, {"status": "busy", "message": "All upload slots are in use. Try again shortly."})
        try:
            if self.path == "/api/release-check":
                from release_check import ReleaseUnavailable, released_strategy
                try:
                    result = released_strategy()
                except ReleaseUnavailable as error:
                    return self.json_response(503, {"status": "unavailable", "message": str(error)})
                if result["status"] == "executed":
                    result["receipt"] = transmit(self.server.receiver, "release-check-" + scenario, scenario,
                                                 result["strategy"])
                return self.json_response(200, result)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            events = queue.Queue()
            with ThreadPoolExecutor(max_workers=2) as pool:
                tasks = [pool.submit(transmit, self.server.receiver, "demo-" + scenario, scenario, arm,
                                     events.put, pace) for arm in ("whole", "resume")]
                while not all(t.done() for t in tasks) or not events.empty():
                    try:
                        event = events.get(timeout=0.05)
                    except queue.Empty:
                        continue
                    self.wfile.write(json.dumps(event).encode() + b"\n")
                    self.wfile.flush()
                for task in tasks:
                    task.result()
        finally:
            self.server.demo_slots.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serving = sub.add_parser("serve")
    serving.add_argument("--port", type=int, default=8765)
    bench = sub.add_parser("run")
    bench.add_argument("--mode", choices=["local", "flagsmith"], required=True)
    bench.add_argument("--out", type=Path, required=True)
    bench.add_argument("--workers", type=int, choices=range(1, 9), default=4)
    bench.add_argument("--smoke", action="store_true", help="four independent identities; use a separate experiment")
    args = parser.parse_args()
    if args.command == "run":
        run(args)
    else:
        with receiver() as backend, LocalServer(("127.0.0.1", args.port), Gallery) as server:
            server.receiver = backend
            server.demo_slots = threading.BoundedSemaphore(4)
            print(f"http://127.0.0.1:{args.port}", flush=True)
            server.serve_forever()


if __name__ == "__main__":
    main()
