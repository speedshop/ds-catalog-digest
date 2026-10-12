import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_GH = '''import base64, json, os, sys
from pathlib import Path
path = Path(os.environ["REPAIR_TEST_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
if args[0] == "api":
    if "contents/" in args[1]:
        print(json.dumps({"content": base64.b64encode(json.dumps(state["ledger"]).encode()).decode(), "sha": "lease"}))
    elif "git/ref/" in args[1]:
        print(json.dumps({"object": {"sha": state["main"]}}))
    elif "/pulls/" in args[1]:
        print(json.dumps(state["pull"]))
    elif "/statuses/" in args[1]:
        state["attestations"] += 1
        print("{}")
    else:
        print(json.dumps({"private": state["private"]}))
elif args[:2] == ["pr", "list"]:
    print(json.dumps(state["pulls"]))
elif args[:2] == ["run", "list"]:
    if "--commit" in args:
        print("700")
    else:
        print(json.dumps([{"databaseId": state["latest"]}]))
elif args[:2] == ["workflow", "run"]:
    pass
elif args[:2] == ["run", "view"]:
    print(state["ciHead"])
elif args[:2] == ["run", "watch"]:
    if state.get("ciFails"):
        raise SystemExit(1)
elif args[:2] == ["pr", "merge"]:
    assert "--auto" not in args
    state["merges"] += 1
elif args[:2] == ["pr", "view"]:
    print("MERGED")
else:
    raise SystemExit(str(args))
path.write_text(json.dumps(state))
'''

with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    executable = work / "gh"
    executable.write_text(f"#!{sys.executable}\n" + FAKE_GH)
    executable.chmod(0o755)
    state_path = work / "state.json"
    event_path = work / "event.json"
    output = work / "output"
    safe_output = work / "safe-output"
    base, head = "a" * 40, "b" * 40
    state = {"main": base, "private": True, "latest": 9, "ledger": {"incident": "9", "attempts": 1, "phase": "repair", "base_sha": base, "repair_run": 10, "deadline": int(time.time()) + 7200}, "pulls": [], "pull": {"head": {"sha": head, "repo": {"full_name": "example/catalog"}}, "base": {"ref": "main"}, "state": "open"}, "ciHead": head, "attestations": 0, "merges": 0}
    state_path.write_text(json.dumps(state))
    environment = dict(os.environ, PATH=str(work) + os.pathsep + os.environ["PATH"], REPAIR_TEST_STATE=str(state_path), GITHUB_REPOSITORY="example/catalog", GITHUB_EVENT_PATH=str(event_path), GITHUB_OUTPUT=str(output), GH_AW_SAFE_OUTPUTS=str(safe_output), GITHUB_RUN_ID="10", GITHUB_RUN_ATTEMPT="1", GITHUB_SERVER_URL="https://github.com", REPAIR_INCIDENT="9", REPAIR_ATTEMPT="1", REPAIR_PR="12", REPAIR_HEAD=head, REPAIR_BRANCH="repair", REPAIR_REQUIRED_CONTEXTS="check")
    event = {"workflow_run": {"id": 10, "run_attempt": 1, "display_title": "Catalog repair 9 attempt 1", "head_repository": {"full_name": "example/catalog"}, "head_branch": "main", "head_sha": base, "conclusion": "success"}}
    event_path.write_text(json.dumps(event))

    def run(script, *arguments, succeeds=True, changes=None):
        output.write_text("")
        safe_output.write_text("")
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *arguments], cwd=ROOT, env=environment | (changes or {}), capture_output=True, text=True)
        assert (result.returncode == 0) == succeeds, result.stderr
        return result

    run("repair_gate.py", "prepare")
    assert "active=true" in output.read_text() and not safe_output.read_text()
    run("repair_gate.py", "prepare", succeeds=False, changes={"GITHUB_RUN_ATTEMPT": "2"})
    assert json.loads(safe_output.read_text())["type"] == "noop"
    run("repair_gate.py", "prepare", succeeds=False, changes={"GITHUB_RUN_ID": "11"})
    assert json.loads(safe_output.read_text())["type"] == "noop"
    run("repair_gate.py", "select")
    assert "has_patch=false" in output.read_text()
    pull = {"number": 12, "title": "[catalog-repair] incident 9 attempt 1", "headRefOid": head, "headRefName": "repair", "baseRefName": "main", "author": {"login": "github-actions[bot]"}, "body": "https://github.com/example/catalog/actions/runs/10"}
    state["pulls"] = [pull]
    state_path.write_text(json.dumps(state))
    run("repair_gate.py", "select")
    assert "has_patch=true" in output.read_text() and f"head={head}" in output.read_text()
    pull["author"]["login"] = "untrusted"
    state_path.write_text(json.dumps(state))
    run("repair_gate.py", "select", succeeds=False)
    pull["author"]["login"] = "github-actions[bot]"
    pull["body"] = "https://github.com/example/catalog/actions/runs/11"
    state_path.write_text(json.dumps(state))
    run("repair_gate.py", "select", succeeds=False)
    for wrong_origin in ("https://github.com/example/catalog/actions/runs/100", "https://github.com/other/catalog/actions/runs/10"):
        pull["body"] = wrong_origin
        state_path.write_text(json.dumps(state))
        run("repair_gate.py", "select", succeeds=False)
    pull["body"] = "https://github.com/example/catalog/actions/runs/10"
    state_path.write_text(json.dumps(state))
    event["workflow_run"]["conclusion"] = "failure"
    event_path.write_text(json.dumps(event))
    run("repair_gate.py", "select", succeeds=False)
    event["workflow_run"]["conclusion"] = "success"
    event_path.write_text(json.dumps(event))
    state["main"] = "c" * 40
    state_path.write_text(json.dumps(state))
    run("repair_gate.py", "select")
    assert "active=false" in output.read_text()
    state["main"] = base
    state_path.write_text(json.dumps(state))
    run("merge_repair.py")
    merged = json.loads(state_path.read_text())
    assert merged["merges"] == 1 and merged["attestations"] == 1
    state["ciHead"] = "c" * 40
    state_path.write_text(json.dumps(state))
    run("merge_repair.py", succeeds=False)
    rejected = json.loads(state_path.read_text())
    assert rejected["merges"] == 0 and rejected["attestations"] == 0
    state["ciHead"] = head
    state["ciFails"] = True
    state_path.write_text(json.dumps(state))
    run("merge_repair.py", succeeds=False)
    rejected = json.loads(state_path.read_text())
    assert rejected["merges"] == 0 and rejected["attestations"] == 0
    state.pop("ciFails")
    state["ledger"]["deadline"] = 0
    state_path.write_text(json.dumps(state))
    run("repair_gate.py", "prepare", succeeds=False)
    run("merge_repair.py", succeeds=False)
    rejected = json.loads(state_path.read_text())
    assert rejected["merges"] == 0 and rejected["attestations"] == 0
    state["ledger"]["deadline"] = int(time.time()) + 7200
    state_path.write_text(json.dumps(state))
    artifact = json.loads((ROOT / "catalog/model-selection-catalog.json").read_text())
    artifact_path = work / "model-selection-catalog.json"
    artifact_path.write_text(json.dumps(artifact))
    run("repair_gate.py", "validate-artifact", str(work))
    changed = json.loads(json.dumps(artifact))
    changed["catalog"]["distribution"]["allowRedistribution"] = not changed["catalog"]["distribution"]["allowRedistribution"]
    artifact_path.write_text(json.dumps(changed))
    run("repair_gate.py", "validate-artifact", str(work), succeeds=False)
    changed = json.loads(json.dumps(artifact))
    changed["catalog"]["metricDefinitions"]["smart"]["task"] = "A different evaluation task"
    artifact_path.write_text(json.dumps(changed))
    result = run("repair_gate.py", "validate-artifact", str(work), succeeds=False)
    assert "Source meaning changed" in result.stderr
    changed = json.loads(json.dumps(artifact))
    changed["variants"] = changed["variants"][:len(changed["variants"]) // 2]
    changed["catalog"]["provenance"]["completeVariantCount"] = len(changed["variants"])
    if "adjustedVariantCount" in changed["catalog"]["provenance"]:
        changed["catalog"]["provenance"]["adjustedVariantCount"] = sum(any(origin["kind"] == "adjusted" for origin in variant["metricOrigins"].values()) for variant in changed["variants"])
    artifact_path.write_text(json.dumps(changed))
    result = run("repair_gate.py", "validate-artifact", str(work), succeeds=False)
    assert "coverage drop" in result.stderr, result.stderr
    workflow = (ROOT / ".github/workflows/repair-verify.yml").read_text()
    independent = workflow.split("  validate:\n", 1)[1].split("  merge:\n", 1)[0]
    assert "-r requirements.txt" in independent and "path: candidate" not in independent
    assert "validate-artifact acquired" in independent
    assert "needs.validate.result == 'success'" in workflow
    event["workflow_run"] = {"id": 9, "conclusion": "success"}
    event_path.write_text(json.dumps(event))
    driver = work / "heartbeat-driver.py"
    driver.write_text('import runpy, sys, urllib.request\nfrom pathlib import Path\nsys.path.insert(0,str(Path(sys.argv[1]).parent))\nclass Response:\n status=200\n def __enter__(self): return self\n def __exit__(self,*args): pass\ndef request(*args,**kwargs):\n print("CHECK_IN")\n return Response()\nurllib.request.urlopen=request\nrunpy.run_path(sys.argv[1],run_name="__main__")\n')
    heartbeat_environment = environment | {"DMS_CHECK_IN_URL": "https://nosnch.in/system-test-fixture"}
    result = subprocess.run([sys.executable, str(driver), str(ROOT / "scripts/heartbeat.py")], env=heartbeat_environment, capture_output=True, text=True)
    assert result.returncode == 0 and "CHECK_IN" in result.stdout, result.stderr
    event["workflow_run"]["id"] = 8
    event_path.write_text(json.dumps(event))
    result = subprocess.run([sys.executable, str(driver), str(ROOT / "scripts/heartbeat.py")], env=heartbeat_environment, capture_output=True, text=True)
    assert result.returncode == 0 and "CHECK_IN" not in result.stdout
    event["workflow_run"].update(id=9, conclusion="failure")
    event_path.write_text(json.dumps(event))
    result = subprocess.run([sys.executable, str(driver), str(ROOT / "scripts/heartbeat.py")], env=heartbeat_environment, capture_output=True, text=True)
    assert result.returncode == 0 and "CHECK_IN" not in result.stdout

print("System repair: single-use reservation, PR provenance, immutable head/base, exact-commit CI, independent artifact validation, no failure attestations/merge, success-only non-stale heartbeat passed")
