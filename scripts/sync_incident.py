import base64
import json
import os
import subprocess
import time
from pathlib import Path

LABEL = "catalog-maintenance"
STATE_BRANCH = "catalog-maintenance-state"
STATE_PATH = ".catalog-maintenance.json"
REPAIR_WORKFLOW = "catalog-repair.lock.yml"
MAX_ATTEMPTS = 2
REPAIR_DEADLINE_SECONDS = 7200
PUBLICATION_DEADLINE_SECONDS = 3600


def gh(*arguments, document=None, missing=False):
    result = subprocess.run(["gh", *arguments], input=json.dumps(document) if document is not None else None, capture_output=True, text=True)
    if result.returncode:
        if missing and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError(f"GitHub operation failed: {' '.join(arguments[:2])}")
    return result.stdout


def api(path, document=None, missing=False):
    arguments = ["api", path]
    if document is not None:
        arguments += ["--method", "POST", "--input", "-"]
    value = gh(*arguments, document=document, missing=missing)
    return json.loads(value) if value else None


def load_state(repository):
    file = api(f"repos/{repository}/contents/{STATE_PATH}?ref={STATE_BRANCH}", missing=True)
    return (json.loads(base64.b64decode(file["content"])), file["sha"]) if file else ({}, None)


def save_state(repository, state, sha):
    if not sha and not api(f"repos/{repository}/git/ref/heads/{STATE_BRANCH}", missing=True):
        main = api(f"repos/{repository}/git/ref/heads/main")
        api(f"repos/{repository}/git/refs", {"ref": f"refs/heads/{STATE_BRANCH}", "sha": main["object"]["sha"]})
    document = {"branch": STATE_BRANCH, "message": "Record bounded catalog repair state", "content": base64.b64encode((json.dumps(state, sort_keys=True) + "\n").encode()).decode()}
    if sha:
        document["sha"] = sha
    result = subprocess.run(["gh", "api", f"repos/{repository}/contents/{STATE_PATH}", "--method", "PUT", "--input", "-"], input=json.dumps(document), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Could not persist bounded repair state")
    return json.loads(result.stdout)["content"]["sha"]


def incidents(repository):
    return json.loads(gh("issue", "list", "--repo", repository, "--label", LABEL, "--state", "open", "--limit", "100", "--json", "number"))


def escalate(repository, state, reason, url):
    if incidents(repository):
        return
    gh("label", "create", LABEL, "--repo", repository, "--color", "B60205", "--description", "Automatic catalog repair needs human help", "--force")
    body = f"@nateberkopec automatic catalog repair could not restore green.\n\n{reason}\n\nWorkflow: {url}\n\nIncident: {state.get('incident', 'orchestration failure')}; attempts reserved: {state.get('attempts', 0)}/{MAX_ATTEMPTS}. The last-known-good catalog remains available. Inspect the workflow logs and acquisition report. Another daily failure does not reset the repair budget. This issue closes after successful production publication."
    gh("issue", "create", "--repo", repository, "--title", "Catalog automatic repair needs human help", "--body", body, "--label", LABEL)


def dispatch(repository, state, sha):
    state["attempts"] += 1
    state["phase"] = "repair"
    state["deadline"] = int(time.time()) + REPAIR_DEADLINE_SECONDS
    state.pop("repair_run", None)
    state["base_sha"] = api(f"repos/{repository}/git/ref/heads/main")["object"]["sha"]
    sha = save_state(repository, state, sha)
    try:
        gh("label", "create", "catalog-repair", "--repo", repository, "--color", "0E8A16", "--description", "Bounded Luna catalog repair", "--force")
        gh("workflow", "run", REPAIR_WORKFLOW, "--repo", repository, "--ref", "main", "-f", f"incident={state['incident']}", "-f", f"attempt={state['attempts']}", "-f", f"failed_run={state['failed_run']}")
        title = f"Catalog repair {state['incident']} attempt {state['attempts']}"
        for _ in range(12):
            runs = json.loads(gh("run", "list", "--repo", repository, "--workflow", REPAIR_WORKFLOW, "--branch", "main", "--event", "workflow_dispatch", "--limit", "100", "--json", "databaseId,displayTitle,headSha"))
            matching = [run for run in runs if run["displayTitle"] == title and run["headSha"] == state["base_sha"]]
            if matching:
                state["repair_run"] = min(run["databaseId"] for run in matching)
                save_state(repository, state, sha)
                break
            time.sleep(2)
        else:
            raise RuntimeError("Could not bind the reserved repair workflow run")
    except RuntimeError:
        state["phase"] = "escalated"
        save_state(repository, state, sha)
        escalate(repository, state, "The bounded repair attempt could not be launched.", state["failed_url"])
        raise


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    repository = os.environ["GITHUB_REPOSITORY"]
    if "workflow_run" not in event:
        state, sha = load_state(repository)
        if state.get("phase") in {"repair", "publication"} and state.get("deadline", 0) <= time.time():
            state["phase"] = "escalated"
            save_state(repository, state, sha)
            escalate(repository, state, "Automatic repair or its production refresh exceeded the bounded deadline.", state["failed_url"])
        return
    run = event["workflow_run"]
    if run.get("head_branch") != "main" or run.get("head_repository", {}).get("full_name") != repository:
        return
    state, sha = load_state(repository)
    if run["name"] == "Publish catalog digest":
        latest = json.loads(gh("run", "list", "--repo", repository, "--workflow", "publish.yml", "--branch", "main", "--status", "completed", "--limit", "1", "--json", "databaseId"))
        if not latest or latest[0]["databaseId"] != run["id"]:
            return
        if run["conclusion"] == "success":
            if state:
                save_state(repository, {}, sha)
            for issue in incidents(repository):
                gh("issue", "close", str(issue["number"]), "--repo", repository, "--comment", f"Production publication recovered: {run['html_url']}")
            return
        if run["conclusion"] not in {"failure", "timed_out", "action_required"}:
            return
        if state.get("phase") in {"repair", "escalated"} or run["id"] <= int(state.get("failed_run", 0)):
            return
        if not state:
            state = {"incident": str(run["id"]), "attempts": 0}
        state.update(failed_run=str(run["id"]), failed_url=run["html_url"])
    elif run["name"] == "Verify catalog repair":
        if run.get("run_attempt", 1) != 1 or state.get("phase") != "repair" or run.get("display_title") != f"Verify Catalog repair {state['incident']} attempt {state['attempts']}":
            return
        if state.get("deadline", 0) <= time.time():
            state["phase"] = "escalated"
            save_state(repository, state, sha)
            escalate(repository, state, "The bounded repair result arrived after its deadline.", run["html_url"])
            return
        if run["conclusion"] == "success":
            state["phase"] = "publication"
            state["deadline"] = int(time.time()) + PUBLICATION_DEADLINE_SECONDS
            sha = save_state(repository, state, sha)
            gh("workflow", "run", "publish.yml", "--repo", repository, "--ref", "main")
            return
    else:
        return
    if state["attempts"] >= MAX_ATTEMPTS:
        state["phase"] = "escalated"
        save_state(repository, state, sha)
        escalate(repository, state, "Both bounded attempts failed to restore verified production publication.", run["html_url"])
    else:
        dispatch(repository, state, sha)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        repository = os.environ["GITHUB_REPOSITORY"]
        url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
        escalate(repository, {}, "The automatic repair controller failed; a repair could not be completed safely.", url)
        raise
