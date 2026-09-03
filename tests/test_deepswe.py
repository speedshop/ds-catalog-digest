import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from deepswe import attach_providers, load_artifact, validate_leaderboard


class DeepSweTest(unittest.TestCase):
    def row(self):
        return {
            "config": "mini_swe_agent_gpt_5_5_low",
            "model": "gpt-5-5",
            "harness": "mini-swe-agent",
            "pass_at_1": 0.5,
            "mean_duration_seconds": 10.0,
            "mean_cost_usd": 1.0,
        }

    def test_attaches_the_single_recorded_provider(self):
        rows = [self.row()]
        attach_providers(rows, {"rows": [{"config": rows[0]["config"], "provider": "openai"}]})
        self.assertEqual("openai", rows[0]["provider"])

    def test_rejects_multiple_providers_for_one_configuration(self):
        rows = [self.row()]
        trials = {"rows": [
            {"config": rows[0]["config"], "provider": "openai"},
            {"config": rows[0]["config"], "provider": "other"},
        ]}
        with self.assertRaisesRegex(ValueError, "exactly one"):
            attach_providers(rows, trials)

    def test_requires_complete_metrics(self):
        row = self.row()
        row["mean_cost_usd"] = None
        with self.assertRaisesRegex(ValueError, "mean_cost_usd"):
            validate_leaderboard({"rows": [row]})

    def test_checks_artifact_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            payload = json.dumps({"rows": []}).encode()
            path.write_bytes(payload)
            document = load_artifact("unused", hashlib.sha256(payload).hexdigest(), path)
            self.assertEqual({"rows": []}, document)
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                load_artifact("unused", "0" * 64, path)


if __name__ == "__main__":
    unittest.main()
