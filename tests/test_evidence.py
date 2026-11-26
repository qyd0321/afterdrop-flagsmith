import json
import shutil
import tempfile
import unittest
from pathlib import Path

from audit_run import validate
from reconcile import reconcile


ROOT = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.run_dir = Path(directory.name) / "run"
        self.snapshot = Path(directory.name) / "platform.json"
        self.release = ROOT / "evidence/release.json"
        shutil.copytree(ROOT / "results/official", self.run_dir)
        shutil.copyfile(ROOT / "evidence/platform.json", self.snapshot)

    def test_final_release_reconciles(self):
        result = reconcile(self.run_dir, self.snapshot, self.release)
        self.assertEqual(result["sessions_checked"], 160)
        self.assertEqual(result["server_assembled_files"], 106)

    def test_high_latency_guardrail_from_ledger(self):
        path = self.run_dir / "summary.json"
        data = json.loads(path.read_text())
        data["groups"]["latency"]["resume"].update(successes=9, success_rate=1.0)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "latency/resume"):
            validate(self.run_dir)

    def test_incorrect_receiver_offset(self):
        path = self.run_dir / "server-receipts.jsonl"
        rows = path.read_text().splitlines()
        row = json.loads(rows[0])
        row["confirmed"] -= 1
        rows[0] = json.dumps(row)
        path.write_text("\n".join(rows))
        with self.assertRaisesRegex(ValueError, "acknowledgement"):
            validate(self.run_dir)

    def test_final_release_rejects_foreign_experiment(self):
        data = json.loads(self.snapshot.read_text())
        data["experiment_id"] += 1
        self.snapshot.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "completed release"):
            reconcile(self.run_dir, self.snapshot, self.release)

    def test_open_run_can_be_monitored_but_not_submitted_as_final(self):
        data = json.loads(self.snapshot.read_text())
        data["results"]["is_final"] = False
        self.snapshot.write_text(json.dumps(data))
        self.assertTrue(reconcile(self.run_dir, self.snapshot)["platform_agrees"])
        with self.assertRaisesRegex(ValueError, "completed release"):
            reconcile(self.run_dir, self.snapshot, self.release)

    def test_recorded_control_rollout_has_zero_treatment_weight(self):
        path = self.snapshot.parent / "release.json"
        data = json.loads(self.release.read_text())
        data["flag"]["variants"][0]["weight"] = 50
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "global control"):
            reconcile(self.run_dir, self.snapshot, path)
