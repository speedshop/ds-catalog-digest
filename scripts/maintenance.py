"""Prepare validated, meaningful catalog updates and acquisition diagnostics."""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

MAX_COVERAGE_DROP = 0.2


def write_json(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n")


def prepare_publication(catalog, previous, output_dir):
    output_dir = Path(output_dir)
    before = {variant["id"]: variant for variant in (previous or {}).get("variants", [])}
    after = {variant["id"]: variant for variant in catalog["variants"]}
    if len(after) != len(catalog["variants"]):
        raise ValueError("Catalog contains duplicate variant IDs")
    observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    report = {
        "observedAt": observed_at,
        "benchmarkVersion": catalog["catalog"]["version"],
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "updated": sorted(key for key in before.keys() & after.keys() if before[key] != after[key]),
        "completeVariantCount": len(after),
        "excludedVariantCount": catalog["catalog"]["provenance"].get("sourceModelCount", len(after)) - len(after),
    }
    write_json(output_dir / "acquisition-report.json", report)
    if not after:
        raise ValueError("Source contains no Complete Variants")
    if previous:
        old_metadata = previous["catalog"]
        metadata = catalog["catalog"]
        old_version = [int(part) for part in old_metadata["version"].removeprefix("v").split(".")]
        new_version = [int(part) for part in metadata["version"].removeprefix("v").split(".")]
        if new_version + [0] * (3 - len(new_version)) < old_version + [0] * (3 - len(old_version)):
            raise ValueError("Source benchmark version regressed")
        for field in ("distribution", "metricDefinitions"):
            if old_metadata[field] != metadata[field]:
                raise ValueError(f"Source meaning changed: {field}")
        old_count = old_metadata["provenance"].get("sourceModelCount", len(before))
        new_count = metadata["provenance"].get("sourceModelCount", len(after))
        if new_count < old_count * (1 - MAX_COVERAGE_DROP):
            raise ValueError(f"Suspicious source coverage drop: {new_count} < {old_count}")
        if len(after) < len(before) * (1 - MAX_COVERAGE_DROP):
            raise ValueError(f"Suspicious Complete Variant coverage drop: {len(after)} < {len(before)}")
        comparable = copy.deepcopy(catalog)
        comparable["catalog"]["generatedAt"] = old_metadata["generatedAt"]
        if comparable == previous:
            catalog["catalog"]["generatedAt"] = old_metadata["generatedAt"]
    write_json(output_dir / "model-selection-catalog.json", catalog)
