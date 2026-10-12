import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sync_incident import api, gh, load_state


def context():
    repository = os.environ["GITHUB_REPOSITORY"]
    state, _ = load_state(repository)
    incident = os.environ.get("REPAIR_INCIDENT", "")
    attempt = os.environ.get("REPAIR_ATTEMPT", "")
    if not incident.isdigit() or attempt not in {"1", "2"}:
        return None
    if state.get("deadline", 0) <= time.time():
        return None
    if state.get("phase") != "repair" or state.get("incident") != incident or str(state.get("attempts")) != attempt:
        return None
    if api(f"repos/{repository}/git/ref/heads/main")["object"]["sha"] != state["base_sha"]:
        return None
    catalog = json.loads(Path("catalog/model-selection-catalog.json").read_text())
    if not catalog["catalog"]["distribution"]["allowRedistribution"] and not api(f"repos/{repository}")["private"]:
        raise RuntimeError("Restricted catalog repair requires a private repository")
    return state


def prepare():
    state = context()
    for _ in range(12):
        if not state or state.get("repair_run") or os.environ.get("GITHUB_RUN_ATTEMPT", "1") != "1":
            break
        time.sleep(2)
        state = context()
    if not state or str(state.get("repair_run")) != os.environ["GITHUB_RUN_ID"] or os.environ.get("GITHUB_RUN_ATTEMPT", "1") != "1":
        with open(os.environ["GH_AW_SAFE_OUTPUTS"], "a") as output:
            output.write(json.dumps({"type": "noop", "message": "No current bounded repair reservation matches this dispatch"}) + "\n")
        raise RuntimeError("Rejected unreserved repair before any inference")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("active=true\n")
    path = Path("/tmp/gh-aw/agent/repair-context.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def select():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    run = event["workflow_run"]
    match = re.fullmatch(r"Catalog repair ([0-9]+) attempt ([12])", run.get("display_title", ""))
    if not match:
        raise RuntimeError("Unexpected repair workflow identity")
    os.environ["REPAIR_INCIDENT"], os.environ["REPAIR_ATTEMPT"] = match.groups()
    state = context()
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"incident={match[1]}\nattempt={match[2]}\n")
        if not state:
            output.write("active=false\n")
            return
        if run["id"] != state.get("repair_run") or run.get("run_attempt", 1) != 1:
            raise RuntimeError("Repair run does not match its single-use reservation")
        if run.get("head_repository", {}).get("full_name") != os.environ["GITHUB_REPOSITORY"] or run.get("head_branch") != "main" or run["head_sha"] != state["base_sha"]:
            raise RuntimeError("Repair did not execute on its reserved trusted main commit")
        if run["conclusion"] != "success":
            raise RuntimeError("Luna did not successfully finish the bounded repair attempt")
        title = f"[catalog-repair] incident {state['incident']} attempt {state['attempts']}"
        pulls = json.loads(gh("pr", "list", "--repo", os.environ["GITHUB_REPOSITORY"], "--label", "catalog-repair", "--state", "open", "--json", "number,title,headRefOid,headRefName,baseRefName,author,body"))
        candidates = [pull for pull in pulls if re.match(re.escape(title) + r"(?![0-9])", pull["title"])]
        if len(candidates) > 1:
            raise RuntimeError("Multiple candidate repair PRs")
        output.write("active=true\n")
        output.write(f"base={state['base_sha']}\n")
        if not candidates:
            output.write("has_patch=false\n")
            return
        pull = candidates[0]
        origin = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run['id']}"
        if pull["baseRefName"] != "main" or pull["author"]["login"] not in {"github-actions[bot]", "app/github-actions"} or not re.search(re.escape(origin) + r"(?![0-9])", pull["body"]):
            raise RuntimeError("Repair PR provenance is not the trusted Luna run")
        output.write(f"has_patch=true\npr={pull['number']}\nhead={pull['headRefOid']}\nbranch={pull['headRefName']}\n")


def verify_policy(trusted, candidate):
    policies = {
        "aa_web.py": {"validate_fast_definition", "FAST_DEFINITION_MARKERS"},
        "deepswe.py": {"load_manifest", "load_artifact", "attach_providers", "complete_metrics", "validate_leaderboard"},
    }
    for name, protected in policies.items():
        original = Path(trusted, "scripts", name)
        if not original.exists():
            continue
        before = ast.parse(original.read_text())
        after = ast.parse(Path(candidate, "scripts", name).read_text())
        def definitions(tree):
            found = {}
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name in protected:
                    found[node.name] = ast.dump(node, include_attributes=False)
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in protected:
                            found[target.id] = ast.dump(node, include_attributes=False)
            return found
        if definitions(before) != definitions(after):
            raise RuntimeError("Source semantic validation was modified")
        before_functions = {node.name: node for node in before.body if isinstance(node, ast.FunctionDef)}
        after_functions = {node.name: node for node in after.body if isinstance(node, ast.FunctionDef)}
        for function, original_function in before_functions.items():
            calls = [ast.dump(statement, include_attributes=False) for statement in original_function.body if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in protected for node in ast.walk(statement))]
            if calls:
                candidate_statements = {ast.dump(statement, include_attributes=False) for statement in (after_functions[function].body if function in after_functions else [])}
                if any(call not in candidate_statements for call in calls):
                    raise RuntimeError("Source semantic validator invocation was modified")
        if name == "deepswe.py":
            checks = [ast.dump(node, include_attributes=False) for node in before_functions["discover_release"].body if isinstance(node, ast.If) and any(marker in ast.dump(node.test) for marker in ("license", "expectedUnit", "expectedScope", "allowedHarnesses"))]
            candidate_checks = {ast.dump(node, include_attributes=False) for node in (after_functions["discover_release"].body if "discover_release" in after_functions else []) if isinstance(node, ast.If)}
            if any(check not in candidate_checks for check in checks):
                raise RuntimeError("Source licensing, scoring, scope, or harness guard was modified")


def verify():
    trusted, candidate, base, head = sys.argv[2:]
    changed = subprocess.check_output(["git", "-C", candidate, "diff", "--name-only", base, head], text=True).splitlines()
    allowed = {path for path in ("scripts/aa_web.py", "scripts/deepswe.py", "requirements.txt") if Path(trusted, path).exists()}
    if not changed or any(path not in allowed for path in changed):
        raise RuntimeError("Repair changes files outside the acquisition/dependency boundary")
    protected = ["schema", "sources", "tests", "scripts/maintenance.py", "scripts/validate_catalog.py", "scripts/build_catalog.py", "catalog"]
    for path in protected:
        original = Path(trusted, path)
        proposed = Path(candidate, path)
        if not original.exists():
            continue
        if original.is_dir():
            files = [file.relative_to(original) for file in original.rglob("*") if file.is_file() and "__pycache__" not in file.parts]
            for file in files:
                if Path(original, file).read_bytes() != Path(proposed, file).read_bytes():
                    raise RuntimeError("Trusted gate or published baseline was modified")
        elif original.read_bytes() != proposed.read_bytes():
            raise RuntimeError("Trusted gate was modified")
    verify_policy(trusted, candidate)
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"], cwd=candidate, check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=candidate, check=True)
    for test in ("system_maintenance.py", "system_incidents.py", "system_publication.py", "system_repair.py"):
        path = Path(candidate, "tests", test)
        if path.exists():
            subprocess.run([sys.executable, str(path.resolve())], cwd=candidate, check=True)
    subprocess.run([sys.executable, "scripts/build_catalog.py", "--output-dir", "dist"], cwd=candidate, check=True)
    subprocess.run([sys.executable, str(Path(trusted, "scripts/validate_catalog.py").resolve()), "dist/model-selection-catalog.json", str(Path(trusted, "schema/model-metrics-catalog.schema.json").resolve())], cwd=candidate, check=True)
    boundary = Path(trusted, "scripts/check_forbidden_source.py")
    if boundary.exists():
        subprocess.run([sys.executable, str(boundary.resolve())], cwd=candidate, check=True)


def validate_artifact():
    artifact = Path(sys.argv[2]).resolve() / "model-selection-catalog.json"
    subprocess.run([sys.executable, "scripts/validate_catalog.py", str(artifact), "schema/model-metrics-catalog.schema.json"], check=True)
    catalog = json.loads(artifact.read_text())
    previous = json.loads(Path("catalog/model-selection-catalog.json").read_text())
    from maintenance import prepare_publication
    with tempfile.TemporaryDirectory() as output:
        prepare_publication(catalog, previous, output)
    if Path("scripts/aa_web.py").exists():
        from build_catalog import validate_coverage
        validate_coverage(range(catalog["catalog"]["provenance"]["sourceModelCount"]), catalog)


if __name__ == "__main__":
    {"prepare": prepare, "select": select, "verify": verify, "validate-artifact": validate_artifact}[sys.argv[1]]()
