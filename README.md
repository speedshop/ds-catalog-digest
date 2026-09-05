# DeepSWE Catalog Digest

This repository publishes a public model-selection catalog. The catalog uses data from the official DeepSWE leaderboard.

Use the catalog to compare model configurations and select a Pi Provider Route.

## Features

The catalog contains three metrics:

- **Smart** is the DeepSWE pass@1 score. A higher value is better.
- **Fast** is the mean task time in seconds. A lower value is better.
- **Cheap** is the mean reported task cost in US dollars. A lower value is better.

Each Model Variant identifies one model checkpoint and one reasoning effort. Smart, Fast, and Cheap record source metric origins for the DeepSWE release; these measurements are not adjusted. Variant provenance records the source provider, the mini-swe-agent harness, trial counts, and the confidence interval.

The catalog also contains verified Pi Provider Routes. A route identifies a provider, model ID, and thinking level.

Read the stable catalog at [`catalog/model-selection-catalog.json`](catalog/model-selection-catalog.json). The vendored [`schema/model-selection-catalog.schema.json`](schema/model-selection-catalog.schema.json) exactly matches the canonical catalog-v1 schema owned by `speedshop/pi-pareto-model`; [`CONTRACT.md`](CONTRACT.md) documents this producer's mapping.

## Installation

Install these tools:

- Python 3.13 or later
- Node.js 22 or later
- [mise](https://mise.jdx.dev/)

Then run these commands:

```fish
git clone https://github.com/speedshop/ds-catalog-digest.git
cd ds-catalog-digest
mise install
mise run install
```

The build does not require API credentials.

## Usage

Build the catalog:

```console
$ mise run build
```

Validate the catalog:

```fish
python scripts/validate_catalog.py \
  dist/model-selection-catalog.json \
  dist/schema.json
```

The build writes these files:

- `dist/model-selection-catalog.json`
- `dist/model-aliases.json`
- `dist/pi-model-catalog.json`
- `dist/pi-catalog-diff.json`
- `dist/route-candidates.json`
- `dist/ALIAS_AUDIT.md`

## Source control

[`sources/deepswe-v1.1.json`](sources/deepswe-v1.1.json) identifies the source release. It also records each artifact URL and SHA-256 checksum.

The build verifies each checksum. The build stops if an artifact changed.

The daily workflow performs these tasks:

1. Refresh the public Pi Provider Route catalog.
2. Build and validate the model-selection catalog.
3. Check the generated files for restricted source data and secrets.
4. Publish the stable files.
5. Open an issue for each unresolved or changed route.

## Development

Run all checks before you submit a change:

```fish
mise run test
mise run lint
mise run build
```

Record Route Decisions in [`mappings/route-decisions.json`](mappings/route-decisions.json). The publisher accepts a route only while its fingerprint matches the current Pi catalog.

Preserve the exact checkpoint and reasoning effort. Do not infer a missing score. Do not replace one reasoning effort with another effort.

## Contributing

Submit a focused pull request. Include tests for behavior changes. Preserve source checksums, provenance, and attribution.

## License

The repository code uses the MIT License. The generated DeepSWE data uses the CC BY 4.0 license.

Read [`DATA_LICENSE.md`](DATA_LICENSE.md) for the required attribution and distribution terms.
