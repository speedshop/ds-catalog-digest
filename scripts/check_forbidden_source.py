#!/usr/bin/env python3
"""Fail if restricted-source identifiers enter this public repository."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", "node_modules", "dist", "__pycache__"}
FORBIDDEN = (
    "artificial" + " analysis",
    "artificial" + "analysis",
    "aa" + ":model:",
    "aa" + "-catalog-digest",
)

violations = []
for path in ROOT.rglob("*"):
    if not path.is_file() or SKIP_PARTS.intersection(path.relative_to(ROOT).parts):
        continue
    try:
        text = path.read_text().lower()
    except UnicodeDecodeError:
        continue
    for phrase in FORBIDDEN:
        if phrase in text:
            violations.append(f"{path.relative_to(ROOT)} contains a forbidden source identifier")

if violations:
    raise SystemExit("\n".join(violations))
