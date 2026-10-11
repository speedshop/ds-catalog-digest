"""Exercise the actual publication shell against a local Git remote."""

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/publish.yml").read_text()
publication = "\n".join(line[10:] for line in workflow.rsplit("        run: |\n", 1)[1].splitlines())
FAKE_GH = '''import json, os, subprocess, sys
from pathlib import Path
path = Path(os.environ["PUBLICATION_PR_STATE"])
state = json.loads(path.read_text())
args = sys.argv[1:]
remote = os.environ["PUBLICATION_REMOTE"]
if args[:2] == ["repo", "view"]:
    print(os.environ.get("PUBLICATION_IS_PRIVATE", "true"))
elif args[:2] == ["pr", "list"]:
    if state["state"] == "OPEN":
        print("https://example.com/pull/1")
elif args[:2] == ["pr", "create"]:
    state["creates"] += 1
    state["state"] = "OPEN"
    print("https://example.com/pull/1")
elif args[:2] == ["pr", "edit"]:
    assert state["state"] == "OPEN"
    state["edits"] += 1
elif args[:2] == ["workflow", "run"]:
    pass
elif args[:2] == ["run", "list"]:
    print("100")
elif args[:2] == ["run", "watch"]:
    if os.environ.get("PUBLICATION_CI_FAIL") == "true":
        raise SystemExit("Simulated CI failure")
elif args[0] == "api":
    state["attestations"] += 1
elif args[:2] == ["pr", "merge"]:
    if "--disable-auto" in args:
        state["auto"] = False
        state["disables"] += 1
    else:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        subprocess.run(["git", "--git-dir", remote, "update-ref", "refs/heads/main", head], check=True)
        subprocess.run(["git", "--git-dir", remote, "update-ref", "-d", "refs/heads/catalog-publish"], check=True)
        state["state"] = "MERGED"
elif args[:2] == ["pr", "view"]:
    print(str(state["auto"]).lower() if "autoMergeRequest" in args else state["state"])
elif args[:2] == ["pr", "close"]:
    state["state"] = "CLOSED"
    state["closes"] += 1
    subprocess.run(["git", "--git-dir", remote, "update-ref", "-d", "refs/heads/catalog-publish"], check=True)
else:
    raise SystemExit("Unexpected command")
path.write_text(json.dumps(state))
'''


def git(directory, *arguments):
    result = subprocess.run(["git", *arguments], cwd=directory, check=True, capture_output=True, text=True)
    return result.stdout.strip()


with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    remote = work / "remote.git"
    seed = work / "seed"
    runner = work / "runner"
    tools = work / "tools"
    tools.mkdir()
    fake = tools / "gh"
    fake.write_text(f"#!{sys.executable}\n" + FAKE_GH)
    fake.chmod(0o755)
    state_path = work / "publication-state.json"
    state_path.write_text(json.dumps({"state": "NONE", "creates": 0, "edits": 0, "closes": 0, "attestations": 0, "auto": False, "disables": 0}))
    git(work, "init", "--bare", str(remote))
    git(work, "init", "--initial-branch=main", str(seed))
    git(seed, "config", "core.hooksPath", "/dev/null")
    git(seed, "config", "user.name", "System check")
    git(seed, "config", "user.email", "system@example.com")
    (seed / "catalog").mkdir()
    catalog = json.loads((ROOT / "catalog/model-selection-catalog.json").read_text())
    encoded = json.dumps(catalog, sort_keys=True) + "\n"
    (seed / "catalog/model-selection-catalog.json").write_text(encoded)
    source_manifest = ROOT / "catalog/source-manifest.json"
    if source_manifest.exists():
        (seed / "catalog/source-manifest.json").write_bytes(source_manifest.read_bytes())
    git(seed, "add", "catalog")
    git(seed, "commit", "--no-gpg-sign", "-m", "Initial catalog")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "--set-upstream", "origin", "main")
    git(work, "clone", "--branch", "main", str(remote), str(runner))
    git(runner, "config", "core.hooksPath", "/dev/null")
    (runner / "dist").mkdir()
    artifact = runner / "dist/model-selection-catalog.json"
    artifact.write_text(encoded)
    if source_manifest.exists():
        (runner / "dist/source-manifest.json").write_bytes(source_manifest.read_bytes())
    initial = git(runner, "rev-parse", "HEAD")
    environment = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"], PUBLICATION_REMOTE=str(remote), PUBLICATION_PR_STATE=str(state_path), GITHUB_SHA=initial, GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1", GITHUB_SERVER_URL="https://example.com", GITHUB_REPOSITORY="example/catalog", GH_TOKEN="system-check-only")

    def publish(succeeds=True):
        result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", publication], cwd=runner, env=environment, capture_output=True, text=True)
        assert (result.returncode == 0) == succeeds, result.stdout + result.stderr
        return result

    if "Require a private repository" in workflow:
        environment["PUBLICATION_IS_PRIVATE"] = "false"
        publish(succeeds=False)
        assert git(work, "--git-dir", str(remote), "rev-parse", "main") == initial
        environment["PUBLICATION_IS_PRIVATE"] = "true"
    publish()
    assert git(work, "--git-dir", str(remote), "rev-parse", "main") == initial
    git(runner, "switch", "main")
    changed = copy.deepcopy(catalog)
    changed["variants"][0]["metrics"]["smart"] *= 0.99
    artifact.write_text(json.dumps(changed, sort_keys=True) + "\n")
    environment["GITHUB_RUN_ID"] = "2"
    environment["PUBLICATION_CI_FAIL"] = "true"
    publish(succeeds=False)
    assert git(work, "--git-dir", str(remote), "rev-parse", "main") == initial
    state = json.loads(state_path.read_text())
    assert state["creates"] == 1 and state["state"] == "OPEN" and state["attestations"] == 0
    state["auto"] = True
    state_path.write_text(json.dumps(state))
    environment["PUBLICATION_CI_FAIL"] = "false"
    publish()
    state = json.loads(state_path.read_text())
    assert state["creates"] == 1 and state["edits"] == 1 and state["disables"] == 1 and state["state"] == "MERGED"
    updated = git(work, "--git-dir", str(remote), "rev-parse", "main")
    assert updated != initial
    published = json.loads(git(work, "--git-dir", str(remote), "show", "main:catalog/model-selection-catalog.json"))
    assert published == changed
    if source_manifest.exists():
        recorded = git(work, "--git-dir", str(remote), "show", "main:catalog/source-manifest.json")
        assert json.loads(recorded) == json.loads(source_manifest.read_text())
    environment["GITHUB_RUN_ID"] = "3"
    publish(succeeds=False)
    assert git(work, "--git-dir", str(remote), "rev-parse", "main") == updated
    git(runner, "switch", "main")
    git(runner, "reset", "--hard", updated)
    environment["GITHUB_SHA"] = updated
    environment["GITHUB_RUN_ID"] = "4"
    publish()
    assert git(work, "--git-dir", str(remote), "rev-parse", "main") == updated
    newer = copy.deepcopy(changed)
    newer["variants"][0]["metrics"]["smart"] *= 0.99
    artifact.write_text(json.dumps(newer, sort_keys=True) + "\n")
    environment["PUBLICATION_CI_FAIL"] = "true"
    publish(succeeds=False)
    assert json.loads(state_path.read_text())["state"] == "OPEN"
    artifact.write_text(json.dumps(changed, sort_keys=True) + "\n")
    publish()
    state = json.loads(state_path.read_text())
    assert state["creates"] == 2 and state["closes"] == 1 and state["state"] == "CLOSED"
    assert git(work, "--git-dir", str(remote), "rev-parse", "main") == updated

print("System publication: exact workflow shell, no-op, atomic update, failed-CI retry reuses PR, obsolete-PR retirement, stale-base rejection, recovery passed")
