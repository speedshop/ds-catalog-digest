"""Acquire official DeepSWE releases and validate their metric semantics."""

import hashlib
import json
import math
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

REQUIRED_METRICS = ("pass_at_1", "mean_duration_seconds", "mean_cost_usd")


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    required = {
        "schemaVersion", "release", "leaderboardUrl", "leaderboardSha256",
        "trialsUrl", "trialsSha256", "datasetUrl", "methodologyUrl", "license", "attribution",
    }
    if manifest.get("schemaVersion") != 1 or set(manifest) != required:
        raise ValueError("Invalid DeepSWE source manifest")
    return manifest


def fetch_bytes(url):
    request = Request(url, headers={"User-Agent": "ds-catalog-digest/2"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=60) as response:
                return response.read()
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
            retry_after = error.headers.get("Retry-After", "")
            delay = min(int(retry_after), 60) if retry_after.isdigit() else 2**attempt
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            delay = 2**attempt
        time.sleep(delay)


def load_artifact(url, expected_sha256, source_path=None):
    payload = Path(source_path).read_bytes() if source_path else fetch_bytes(url)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"DeepSWE artifact checksum mismatch: expected {expected_sha256}, got {digest}")
    return json.loads(payload)


def fetch_release(manifest, leaderboard_path=None, trials_path=None):
    leaderboard = load_artifact(manifest["leaderboardUrl"], manifest["leaderboardSha256"], leaderboard_path)
    trials = load_artifact(manifest["trialsUrl"], manifest["trialsSha256"], trials_path)
    validate_leaderboard(leaderboard)
    attach_providers(leaderboard["rows"], trials)
    return leaderboard


def discover_release(config):
    html = fetch_bytes(config["methodologyUrl"]).decode("utf-8")
    paths = set(re.findall(r"/artifacts/(v\d+(?:\.\d+)*)/leaderboard-live\.json", html))
    if not paths:
        raise ValueError("Official DeepSWE page contains no recognized leaderboard release")
    release = max(paths, key=lambda value: tuple(int(part) for part in value[1:].split(".")))
    dataset = json.loads(fetch_bytes(config["datasetMetadataUrl"]))
    if dataset.get("cardData", {}).get("license") != "cc-by-4.0":
        raise ValueError("DeepSWE source license changed or disappeared")
    leaderboard_url = urljoin(config["methodologyUrl"], f"/artifacts/{release}/leaderboard-live.json")
    trials_url = urljoin(config["methodologyUrl"], f"/artifacts/{release}/trials.json")
    leaderboard_bytes = fetch_bytes(leaderboard_url)
    trials_bytes = fetch_bytes(trials_url)
    leaderboard = json.loads(leaderboard_bytes)
    trials = json.loads(trials_bytes)
    if leaderboard.get("unit") != config["expectedUnit"] or leaderboard.get("scope") != config["expectedScope"]:
        raise ValueError("DeepSWE scoring or aggregation definition changed")
    validate_leaderboard(leaderboard)
    if any(row["harness"] not in config["allowedHarnesses"] for row in leaderboard["rows"]):
        raise ValueError("DeepSWE evaluation harness changed")
    attach_providers(leaderboard["rows"], trials)
    manifest = {
        "schemaVersion": 1,
        "release": release,
        "leaderboardUrl": leaderboard_url,
        "leaderboardSha256": hashlib.sha256(leaderboard_bytes).hexdigest(),
        "trialsUrl": trials_url,
        "trialsSha256": hashlib.sha256(trials_bytes).hexdigest(),
        "datasetUrl": config["datasetUrl"],
        "methodologyUrl": config["methodologyUrl"],
        "license": "CC-BY-4.0",
        "attribution": config["attribution"],
    }
    return leaderboard, manifest


def attach_providers(rows, trials_document):
    trials = trials_document.get("rows")
    if not isinstance(trials, list) or not trials:
        raise ValueError("DeepSWE trials artifact must contain rows")
    providers = {}
    for trial in trials:
        config = trial.get("config")
        provider = trial.get("provider")
        if not config or not provider:
            raise ValueError("Every DeepSWE trial must identify its configuration and provider")
        providers.setdefault(config, set()).add(provider)
    for row in rows:
        config_providers = providers.get(row["config"], set())
        if not config_providers or (row.get("provider") and row["provider"] not in config_providers):
            raise ValueError(f"{row['config']} has inconsistent recorded providers")
        row["providers"] = sorted(config_providers)
        if "provider" not in row:
            row["provider"] = next(iter(config_providers)) if len(config_providers) == 1 else None


def complete_metrics(row):
    return all(row.get(field) is not None for field in REQUIRED_METRICS) and row["mean_duration_seconds"] > 0 and row["mean_cost_usd"] > 0


def validate_leaderboard(document):
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("DeepSWE leaderboard must contain rows")
    configs = [row.get("config") for row in rows]
    if any(not isinstance(config, str) or not config for config in configs):
        raise ValueError("Every DeepSWE row must identify its configuration")
    if len(configs) != len(set(configs)):
        raise ValueError("DeepSWE leaderboard contains duplicate configurations")
    for row in rows:
        for field in ("model", "harness"):
            if not isinstance(row.get(field), str) or not row[field]:
                raise ValueError(f"{row['config']} is missing {field}")
        for field in REQUIRED_METRICS:
            if field not in row:
                raise ValueError(f"{row['config']} is missing {field}")
            value = row[field]
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError(f"{row['config']} has invalid {field}")
        if row["pass_at_1"] is not None and not 0 <= row["pass_at_1"] <= 1:
            raise ValueError(f"{row['config']} has invalid pass_at_1")
        if any(row[field] is not None and row[field] < 0 for field in REQUIRED_METRICS[1:]):
            raise ValueError(f"{row['config']} has negative efficiency metrics")
