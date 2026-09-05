import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_catalog import build_catalog


class CatalogTest(unittest.TestCase):
    def row(self):
        return {
            "config": "mini_swe_agent_gpt_5_5_low",
            "model": "gpt-5-5",
            "provider": "openai",
            "harness": "mini-swe-agent",
            "reasoning_effort": "low",
            "pass_at_1": 0.5,
            "mean_duration_seconds": 10.0,
            "mean_cost_usd": 1.25,
            "n_attempted": 4,
            "n_passed": 2,
            "n_tasks_attempted": 1,
            "n_runs": 4,
            "ci_lo": 0.25,
            "ci_hi": 0.75,
        }

    def test_maps_deepswe_metrics_to_contract(self):
        row = self.row()
        leaderboard = {"generated_at": "2026-09-02T15:18:19Z", "n_tasks_in_set": 1, "rows": [row]}
        manifest = {
            "release": "v1.1",
            "datasetUrl": "https://example.com/data",
            "leaderboardUrl": "https://example.com/leaderboard",
            "trialsUrl": "https://example.com/trials",
            "leaderboardSha256": "a" * 64,
            "trialsSha256": "b" * 64,
            "methodologyUrl": "https://example.com/method",
            "license": "CC-BY-4.0",
            "attribution": "DeepSWE leaderboard data by Datacurve, licensed under CC BY 4.0",
        }
        pi_catalog = {"routes": []}
        catalog, _, _, _ = build_catalog(leaderboard, manifest, pi_catalog, {}, "2026-09-03T00:00:00Z")
        variant = catalog["variants"][0]
        self.assertEqual({"smart": 0.5, "fast": 10.0, "cheap": 1.25}, variant["metrics"])
        self.assertEqual(
            {
                "smart": {"kind": "source", "benchmarkVersion": "v1.1"},
                "fast": {"kind": "source", "benchmarkVersion": "v1.1"},
                "cheap": {"kind": "source", "benchmarkVersion": "v1.1"},
            },
            variant["metricOrigins"],
        )
        self.assertEqual("deepswe:config:mini_swe_agent_gpt_5_5_low", variant["id"])
        self.assertEqual("openai", variant["provenance"]["sourceProvider"])
        self.assertEqual("https://example.com/trials", catalog["catalog"]["provenance"]["trialsUrl"])

    def test_published_catalog_validates(self):
        schema = json.loads((ROOT / "schema/model-selection-catalog.schema.json").read_text())
        catalog = json.loads((ROOT / "catalog/model-selection-catalog.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(catalog)
        self.assertEqual(65, len(catalog["variants"]))


if __name__ == "__main__":
    unittest.main()
