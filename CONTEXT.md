# Domain language

## Canonical Catalog

The picker-ready document containing Complete Variants and catalog-wide definitions for Smart, Fast, and Cheap.

## Model Variant

One DeepSWE configuration identified by model checkpoint and reasoning effort. DeepSWE v1.1 uses the mini-swe-agent harness for every Model Variant.

## Provider Route

A Pi provider, model ID, and thinking level that can invoke a Model Variant.

## Route Decision

An evidence-backed acceptance or rejection of a Provider Route for a Model Variant.

## Route Candidate

A possible Provider Route awaiting a Route Decision. A candidate is not evidence of equivalence.

## Smart

DeepSWE pass@1. Higher is better.

## Fast

Mean end-to-end DeepSWE trial duration in seconds per task. Lower is better.

## Cheap

Mean reported inference cost in USD per DeepSWE task. Lower is better. It is a benchmark reference, not a promise about billing on every equivalent Provider Route.

## Complete Variant

A Model Variant with finite Smart and Fast values and a finite, positive Cheap value. Only Complete Variants enter the Canonical Catalog.

## Source Artifact

An official DeepSWE release artifact identified by URL and SHA-256 checksum.
