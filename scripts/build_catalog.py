#!/usr/bin/env python3
"""Build the public metrics catalog from the current official DeepSWE release."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from deepswe import complete_metrics, discover_release, fetch_release, load_manifest
from maintenance import prepare_publication, write_json

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
    parser.add_argument("--config", default=ROOT / "sources/deepswe.json", type=Path)
    parser.add_argument("--manifest", type=Path, help="Replay a recorded release with checksum verification")
    parser.add_argument("--source", type=Path, help="Use a local leaderboard artifact")
    parser.add_argument("--trials", type=Path, help="Use a local trials artifact")
    parser.add_argument("--previous-catalog", default=ROOT / "catalog/model-selection-catalog.json", type=Path)
    parser.add_argument("--generated-at")
    return parser.parse_args()


def creator(model):
    prefix = model.split("-")[0]
    return CREATORS.get(prefix, "Unknown")


def normalize_variant(row, release):
    effort = row.get("reasoning_effort")
    return {
        "id": f"deepswe:config:{row['config']}",
        "creator": creator(row["model"]),
        "displayName": f"{MODEL_NAMES.get(row['model'], row['model'])} ({effort})" if effort else MODEL_NAMES.get(row["model"], row["model"]),
        "checkpoint": row["model"],
        "quantization": None,
        "reasoning": {"label": effort} if effort else None,
        "metrics": {
            "smart": row["pass_at_1"],
            "fast": row["mean_duration_seconds"],
            "cheap": row["mean_cost_usd"],
        },
        "metricOrigins": {name: {"kind": "source", "benchmarkVersion": release} for name in ("smart", "fast", "cheap")},
        "provenance": {
            "source": "DeepSWE",
            "sourceConfig": row["config"],
            "sourceModel": row["model"],
            "sourceProvider": row["provider"],
            "sourceProviders": row.get("providers", [row["provider"]]),
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


def build_catalog(leaderboard, manifest, generated_at=None):
    rows = leaderboard["rows"]
    timestamp = generated_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    variants = sorted((normalize_variant(row, manifest["release"]) for row in rows if complete_metrics(row)), key=lambda item: item["id"])
    catalog = {
        "schemaVersion": 2,
        "catalog": {
            "id": "deepswe",
            "name": f"DeepSWE {manifest['release']}",
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
                "sourceModelCount": len(rows),
                "excludedVariantCount": len(rows) - len(variants),
                "taskCount": leaderboard["n_tasks_in_set"],
                "harnesses": sorted({row["harness"] for row in rows}),
            },
        },
        "variants": variants,
    }
    return catalog


def main():
    args = parse_args()
    if args.manifest:
        manifest = load_manifest(args.manifest)
        leaderboard = fetch_release(manifest, args.source, args.trials)
    else:
        if args.source or args.trials:
            raise SystemExit("--source and --trials require --manifest")
        leaderboard, manifest = discover_release(json.loads(args.config.read_text()))
    catalog = build_catalog(leaderboard, manifest, args.generated_at)
    previous = json.loads(args.previous_catalog.read_text()) if args.previous_catalog.is_file() else None
    prepare_publication(catalog, previous, args.output_dir)
    write_json(args.output_dir / "source-manifest.json", manifest)
    (args.output_dir / "schema.json").write_text((ROOT / "schema/model-metrics-catalog.schema.json").read_text())
    print(f"Wrote {len(catalog['variants'])} Complete Variants from DeepSWE {manifest['release']}")


if __name__ == "__main__":
    main()
