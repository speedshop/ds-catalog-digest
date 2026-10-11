"""Notify once per publication incident and once when publication recovers."""

import json
import os
import subprocess
from pathlib import Path

LABEL = "catalog-maintenance"


def gh(*arguments):
    return subprocess.run(["gh", *arguments], check=True, capture_output=True, text=True).stdout


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    run = event["workflow_run"]
    conclusion = run["conclusion"]
    if conclusion not in {"success", "failure", "timed_out", "action_required"}:
        return
    completed = json.loads(gh("run", "list", "--repo", os.environ["GITHUB_REPOSITORY"], "--workflow", "publish.yml", "--branch", "main", "--status", "completed", "--limit", "1", "--json", "databaseId"))
    if not completed or completed[0]["databaseId"] != run["id"]:
        return
    issues = json.loads(gh("issue", "list", "--repo", os.environ["GITHUB_REPOSITORY"], "--label", LABEL, "--state", "all", "--limit", "100", "--json", "number,state"))
    opened = [issue for issue in issues if issue["state"] == "OPEN"]
    repository = os.environ["GITHUB_REPOSITORY"]
    if conclusion == "success":
        for issue in opened:
            gh("issue", "close", str(issue["number"]), "--repo", repository, "--comment", f"Publication recovered: {run['html_url']}")
        return
    if opened:
        return
    gh("label", "create", LABEL, "--repo", repository, "--color", "B60205", "--description", "Catalog acquisition or publication incident", "--force")
    body = f"Automatic catalog maintenance failed: {run['html_url']}\n\nThe last-known-good catalog remains available. Inspect the failed job and acquisition report. Ordinary data updates need no review; source interface, methodology, licensing, or suspicious coverage changes require investigation. This issue closes automatically after a successful publication workflow."
    gh("issue", "create", "--repo", repository, "--title", "Catalog maintenance requires investigation", "--body", body, "--label", LABEL)


if __name__ == "__main__":
    main()
