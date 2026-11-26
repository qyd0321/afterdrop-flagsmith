import hashlib
import http.client
import json
import socket
import unittest
from collections import Counter

from upload_lab import Upload, plan, receiver, transmit


class UploadTests(unittest.TestCase):
    def test_frozen_cohorts(self):
        cases = plan()
        self.assertEqual(len(set(identity for identity, _ in cases)), 160)
        self.assertEqual(Counter(case for _, case in cases),
                         {"interrupted": 80, "stable": 40, "latency": 20, "small": 20})
        self.assertFalse({identity for identity, _ in cases} & {identity for identity, _ in plan(True)})

    def test_short_read_retry_offsets_and_digest(self):
        audit = []
        with receiver(audit.append) as server:
            expected = hashlib.sha256(b"abcdefgh").hexdigest()
            server.uploads["test"] = Upload(8, expected)

            def put(offset, length, data):
                conn = http.client.HTTPConnection(*server.server_address, timeout=2)
                conn.request("PUT", "/test", data, {"X-Offset": str(offset), "Content-Length": str(length)})
                if len(data) != length:
                    conn.sock.shutdown(socket.SHUT_WR)
                response = conn.getresponse()
                ack = json.loads(response.read())
                conn.close()
                return response.status, ack

            self.assertEqual(put(0, 4, b"ab")[0], 409)
            self.assertEqual(put(4, 4, b"efgh")[0], 409)
            self.assertEqual(put(0, 4, b"abcd")[1]["confirmed"], 4)
            self.assertEqual(put(0, 4, b"abcd")[1]["confirmed"], 4)
            self.assertEqual(put(0, 4, b"wrong"[:4])[0], 409)
            final = put(4, 4, b"efgh")[1]
            self.assertEqual(final["sha256"], expected)
            self.assertTrue(final["verified"])
        self.assertEqual(audit[0]["received_bytes"], 2)
        self.assertEqual(audit[-1]["confirmed"], 8)

    def test_server_recomputes_digest_for_identical_payload(self):
        with receiver() as server:
            rows = [transmit(server, "probe", "small", arm) for arm in ("whole", "resume")]
        self.assertTrue(all(row["success"] for row in rows))
        self.assertEqual(rows[0]["sha256"], rows[1]["sha256"])
        self.assertEqual(rows[0]["size_bytes"], rows[1]["wire_bytes"])


if __name__ == "__main__":
    unittest.main()
