import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_GH = '''import base64, json, os, sys
from pathlib import Path
path = Path(os.environ["INCIDENT_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
def value(flag):
    return args[args.index(flag) + 1]
if args[0] == "api":
    endpoint = args[1]
    method = value("--method") if "--method" in args else "GET"
    if method == "PUT":
        document = json.load(sys.stdin)
        if state["ledger"] is not None and document.get("sha") != str(state["writes"]):
            raise SystemExit("stale state lease")
        state["ledger"] = json.loads(base64.b64decode(document["content"]))
        state["writes"] += 1
        print(json.dumps({"content": {"sha": str(state["writes"])}}))
    elif endpoint.endswith("git/refs"):
        state["branch"] = True
        print("{}")
    elif "contents/" in endpoint:
        if state["ledger"] is None:
            print("HTTP 404", file=sys.stderr)
            raise SystemExit(1)
        print(json.dumps({"content": base64.b64encode(json.dumps(state["ledger"]).encode()).decode(), "sha": str(state["writes"])}))
    elif endpoint.endswith("git/ref/heads/main"):
        print(json.dumps({"object": {"sha": "0" * 40}}))
    elif "git/ref/" in endpoint:
        if not state["branch"]:
            print("HTTP 404", file=sys.stderr)
            raise SystemExit(1)
        print(json.dumps({"object": {"sha": "0" * 40}}))
    else:
        print(json.dumps({"private": True}))
elif args[:2] == ["run", "list"]:
    if value("--workflow") == "publish.yml":
        print(json.dumps([{"databaseId": state["latest"]}]))
    else:
        print(json.dumps(state["runs"]))
elif args[:2] == ["workflow", "run"]:
    workflow = args[2]
    if workflow == "publish.yml":
        state["publicationRetries"] += 1
    else:
        if state.get("dispatchFails"):
            raise SystemExit(1)
        fields = dict(item.split("=", 1) for index, item in enumerate(args) if index and args[index - 1] == "-f")
        state["dispatches"] += 1
        state["runs"].append({"databaseId": 100 + state["dispatches"], "displayTitle": "Catalog repair " + fields["incident"] + " attempt " + fields["attempt"], "headSha": "0" * 40})
elif args[:2] == ["issue", "list"]:
    print(json.dumps([issue for issue in state["issues"] if issue["state"] == "OPEN"]))
elif args[:2] == ["label", "create"]:
    pass
elif args[:2] == ["issue", "create"]:
    state["creates"] += 1
    state["issues"].append({"number": state["creates"], "state": "OPEN", "body": value("--body")})
elif args[:2] == ["issue", "close"]:
    state["closes"] += 1
    for issue in state["issues"]:
        if str(issue["number"]) == args[2]:
            issue["state"] = "CLOSED"
else:
    raise SystemExit("Unexpected command: " + str(args))
path.write_text(json.dumps(state))
'''

with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    executable = work / "gh"
    executable.write_text(f"#!{sys.executable}\n" + FAKE_GH)
    executable.chmod(0o755)
    state_path = work / "state.json"
    event_path = work / "event.json"
    initial = {"latest": 1, "issues": [], "creates": 0, "closes": 0, "ledger": None, "writes": 0, "branch": False, "dispatches": 0, "publicationRetries": 0, "runs": []}
    state_path.write_text(json.dumps(initial))
    environment = dict(os.environ, PATH=str(work) + os.pathsep + os.environ["PATH"], INCIDENT_STATE=str(state_path), GITHUB_EVENT_PATH=str(event_path), GITHUB_REPOSITORY="example/catalog", GITHUB_RUN_ID="9000")

    def notify(run_id, conclusion, name="Publish catalog digest", title=None, succeeds=True):
        event_path.write_text(json.dumps({"workflow_run": {"id": run_id, "conclusion": conclusion, "name": name, "display_title": title, "head_branch": "main", "head_repository": {"full_name": "example/catalog"}, "html_url": f"https://example.com/run/{run_id}"}}))
        result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_incident.py")], env=environment, capture_output=True, text=True)
        assert (result.returncode == 0) == succeeds, result.stderr
        return json.loads(state_path.read_text())

    first = notify(1, "failure")
    assert first["dispatches"] == 1 and first["creates"] == 0
    assert first["ledger"]["attempts"] == 1 and first["ledger"]["repair_run"] == 101
    assert notify(1, "failure")["dispatches"] == 1
    assert notify(1, "cancelled")["dispatches"] == 1
    state = notify(201, "failure", "Verify catalog repair", "Verify Catalog repair 1 attempt 1")
    assert state["dispatches"] == 2 and state["creates"] == 0
    assert state["ledger"]["repair_run"] == 102
    assert notify(201, "success", "Verify catalog repair", "Verify Catalog repair 1 attempt 1")["publicationRetries"] == 0
    state = notify(202, "success", "Verify catalog repair", "Verify Catalog repair 1 attempt 2")
    assert state["publicationRetries"] == 1 and state["closes"] == 0
    assert notify(202, "success", "Verify catalog repair", "Verify Catalog repair 1 attempt 2")["publicationRetries"] == 1
    state = notify(1, "failure")
    assert state["dispatches"] == 2 and state["creates"] == 0
    state["latest"] = 2
    state_path.write_text(json.dumps(state))
    state = notify(2, "failure")
    assert state["dispatches"] == 2 and state["creates"] == 1
    assert "@nateberkopec" in state["issues"][0]["body"]
    assert notify(1, "failure")["creates"] == 1
    state["latest"] = 3
    state_path.write_text(json.dumps(state))
    assert notify(1, "success")["closes"] == 0
    recovered = notify(3, "success")
    assert recovered["closes"] == 1 and recovered["ledger"] == {}
    assert notify(3, "success")["closes"] == 1
    renewed = notify(3, "failure")
    assert renewed["dispatches"] == 3 and renewed["ledger"]["attempts"] == 1
    assert renewed["creates"] == 1
    failed = dict(initial, dispatchFails=True)
    state_path.write_text(json.dumps(failed))
    failed = notify(1, "failure", succeeds=False)
    assert failed["creates"] == 1 and failed["ledger"]["phase"] == "escalated"
    state_path.write_text(json.dumps(initial))
    reserved = notify(1, "failure")
    event_path.write_text("{}")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_incident.py")], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(state_path.read_text())["creates"] == 0
    reserved["ledger"]["deadline"] = 0
    state_path.write_text(json.dumps(reserved))
    result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_incident.py")], env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    expired = json.loads(state_path.read_text())
    assert expired["creates"] == 1 and expired["ledger"]["phase"] == "escalated"
    assert expired["dispatches"] == 1

print("System incidents: durable two-attempt budget, silent automatic repair, exact run reservation, stale-event suppression, escalation, production recovery passed")
