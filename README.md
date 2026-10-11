# DeepSWE Catalog Digest

A public, metric-only publisher for the official DeepSWE leaderboard.

## Metrics

- **Smart:** attempt pass@1; higher is better.
- **Fast:** mean end-to-end trial duration in seconds per task; lower is better.
- **Cheap:** mean reported inference cost in USD per task; lower is better.

Each Model Variant identifies an evaluated configuration. Provenance records the model checkpoint, reasoning effort, source providers, harness, trial counts, confidence interval, release, and artifact checksums. Only Complete Variants are published; missing measurements are never inferred.

The stable document is [`catalog/model-selection-catalog.json`](catalog/model-selection-catalog.json). The metric-only contract uses numeric `schemaVersion: 2`; see [`CONTRACT.md`](CONTRACT.md).

## Development

Requirements: Python 3.13+ and [mise](https://mise.jdx.dev/). No API credentials are needed to build.

```fish
mise install
mise run install
mise run test
mise run lint
mise run build
```

The build writes the catalog, schema, acquired source manifest, and acquisition report under `dist/`. To replay a recorded release, use `--manifest catalog/source-manifest.json`. Optional `--source PATH --trials PATH` inputs verify local artifacts against that manifest's checksums.

## Automatic maintenance

The daily and manually dispatched workflow:

1. Discovers the latest release linked from the official DeepSWE page.
2. Checks the dataset's declared CC BY 4.0 license and the configured scoring, aggregation, and harness definitions.
3. Downloads the current leaderboard and trials, validates their structure and provider provenance, and records their actual SHA-256 checksums.
4. Builds the Complete Variants and validates the metric-only contract.
5. Checks the public-source boundary and scans generated artifacts for secrets.
6. Publishes the catalog and source manifest atomically through a CI-checked, automatically merged PR, preserving the repository's required status checks.

[`sources/deepswe.json`](sources/deepswe.json) defines the source interface and accepted metric semantics. Checksums record adopted bytes for reproducibility; they do not prevent automatic adoption of ordinary artifact updates or new releases.

New configurations publish automatically, including previously unknown model names. Removed or incomplete configurations are excluded and reported. A greater-than-20% decrease in source or complete-variant count compared with the last-known-good catalog fails closed as suspicious coverage loss.

The publisher owns the `catalog-publish` branch and reuses its single open PR across retries, updating it with a lease-protected push only after acquisition and validation succeed. It disables pending auto-merge before replacement and closes obsolete pending updates when the validated source already matches the published catalog.

Unchanged data preserves `generatedAt` and causes no publication commit. Acquisition reports record the actual observation time, additions, removals, and updates; workflow history records successful refreshes even when publication is unnecessary. Reports are retained for 90 days.

Transient HTTP errors are retried three times with bounded backoff. Failed acquisition, validation, or publication leaves the last-known-good catalog available. A separate notification workflow opens one issue for an ongoing maintenance incident and closes it on recovery; notification failures cannot block publication.

Source-interface, scoring, aggregation, harness, licensing, schema, and suspicious coverage changes require investigation. Automatic code repair is not part of this publisher.

## Distribution

Catalog data is redistributable under CC BY 4.0. Consumers must preserve the embedded attribution and license metadata. Repository code is MIT-licensed. See [`DATA_LICENSE.md`](DATA_LICENSE.md).
