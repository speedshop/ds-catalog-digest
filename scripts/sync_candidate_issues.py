#!/usr/bin/env python3
"""Synchronize unresolved Provider Route candidates with GitHub issues."""

import argparse
import json
import subprocess
from pathlib import Path

LABEL = "route-candidate"
MARKER_PREFIX = "<!-- pi-route-candidate:"


class GhRunner:
    def run(self, arguments, input_text=None):
        result = subprocess.run(["gh", *arguments], check=True, capture_output=True, input=input_text, text=True)
        return result.stdout


def marker(variant_id):
    return f"{MARKER_PREFIX}{variant_id} -->"


def managed_variant_id(body):
    start = body.find(MARKER_PREFIX)
    if start < 0:
        return None
    end = body.find(" -->", start)
    return body[start + len(MARKER_PREFIX) : end] if end >= 0 else None


def issue_body(candidate):
    route_lines = ["No matching route currently exists in the pinned Pi catalog."]
    if candidate["routes"]:
        route_lines = [
            "| Provider | Model ID | Pi thinking level | Fingerprint |",
            "|---|---|---|---|",
            *[
                f"| {route['provider']} | `{route['modelId']}` | `{route['piThinkingLevel']}` | `{route['routeFingerprint']}` |"
                for route in candidate["routes"]
            ],
        ]
    return "\n".join([
        marker(candidate["variantId"]),
        "",
        "This issue is managed from the Provider Route candidate queue.",
        "",
        "## DeepSWE configuration",
        "",
        f"- Variant: `{candidate['variantId']}`",
        f"- Configuration: `{candidate['sourceConfig']}`",
        f"- Model: `{candidate['displayName']}`",
        f"- Recorded provider: `{candidate['sourceProvider']}`",
        f"- Reasoning effort: `{candidate['reasoningEffort']}`",
        "",
        "## Candidate route",
        "",
        *route_lines,
        "",
        f"Reason: `{candidate['reason']}`",
        f"Stale routes: `{len(candidate['staleRoutes'])}`",
        "",
        "## Review",
        "",
        "- [ ] Verify exact model and reasoning-effort identity.",
        "- [ ] Record an accepted or rejected decision in `mappings/route-decisions.json`.",
        "",
    ])


def load_queue(path):
    queue = json.loads(Path(path).read_text())
    if queue.get("schemaVersion") != 1 or not isinstance(queue.get("candidates"), list):
        raise ValueError("Candidate queue must use schemaVersion 1")
    ids = [candidate.get("variantId") for candidate in queue["candidates"]]
    if any(not value or not value.startswith("deepswe:config:") for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("Candidate queue contains invalid or duplicate variant IDs")
    return queue


def synchronize(queue, runner, dry_run=False):
    repository = json.loads(runner.run(["repo", "view", "--json", "isPrivate"]))
    if repository.get("isPrivate") is not False:
        raise ValueError("Candidate issues must be synchronized to a public repository")
    issues = json.loads(runner.run(["issue", "list", "--state", "all", "--limit", "1000", "--json", "number,title,state,body"]))
    managed = {managed_variant_id(issue.get("body", "")): issue for issue in issues if managed_variant_id(issue.get("body", ""))}
    desired = {candidate["variantId"]: candidate for candidate in queue["candidates"]}
    actions = []
    if desired and not dry_run:
        runner.run(["label", "create", LABEL, "--color", "BFDADC", "--description", "Managed Pi Provider Route review", "--force"])
    for variant_id, candidate in desired.items():
        title = f"Verify Pi Provider Route for {candidate['displayName']}"
        body = issue_body(candidate)
        issue = managed.get(variant_id)
        if issue is None:
            actions.append({"action": "create", "variantId": variant_id})
            if not dry_run:
                runner.run(["issue", "create", "--title", title, "--body-file", "-", "--label", LABEL], body)
        else:
            if issue["title"] != title or issue["body"] != body:
                actions.append({"action": "update", "variantId": variant_id, "number": issue["number"]})
                if not dry_run:
                    runner.run(["issue", "edit", str(issue["number"]), "--title", title, "--body-file", "-"], body)
            if issue["state"] != "OPEN":
                actions.append({"action": "reopen", "variantId": variant_id, "number": issue["number"]})
                if not dry_run:
                    runner.run(["issue", "reopen", str(issue["number"])])
    for variant_id, issue in managed.items():
        if variant_id not in desired and issue["state"] == "OPEN":
            actions.append({"action": "close", "variantId": variant_id, "number": issue["number"]})
            if not dry_run:
                runner.run(["issue", "close", str(issue["number"]), "--comment", "The current catalog no longer requires this review."])
    return actions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_queue", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(json.dumps(synchronize(load_queue(args.candidate_queue), GhRunner(), args.dry_run), indent=2))


if __name__ == "__main__":
    main()
