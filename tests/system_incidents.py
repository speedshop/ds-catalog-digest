"""Exercise incident notification and recovery through the command-line boundary."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_GH = '''import json, os, sys
from pathlib import Path
path = Path(os.environ["INCIDENT_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
if args[:2] == ["run", "list"]:
    print(json.dumps([{"databaseId": state["latest"]}]))
elif args[:2] == ["issue", "list"]:
    print(json.dumps(state["issues"]))
elif args[:2] == ["label", "create"]:
    pass
elif args[:2] == ["issue", "create"]:
    state["creates"] += 1
    state["issues"].append({"number": state["creates"], "state": "OPEN"})
elif args[:2] == ["issue", "close"]:
    state["closes"] += 1
    for issue in state["issues"]:
        if str(issue["number"]) == args[2]:
            issue["state"] = "CLOSED"
else:
    raise SystemExit("Unexpected command")
path.write_text(json.dumps(state))
'''

with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    executable = work / "gh"
    executable.write_text(f"#!{sys.executable}\n" + FAKE_GH)
    executable.chmod(0o755)
    state_path = work / "state.json"
    event_path = work / "event.json"
    state_path.write_text(json.dumps({"latest": 1, "issues": [], "creates": 0, "closes": 0}))
    environment = dict(os.environ, PATH=str(work) + os.pathsep + os.environ["PATH"], INCIDENT_STATE=str(state_path), GITHUB_EVENT_PATH=str(event_path), GITHUB_REPOSITORY="example/catalog")

    def notify(run_id, conclusion):
        event_path.write_text(json.dumps({"workflow_run": {"id": run_id, "conclusion": conclusion, "html_url": f"https://example.com/run/{run_id}"}}))
        subprocess.run([sys.executable, str(ROOT / "scripts/sync_incident.py")], env=environment, check=True)
        return json.loads(state_path.read_text())

    assert notify(1, "failure")["creates"] == 1
    assert notify(1, "failure")["creates"] == 1
    assert notify(1, "cancelled")["closes"] == 0
    state = json.loads(state_path.read_text())
    state["latest"] = 2
    state_path.write_text(json.dumps(state))
    assert notify(1, "success")["closes"] == 0
    assert notify(2, "failure")["creates"] == 1
    assert notify(2, "success")["closes"] == 1
    assert notify(2, "success")["closes"] == 1
    assert notify(2, "failure")["creates"] == 2

print("System incidents: one alert per incident, stale-event suppression, recovery passed")
