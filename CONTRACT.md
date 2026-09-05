# Model Selection Catalog v1

[`schema/model-selection-catalog.schema.json`](schema/model-selection-catalog.schema.json) is an unchanged vendored copy of the source-neutral canonical catalog-v1 schema owned by [`speedshop/pi-pareto-model`](https://github.com/speedshop/pi-pareto-model). Catalogs use the numeric `schemaVersion` value `1`.

## Invariants

- One document represents one benchmark catalog and methodology version.
- Every variant has finite Smart and Fast numbers and a finite, positive Cheap number.
- Smart is higher-is-better; Fast and Cheap are lower-is-better.
- Every metric records its benchmark origin; DeepSWE measurements use `kind: "source"`.
- Metric units and task definitions are catalog-wide.
- Variant IDs remain stable when measurements are republished.
- Provider aliases are explicit, verified assertions; consumers do not fuzzy-match names.
- Distribution and attribution metadata travel with the catalog.

## DeepSWE mapping

| Contract field | DeepSWE field | Unit |
|---|---|---|
| Smart | `pass_at_1` | Pass rate |
| Fast | `mean_duration_seconds` | Seconds per DeepSWE task |
| Cheap | `mean_cost_usd` | USD per DeepSWE task |

All metrics come directly from the same released DeepSWE configuration. Each metric origin names that DeepSWE release as its `benchmarkVersion`; none of these values is adjusted. The recorded provider, mini-swe-agent harness, trial counts, confidence interval, source release, and source checksums are retained in provenance.

A Provider Route alias identifies a Pi invocation:

```json
{
  "provider": "openai",
  "modelId": "gpt-5.6-sol",
  "piThinkingLevel": "high",
  "equivalence": "verified"
}
```

The metrics characterize the Model Variant and may be used across verified equivalent Provider Routes. Cheap is a benchmark reference rather than a route-specific billing quote.

## Distribution

The repository's code is MIT-licensed. DeepSWE-derived catalog data is distributed under CC BY 4.0 with attribution to Datacurve. Consumers must preserve the attribution and license metadata embedded in the catalog.

## Delivery

The stable picker-ready document is published at:

```text
catalog/model-selection-catalog.json
```
