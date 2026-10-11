#!/usr/bin/env python3
"""Parse every committed JSON input."""

import json
from pathlib import Path

for pattern in ("schema/**/*.json", "sources/**/*.json", "catalog/**/*.json", "tests/fixtures/**/*.json"):
    for path in Path(".").glob(pattern):
        json.loads(path.read_text())
