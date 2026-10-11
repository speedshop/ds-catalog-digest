"""Exercise the live discovery pipeline against an evolving HTTP source."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "sources/deepswe.json").read_text())
row = {
    "config": "fixture", "model": "new-model", "provider": "example", "harness": "mini-swe-agent",
    "reasoning_effort": "low", "pass_at_1": 0.5, "mean_duration_seconds": 10, "mean_cost_usd": 1,
    "n_attempted": 4, "n_passed": 2, "n_tasks_attempted": 1, "n_runs": 4, "ci_lo": 0.25, "ci_hi": 0.75,
}
leaderboard = {
    "generated_at": "2030-01-01T00:00:00Z", "n_tasks_in_set": 1,
    "scope": config["expectedScope"], "unit": config["expectedUnit"],
    "rows": [dict(copy.deepcopy(row), config=f"config-{index}") for index in range(10)],
}
state = {"release": "v1.1", "leaderboard": leaderboard, "license": "cc-by-4.0", "pageRequests": 0}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *arguments):
        pass

    def do_GET(self):
        if self.path == "/":
            state["pageRequests"] += 1
            if state["pageRequests"] == 1:
                self.send_response(503)
                self.end_headers()
                return
            payload = f'<a href="/artifacts/{state["release"]}/leaderboard-live.json">Leaderboard</a>'.encode()
        elif self.path == "/dataset":
            payload = json.dumps({"cardData": {"license": state["license"]}}).encode()
        elif self.path.endswith("/leaderboard-live.json"):
            payload = json.dumps(state["leaderboard"]).encode()
        elif self.path.endswith("/trials.json"):
            payload = json.dumps({"rows": [{"config": r["config"], "provider": "example"} for r in state["leaderboard"]["rows"]]}).encode()
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(payload)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        base_url = f"http://127.0.0.1:{server.server_port}/"
        config.update(methodologyUrl=base_url, datasetUrl=base_url + "dataset", datasetMetadataUrl=base_url + "dataset")
        config_path = work / "config.json"
        config_path.write_text(json.dumps(config))
        previous = work / "published.json"
        output = work / "output"
        published = output / "model-selection-catalog.json"

        def command(script, *arguments, succeeds=True):
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, arguments)], capture_output=True, text=True)
            assert (result.returncode == 0) == succeeds, result.stdout + result.stderr
            return result

        def build(timestamp, succeeds=True):
            return command("build_catalog.py", "--config", config_path, "--previous-catalog", previous, "--output-dir", output, "--generated-at", timestamp, succeeds=succeeds)

        build("2030-01-01T00:00:00Z")
        assert state["pageRequests"] == 2
        command("validate_catalog.py", published, output / "schema.json")
        previous.write_bytes(published.read_bytes())
        original = previous.read_bytes()
        build("2030-01-02T00:00:00Z")
        assert published.read_bytes() == original
        manifest_before = json.loads((output / "source-manifest.json").read_text())
        state["release"] = "v1.2"
        leaderboard["rows"][0]["mean_cost_usd"] = 2
        leaderboard["rows"][1]["mean_cost_usd"] = None
        leaderboard["rows"] = leaderboard["rows"][1:] + [dict(copy.deepcopy(row), config="new-config")]
        build("2030-01-03T00:00:00Z")
        command("validate_catalog.py", published, output / "schema.json")
        catalog = json.loads(published.read_text())
        ids = {variant["id"] for variant in catalog["variants"]}
        assert "deepswe:config:config-0" not in ids and "deepswe:config:new-config" in ids
        assert "deepswe:config:config-1" not in ids
        assert all("aliases" not in variant for variant in catalog["variants"])
        manifest_after = json.loads((output / "source-manifest.json").read_text())
        assert manifest_after["release"] == "v1.2"
        assert manifest_before["leaderboardSha256"] != manifest_after["leaderboardSha256"]
        assert manifest_after["leaderboardSha256"] == hashlib.sha256(json.dumps(leaderboard).encode()).hexdigest()
        previous.write_bytes(published.read_bytes())
        stable = previous.read_bytes()
        for key, replacement in (("unit", "different scoring"), ("scope", "different evaluation")):
            original_value = leaderboard[key]
            leaderboard[key] = replacement
            build("2030-01-04T00:00:00Z", succeeds=False)
            assert previous.read_bytes() == stable
            leaderboard[key] = original_value
        state["license"] = "restricted"
        build("2030-01-05T00:00:00Z", succeeds=False)
        assert previous.read_bytes() == stable
        state["license"] = "cc-by-4.0"
        rows = leaderboard["rows"]
        leaderboard["rows"] = rows[:3]
        failed = build("2030-01-06T00:00:00Z", succeeds=False)
        assert "Suspicious" in failed.stderr
        assert previous.read_bytes() == stable
        leaderboard["rows"] = rows
        build("2030-01-07T00:00:00Z")
        assert published.read_bytes() == stable
        state["release"] = "v1.1"
        failed = build("2030-01-08T00:00:00Z", succeeds=False)
        assert "Source benchmark version regressed" in failed.stderr
        assert previous.read_bytes() == stable
finally:
    server.shutdown()
    server.server_close()

print("System maintenance: HTTP retry, release discovery, checksum adoption, additions, removals, exclusions, no churn, semantic/license gates, recovery passed")
