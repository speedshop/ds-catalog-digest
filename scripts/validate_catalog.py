#!/usr/bin/env python3
"""Validate a picker catalog against the shared JSON Schema."""

import argparse
import json
import math
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.validators import validator_for


def reject_json_constant(value):
    raise ValueError(f"Invalid JSON number: {value}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("schema", type=Path)
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(), parse_constant=reject_json_constant)
    schema = json.loads(args.schema.read_text(), parse_constant=reject_json_constant)
    validator_class = validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema, format_checker=FormatChecker()).validate(catalog)

    for variant in catalog["variants"]:
        if not all(math.isfinite(variant["metrics"][name]) for name in ("smart", "fast", "cheap")):
            raise ValueError(f"Variant contains a non-finite metric: {variant['id']}")
        if any(alias["piThinkingLevel"] is None for alias in variant["aliases"]):
            raise ValueError(f"Variant alias has no Pi thinking level: {variant['id']}")
        aliases = [
            (alias["provider"], alias["modelId"], alias["piThinkingLevel"])
            for alias in variant["aliases"]
        ]
        if len(aliases) != len(set(aliases)):
            raise ValueError(f"Variant contains duplicate aliases: {variant['id']}")

    ids = [variant["id"] for variant in catalog["variants"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Catalog contains duplicate variant IDs")
    print(f"Validated {len(ids)} complete variants against schema v{catalog['schemaVersion']}")


if __name__ == "__main__":
    main()
