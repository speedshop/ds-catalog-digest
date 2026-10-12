import os
import time

from repair_gate import context
from sync_incident import api, gh


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    if not context():
        raise RuntimeError("Repair reservation is no longer current")
    number = int(os.environ["REPAIR_PR"])
    head = os.environ["REPAIR_HEAD"]
    branch = os.environ["REPAIR_BRANCH"]
    pull = api(f"repos/{repository}/pulls/{number}")
    if pull["head"]["sha"] != head or pull["head"]["repo"]["full_name"] != repository or pull["base"]["ref"] != "main" or pull["state"] != "open":
        raise RuntimeError("Verified repair PR changed")
    gh("workflow", "run", "ci.yml", "--repo", repository, "--ref", branch)
    run = ""
    for _ in range(12):
        run = gh("run", "list", "--repo", repository, "--workflow", "ci.yml", "--branch", branch, "--commit", head, "--event", "workflow_dispatch", "--limit", "1", "--json", "databaseId", "--jq", ".[0].databaseId // empty").strip()
        if run:
            break
        time.sleep(5)
    if not run or gh("run", "view", run, "--repo", repository, "--json", "headSha", "--jq", ".headSha").strip() != head:
        raise RuntimeError("No exact-commit repair CI run")
    gh("run", "watch", run, "--repo", repository, "--exit-status")
    if not context() or api(f"repos/{repository}/pulls/{number}")["head"]["sha"] != head:
        raise RuntimeError("Repair changed while CI ran")
    url = f"{os.environ['GITHUB_SERVER_URL']}/{repository}/actions/runs/{run}"
    for status in os.environ["REPAIR_REQUIRED_CONTEXTS"].split():
        api(f"repos/{repository}/statuses/{head}", {"state": "success", "context": status, "description": "Trusted repair gate and exact-commit CI passed", "target_url": url})
    gh("pr", "merge", str(number), "--repo", repository, "--squash", "--delete-branch", "--match-head-commit", head)
    for _ in range(30):
        if gh("pr", "view", str(number), "--repo", repository, "--json", "state", "--jq", ".state").strip() == "MERGED":
            print("Verified Luna repair merged; production refresh must establish recovery")
            return
        if not context():
            gh("pr", "merge", str(number), "--repo", repository, "--disable-auto")
            raise RuntimeError("Repair reservation expired while waiting for merge")
        time.sleep(10)
    gh("pr", "merge", str(number), "--repo", repository, "--disable-auto")
    raise RuntimeError("Verified repair did not merge within five minutes")


if __name__ == "__main__":
    main()
