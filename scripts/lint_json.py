#!/usr/bin/env python3
"""Parse every committed JSON input."""

import json
from pathlib import Path

for pattern in ("schema/**/*.json", "sources/**/*.json", "mappings/**/*.json", "pi-catalog/**/*.json", "package*.json"):
    for path in Path(".").glob(pattern):
        json.loads(path.read_text())
