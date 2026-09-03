import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from route_mappings import canonical_model_id, compile_aliases, route_fingerprint, variant_id


class RouteMappingsTest(unittest.TestCase):
    def route(self):
        return {
            "provider": "openai",
            "modelId": "gpt-5.5",
            "name": "GPT-5.5",
            "api": "openai-responses",
            "reasoning": True,
            "supportedThinkingLevels": ["low", "high"],
            "thinkingLevelMap": {},
            "contextWindow": 100,
            "maxTokens": 20,
            "fingerprint": "ignored",
        }

    def row(self):
        return {
            "config": "mini_swe_agent_gpt_5_5_low",
            "provider": "openai",
            "model": "gpt-5-5",
            "reasoning_effort": "low",
        }

    def test_limits_do_not_change_route_fingerprint(self):
        route = self.route()
        changed = copy.deepcopy(route)
        changed["contextWindow"] = 200
        changed["maxTokens"] = 40
        self.assertEqual(route_fingerprint(route), route_fingerprint(changed))

    def test_behavioral_fields_change_route_fingerprint(self):
        route = self.route()
        changed = copy.deepcopy(route)
        changed["name"] = "Renamed"
        self.assertNotEqual(route_fingerprint(route), route_fingerprint(changed))

    def test_canonical_model_ids_preserve_checkpoint_identity(self):
        self.assertEqual("gpt-5-6-sol", canonical_model_id("openai/gpt-5.6-sol:batch"))
        self.assertEqual("claude-opus-5", canonical_model_id("global.anthropic.claude-opus-5"))
        self.assertNotEqual(canonical_model_id("gpt-5.6-sol"), canonical_model_id("gpt-5.6-sol-pro"))

    def test_only_current_accepted_decisions_publish(self):
        row = self.row()
        route = self.route()
        decision = {
            "outcome": "accepted",
            "route": {"provider": "openai", "modelId": "gpt-5.5", "piThinkingLevel": "low"},
            "routeFingerprint": route_fingerprint(route),
        }
        aliases, stale = compile_aliases([row], {"routes": [route]}, {variant_id(row): [decision]})
        self.assertEqual("verified", aliases[variant_id(row)][0]["equivalence"])
        self.assertEqual([], stale)


if __name__ == "__main__":
    unittest.main()
