# Model Metrics Catalog v2

The normative contract is [`schema/model-metrics-catalog.schema.json`](schema/model-metrics-catalog.schema.json), vendored byte-for-byte from the consumer repository.

## Invariants

- `schemaVersion` is numeric `2`; other versions fail closed.
- One document targets one benchmark catalog and methodology version.
- Every Model Variant has a stable source-namespaced ID, display name, creator, and finite Smart, Fast, and Cheap values.
- Smart is higher-is-better; Fast and Cheap are lower-is-better.
- Fast is positive. The shared contract permits zero Cheap; this producer requires positive Cheap.
- Metric units and task definitions are catalog-wide.
- Every metric identifies its source benchmark version. This publisher does not estimate missing metrics.
- Distribution and attribution metadata travel with the catalog.
- The contract contains benchmark measurements, not invocation configuration.

## Source mapping

| Metric | DeepSWE field | Unit |
|---|---|---|
| Smart | `pass_at_1` | Attempt pass rate |
| Fast | `mean_duration_seconds` | Seconds per DeepSWE task |
| Cheap | `mean_cost_usd` | USD per DeepSWE task |

All metrics belong to the same evaluated configuration, identified by `deepswe:config:<config>`. The checkpoint, reasoning effort, source providers, harness, trial counts, confidence interval, release, and artifact checksums remain in the catalog.

Unknown creator names are reported as `Unknown`; unknown model IDs remain verbatim rather than blocking new measurements or guessing identity.

## Delivery and distribution

`catalog/model-selection-catalog.json` is the stable public document. `catalog/source-manifest.json` records its adopted source URLs and checksums. They publish atomically.

The distribution classification is `redistributable` and `allowRedistribution` is true. Data is CC BY 4.0 with attribution to Datacurve. Consumers must preserve the embedded attribution and license metadata.
