"""Compile evidence-backed Pi Provider Routes for DeepSWE variants."""

import hashlib
import json
from pathlib import Path

NON_BEHAVIORAL_ROUTE_FIELDS = {"contextWindow", "maxTokens", "fingerprint"}


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def route_fingerprint(route):
    fingerprint_input = {key: value for key, value in route.items() if key not in NON_BEHAVIORAL_ROUTE_FIELDS}
    return "sha256:" + hashlib.sha256(canonical_json(fingerprint_input).encode()).hexdigest()


def variant_id(row):
    return f"deepswe:config:{row['config']}"


def canonical_model_id(model_id):
    value = model_id.lower().lstrip("~").removesuffix(":batch")
    value = value.rsplit("/", 1)[-1].replace(".", "-").replace("_", "-")
    prefixes = (
        "global-openai-",
        "openai-",
        "global-anthropic-",
        "us-anthropic-",
        "eu-anthropic-",
        "au-anthropic-",
        "jp-anthropic-",
        "anthropic-",
    )
    for prefix in prefixes:
        if value.startswith(prefix):
            value = value.removeprefix(prefix)
            break
    return value


def matching_routes(row, pi_catalog):
    effort = row.get("reasoning_effort")
    if effort is None:
        return []
    model = canonical_model_id(row["model"])
    return [
        route
        for route in pi_catalog["routes"]
        if canonical_model_id(route["modelId"]) == model and effort in route["supportedThinkingLevels"]
    ]


def load_decisions(path):
    document = json.loads(Path(path).read_text())
    if document.get("schemaVersion") != 1 or not isinstance(document.get("variants"), dict):
        raise ValueError("Route Decisions must use schemaVersion 1 and contain variants")
    return document["variants"]


def route_index(pi_catalog):
    return {(route["provider"], route["modelId"]): route for route in pi_catalog["routes"]}


def compile_aliases(rows, pi_catalog, decisions):
    routes = route_index(pi_catalog)
    aliases = {}
    stale = []
    for row in rows:
        source_id = variant_id(row)
        accepted = []
        for decision in decisions.get(source_id, []):
            if decision.get("outcome") != "accepted":
                continue
            decided_route = decision["route"]
            key = (decided_route["provider"], decided_route["modelId"])
            route = routes.get(key)
            if not route or route_fingerprint(route) != decision.get("routeFingerprint"):
                stale.append({"variantId": source_id, "provider": key[0], "modelId": key[1]})
                continue
            level = decided_route.get("piThinkingLevel")
            if level not in route["supportedThinkingLevels"]:
                stale.append({"variantId": source_id, "provider": key[0], "modelId": key[1]})
                continue
            accepted.append({**decided_route, "equivalence": "verified"})
        aliases[source_id] = sorted(accepted, key=lambda item: (item["provider"], item["modelId"], item["piThinkingLevel"] or ""))
    return aliases, stale


def candidate_queue(rows, pi_catalog, decisions, stale):
    stale_by_variant = {}
    for item in stale:
        stale_by_variant.setdefault(item["variantId"], []).append(item)
    candidates = []
    for row in rows:
        source_id = variant_id(row)
        existing_routes = {
            (decision["route"]["provider"], decision["route"]["modelId"], decision["route"]["piThinkingLevel"])
            for decision in decisions.get(source_id, [])
            if decision.get("route")
        }
        stale_routes = stale_by_variant.get(source_id, [])
        stale_keys = {(item["provider"], item["modelId"], row["reasoning_effort"]) for item in stale_routes}
        discovered = []
        for route in matching_routes(row, pi_catalog):
            key = (route["provider"], route["modelId"], row["reasoning_effort"])
            if key not in existing_routes or key in stale_keys:
                discovered.append({
                    "provider": route["provider"],
                    "modelId": route["modelId"],
                    "piThinkingLevel": row["reasoning_effort"],
                    "routeFingerprint": route_fingerprint(route),
                })
        if not discovered and not stale_routes and existing_routes:
            continue
        reason = "route_changed" if stale_routes else "route_discovered" if discovered else "missing_route"
        candidates.append({
            "variantId": source_id,
            "displayName": row["model"],
            "sourceConfig": row["config"],
            "sourceProvider": row["provider"],
            "reasoningEffort": row.get("reasoning_effort"),
            "reason": reason,
            "routes": discovered,
            "staleRoutes": stale_routes,
        })
    return {"schemaVersion": 1, "candidates": candidates}
