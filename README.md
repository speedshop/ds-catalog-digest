# DeepSWE Catalog Digest

A public, machine-readable model-selection catalog derived from the official DeepSWE leaderboard. It publishes comparable Smart, Fast, and Cheap measurements plus verified Pi Provider Routes.

## Features

- **Smart:** DeepSWE pass@1
- **Fast:** mean end-to-end trial duration per task
- **Cheap:** mean reported inference cost per task
- Exact model and reasoning-effort variants
- Source provider, mini-swe-agent harness, trial counts, and confidence intervals in provenance
- Explicit, fingerprinted Pi Provider Route aliases

The stable catalog is [`catalog/model-selection-catalog.json`](catalog/model-selection-catalog.json). Its format is documented in [`CONTRACT.md`](CONTRACT.md).

## Installation

Requirements:

- Python 3.13+
- Node.js 22+
- [mise](https://mise.jdx.dev/)

```fish
git clone https://github.com/speedshop/ds-catalog-digest.git
cd ds-catalog-digest
mise install
mise run install
```

No API credentials are required. The build downloads checksum-pinned public DeepSWE artifacts and public Pi provider catalogs.

## Usage

Build the catalog and route-maintenance artifacts:

```console
$ mise run build
```

Validate the result:

```fish
python scripts/validate_catalog.py \
  dist/model-selection-catalog.json \
  dist/schema.json
```

The build writes:

- `dist/model-selection-catalog.json`
- `dist/model-aliases.json`
- `dist/pi-model-catalog.json`
- `dist/pi-catalog-diff.json`
- `dist/route-candidates.json`
- `dist/ALIAS_AUDIT.md`

## Reproducibility

[`sources/deepswe-v1.1.json`](sources/deepswe-v1.1.json) pins the release, artifact URLs, and SHA-256 checksums. A checksum mismatch fails the build rather than silently importing changed data.

The daily publication workflow refreshes Pi Provider Routes, validates the catalog, updates stable artifacts, and opens managed issues for unresolved or stale route mappings.

## Development

```fish
mise run test
mise run lint
mise run build
```

Route Decisions live in [`mappings/route-decisions.json`](mappings/route-decisions.json). Only accepted decisions whose fingerprints still match the current Pi catalog are published.

## Contributing

Changes should preserve exact checkpoint and reasoning-effort identity, reproducible source acquisition, and attribution. Never infer scores or substitute one reasoning effort for another.

## License

Repository code is MIT-licensed. Generated DeepSWE-derived data is CC BY 4.0. See [`DATA_LICENSE.md`](DATA_LICENSE.md) for attribution and redistribution terms.
