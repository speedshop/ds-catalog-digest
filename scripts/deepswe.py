"""Acquire and validate pinned DeepSWE leaderboard artifacts."""

import hashlib
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen

REQUIRED_METRICS = ("pass_at_1", "mean_duration_seconds", "mean_cost_usd")


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    required = {
        "schemaVersion",
        "release",
        "leaderboardUrl",
        "leaderboardSha256",
        "trialsUrl",
        "trialsSha256",
        "datasetUrl",
        "methodologyUrl",
        "license",
        "attribution",
    }
    if manifest.get("schemaVersion") != 1 or set(manifest) != required:
        raise ValueError("Invalid DeepSWE source manifest")
    return manifest


def fetch_bytes(url):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ds-catalog-digest/1"})
    with urlopen(request, timeout=120) as response:
        return response.read()


def load_artifact(url, expected_sha256, source_path=None):
    payload = Path(source_path).read_bytes() if source_path else fetch_bytes(url)
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"DeepSWE artifact checksum mismatch: expected {expected_sha256}, got {digest}")
    return json.loads(payload)


def fetch_release(manifest, leaderboard_path=None, trials_path=None):
    leaderboard = load_artifact(
        manifest["leaderboardUrl"], manifest["leaderboardSha256"], leaderboard_path
    )
    trials = load_artifact(manifest["trialsUrl"], manifest["trialsSha256"], trials_path)
    validate_leaderboard(leaderboard)
    attach_providers(leaderboard["rows"], trials)
    return leaderboard


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
        if len(config_providers) != 1:
            raise ValueError(f"{row['config']} does not have exactly one recorded provider")
        row["provider"] = next(iter(config_providers))


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
        for field in ("model", "harness", *REQUIRED_METRICS):
            if row.get(field) is None:
                raise ValueError(f"{row['config']} is missing {field}")
        for field in REQUIRED_METRICS:
            value = row[field]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                raise ValueError(f"{row['config']} has invalid {field}")
        if not 0 <= row["pass_at_1"] <= 1:
            raise ValueError(f"{row['config']} has invalid pass_at_1")
        if row["mean_duration_seconds"] < 0 or row["mean_cost_usd"] <= 0:
            raise ValueError(f"{row['config']} is not a Complete Variant")
