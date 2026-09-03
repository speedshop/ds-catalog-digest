#!/usr/bin/env python3
"""Build the public model-selection catalog from a pinned DeepSWE release."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from deepswe import fetch_release, load_manifest
from route_mappings import candidate_queue, compile_aliases, load_decisions, route_fingerprint, variant_id

ROOT = Path(__file__).resolve().parents[1]
CREATORS = {
    "claude": "Anthropic",
    "deepseek": "DeepSeek",
    "gemini": "Google",
    "glm": "Z AI",
    "gpt": "OpenAI",
    "grok": "xAI",
    "kimi": "Moonshot AI",
    "muse": "Meta",
    "qwen": "Alibaba",
    "qwen3": "Alibaba",
}
MODEL_NAMES = {
    "claude-fable-5": "Claude Fable 5",
    "claude-opus-4-8": "Claude Opus 4.8",
    "claude-opus-5": "Claude Opus 5",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-sonnet-5": "Claude Sonnet 5",
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
    "gemini-3-1-pro-preview": "Gemini 3.1 Pro Preview",
    "gemini-3-5-flash": "Gemini 3.5 Flash",
    "gemini-3-6-flash": "Gemini 3.6 Flash",
    "gemini-3-7-flash": "Gemini 3.7 Flash",
    "gemini-3-8-flash": "Gemini 3.8 Flash",
    "glm-5-2": "GLM-5.2",
    "glm-5-3": "GLM-5.3",
    "glm-5-3-flash": "GLM-5.3-Flash",
    "gpt-5-4": "GPT-5.4",
    "gpt-5-5": "GPT-5.5",
    "gpt-5-6-luna": "GPT-5.6 Luna",
    "gpt-5-6-sol": "GPT-5.6 Sol",
    "gpt-5-6-terra": "GPT-5.6 Terra",
    "grok-4-5": "Grok 4.5",
    "grok-4-6": "Grok 4.6",
    "kimi-k2-7-code": "Kimi K2.7 Code",
    "kimi-k3": "Kimi K3",
    "muse-spark-1-1": "Muse Spark 1.1",
    "muse-spark-1-2": "Muse Spark 1.2",
    "qwen3-8-max": "Qwen3.8 Max",
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=ROOT / "dist", type=Path)
    parser.add_argument("--manifest", default=ROOT / "sources/deepswe-v1.1.json", type=Path)
    parser.add_argument("--source", type=Path, help="Use a local leaderboard artifact")
    parser.add_argument("--trials", type=Path, help="Use a local trials artifact")
    parser.add_argument("--pi-catalog", default=ROOT / "mappings/pi-model-catalog.json", type=Path)
    parser.add_argument("--route-decisions", default=ROOT / "mappings/route-decisions.json", type=Path)
    parser.add_argument("--previous-pi-catalog", default=ROOT / "mappings/pi-model-catalog.json", type=Path)
    parser.add_argument("--generated-at")
    return parser.parse_args()


def creator(model):
    prefix = model.split("-")[0]
    if prefix not in CREATORS:
        raise ValueError(f"Unknown creator for {model}")
    return CREATORS[prefix]


def normalize_variant(row, aliases):
    effort = row.get("reasoning_effort")
    return {
        "id": variant_id(row),
        "creator": creator(row["model"]),
        "displayName": f"{MODEL_NAMES[row['model']]} ({effort})" if effort else MODEL_NAMES[row["model"]],
        "checkpoint": row["model"],
        "quantization": None,
        "reasoning": {"label": effort} if effort else None,
        "metrics": {
            "smart": row["pass_at_1"],
            "fast": row["mean_duration_seconds"],
            "cheap": row["mean_cost_usd"],
        },
        "aliases": aliases[variant_id(row)],
        "provenance": {
            "source": "DeepSWE",
            "sourceConfig": row["config"],
            "sourceModel": row["model"],
            "sourceProvider": row["provider"],
            "harness": row["harness"],
            "attempted": row["n_attempted"],
            "passed": row["n_passed"],
            "tasksAttempted": row["n_tasks_attempted"],
            "runs": row["n_runs"],
            "smartConfidenceInterval95": [row["ci_lo"], row["ci_hi"]],
            "smartAggregation": "pass_at_1",
            "fastAggregation": "mean_duration_seconds",
            "cheapAggregation": "mean_cost_usd",
        },
    }


def build_catalog(leaderboard, manifest, pi_catalog, decisions, generated_at=None):
    rows = leaderboard["rows"]
    aliases, stale = compile_aliases(rows, pi_catalog, decisions)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    variants = sorted((normalize_variant(row, aliases) for row in rows), key=lambda item: item["id"])
    catalog = {
        "schemaVersion": 1,
        "catalog": {
            "id": "deepswe-v1.1",
            "name": "DeepSWE v1.1",
            "version": manifest["release"],
            "generatedAt": timestamp,
            "sourceUpdatedAt": leaderboard["generated_at"],
            "distribution": {
                "classification": "redistributable",
                "termsUrl": manifest["datasetUrl"],
                "attribution": manifest["attribution"],
                "allowRedistribution": True,
            },
            "metricDefinitions": {
                "smart": {"unit": "pass-rate", "better": "higher", "task": "DeepSWE task pass@1", "methodologyUrl": manifest["methodologyUrl"]},
                "fast": {"unit": "seconds-per-deepswe-task", "better": "lower", "task": "Mean end-to-end DeepSWE trial duration", "methodologyUrl": manifest["methodologyUrl"]},
                "cheap": {"unit": "USD-per-deepswe-task", "better": "lower", "task": "Mean reported inference cost per DeepSWE trial", "methodologyUrl": manifest["methodologyUrl"]},
            },
            "provenance": {
                "source": "DeepSWE",
                "datasetUrl": manifest["datasetUrl"],
                "leaderboardUrl": manifest["leaderboardUrl"],
                "trialsUrl": manifest["trialsUrl"],
                "leaderboardSha256": manifest["leaderboardSha256"],
                "trialsSha256": manifest["trialsSha256"],
                "release": manifest["release"],
                "license": manifest["license"],
                "configurationCount": len(rows),
                "taskCount": leaderboard["n_tasks_in_set"],
                "harnesses": sorted({row["harness"] for row in rows}),
            },
        },
        "variants": variants,
    }
    return catalog, aliases, candidate_queue(rows, pi_catalog, decisions, stale), stale


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n")


def pi_catalog_diff(previous, current):
    def indexed(document):
        return {(route["provider"], route["modelId"]): route for route in document["routes"]}

    old = indexed(previous)
    new = indexed(current)
    return {
        "schemaVersion": 1,
        "added": [{"provider": key[0], "modelId": key[1]} for key in sorted(new.keys() - old.keys())],
        "removed": [{"provider": key[0], "modelId": key[1]} for key in sorted(old.keys() - new.keys())],
        "changed": [
            {"provider": key[0], "modelId": key[1]}
            for key in sorted(old.keys() & new.keys())
            if route_fingerprint(old[key]) != route_fingerprint(new[key])
        ],
    }


def main():
    args = parse_args()
    manifest = load_manifest(args.manifest)
    leaderboard = fetch_release(manifest, args.source, args.trials)
    pi_catalog = json.loads(args.pi_catalog.read_text())
    decisions = load_decisions(args.route_decisions)
    previous_pi_catalog = json.loads(args.previous_pi_catalog.read_text())
    catalog, aliases, candidates, stale = build_catalog(leaderboard, manifest, pi_catalog, decisions, args.generated_at)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "model-selection-catalog.json", catalog)
    write_json(args.output_dir / "model-aliases.json", {"schemaVersion": 1, "variants": aliases})
    write_json(args.output_dir / "route-candidates.json", candidates)
    write_json(args.output_dir / "pi-catalog-diff.json", pi_catalog_diff(previous_pi_catalog, pi_catalog))
    (args.output_dir / "schema.json").write_text((ROOT / "schema/model-selection-catalog-v1.schema.json").read_text())
    routed = sum(bool(value) for value in aliases.values())
    audit = [
        "# Pi Provider Route audit",
        "",
        f"- DeepSWE release: {manifest['release']}",
        f"- Complete Variants: {len(catalog['variants'])}",
        f"- Variants with verified Provider Routes: {routed}",
        f"- Verified Provider Routes: {sum(map(len, aliases.values()))}",
        f"- Route Candidates: {len(candidates['candidates'])}",
        f"- Stale accepted routes: {len(stale)}",
        "",
        "## Unresolved configurations",
        "",
        "| Configuration | Reason |",
        "|---|---|",
        *[f"| `{item['sourceConfig']}` | {item['reason']} |" for item in candidates["candidates"]],
        "",
    ]
    (args.output_dir / "ALIAS_AUDIT.md").write_text("\n".join(audit))
    print(f"Wrote {len(catalog['variants'])} Complete Variants from DeepSWE {manifest['release']}")


if __name__ == "__main__":
    main()
