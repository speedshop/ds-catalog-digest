import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_catalog import build_catalog
from route_mappings import load_decisions


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

    def test_published_catalog_matches_deterministic_rebuild(self):
        catalog_path = ROOT / "catalog/model-selection-catalog.json"
        published = json.loads(catalog_path.read_text())
        leaderboard = {
            "generated_at": published["catalog"]["sourceUpdatedAt"],
            "n_tasks_in_set": published["catalog"]["provenance"]["taskCount"],
            "rows": [],
        }
        for variant in published["variants"]:
            provenance = variant["provenance"]
            leaderboard["rows"].append({
                "config": provenance["sourceConfig"],
                "model": provenance["sourceModel"],
                "provider": provenance["sourceProvider"],
                "harness": provenance["harness"],
                "reasoning_effort": (variant.get("reasoning") or {}).get("label"),
                "pass_at_1": variant["metrics"]["smart"],
                "mean_duration_seconds": variant["metrics"]["fast"],
                "mean_cost_usd": variant["metrics"]["cheap"],
                "n_attempted": provenance["attempted"],
                "n_passed": provenance["passed"],
                "n_tasks_attempted": provenance["tasksAttempted"],
                "n_runs": provenance["runs"],
                "ci_lo": provenance["smartConfidenceInterval95"][0],
                "ci_hi": provenance["smartConfidenceInterval95"][1],
            })

        manifest = json.loads((ROOT / "sources/deepswe-v1.1.json").read_text())
        pi_catalog = json.loads((ROOT / "mappings/pi-model-catalog.json").read_text())
        decisions = load_decisions(ROOT / "mappings/route-decisions.json")
        rebuilt, _, _, _ = build_catalog(
            leaderboard,
            manifest,
            pi_catalog,
            decisions,
            published["catalog"]["generatedAt"],
        )
        rebuilt_bytes = json.dumps(rebuilt, indent=2, sort_keys=False) + "\n"
        self.assertEqual(catalog_path.read_text(), rebuilt_bytes)


if __name__ == "__main__":
    unittest.main()
