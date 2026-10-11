#!/usr/bin/env python3
"""Validate a public metrics catalog against the shared JSON Schema."""

import argparse
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def reject_json_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("schema", type=Path)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(), parse_constant=reject_json_constant)
    schema = json.loads(args.schema.read_text(), parse_constant=reject_json_constant)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(catalog)

    distribution = catalog["catalog"]["distribution"]
    if distribution["classification"] != "redistributable" or distribution["allowRedistribution"] is not True:
        raise ValueError("DeepSWE catalog must remain redistributable")
    if catalog["catalog"]["provenance"]["license"] != "CC-BY-4.0":
        raise ValueError("DeepSWE license changed")
    for variant in catalog["variants"]:
        if not all(math.isfinite(variant["metrics"][name]) for name in ("smart", "fast", "cheap")):
            raise ValueError(f"Variant contains a non-finite metric: {variant['id']}")
        if variant["metrics"]["cheap"] <= 0:
            raise ValueError(f"Variant has unavailable Cheap metric: {variant['id']}")
        if any(origin != {"kind": "source", "benchmarkVersion": catalog["catalog"]["version"]} for origin in variant["metricOrigins"].values()):
            raise ValueError(f"DeepSWE metrics must come from the recorded release: {variant['id']}")

    ids = [variant["id"] for variant in catalog["variants"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Catalog contains duplicate variant IDs")
    print(f"Validated {len(ids)} complete variants against schema v{catalog['schemaVersion']}")


if __name__ == "__main__":
    main()
