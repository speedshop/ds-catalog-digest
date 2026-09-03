import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sync_candidate_issues


class Runner:
    def __init__(self, issues=None):
        self.issues = issues or []
        self.calls = []

    def run(self, arguments, input_text=None):
        self.calls.append((arguments, input_text))
        if arguments[:2] == ["repo", "view"]:
            return json.dumps({"isPrivate": False})
        if arguments[:2] == ["issue", "list"]:
            return json.dumps(self.issues)
        return ""


class CandidateIssuesTest(unittest.TestCase):
    def candidate(self):
        return {
            "variantId": "deepswe:config:test",
            "displayName": "test-model",
            "sourceConfig": "test",
            "sourceProvider": "provider",
            "reasoningEffort": "high",
            "reason": "missing_route",
            "routes": [],
            "staleRoutes": [],
        }

    def test_creates_issue_for_candidate(self):
        runner = Runner()
        actions = sync_candidate_issues.synchronize({"schemaVersion": 1, "candidates": [self.candidate()]}, runner)
        self.assertEqual("create", actions[0]["action"])
        self.assertTrue(any(call[0][:2] == ["issue", "create"] for call in runner.calls))

    def test_refuses_private_repository(self):
        runner = Runner()
        runner.run = lambda arguments, input_text=None: json.dumps({"isPrivate": True})
        with self.assertRaisesRegex(ValueError, "public"):
            sync_candidate_issues.synchronize({"schemaVersion": 1, "candidates": []}, runner)


if __name__ == "__main__":
    unittest.main()
