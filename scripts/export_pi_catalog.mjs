#!/usr/bin/env node

import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ModelRuntime,
  SessionManager,
  createAgentSession,
} from "@earendil-works/pi-coding-agent";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"];
const STANDARD_LEVELS = new Set(LEVELS.slice(0, 5));
const REMOTE_CATALOG_TIMEOUT_MS = 30_000;
const PROVIDERS_WITHOUT_REMOTE_CATALOGS = new Set(["radius"]);
const NON_BEHAVIORAL_ROUTE_FIELDS = new Set(["contextWindow", "fingerprint", "maxTokens"]);
const COMPAT_FIELDS = [
  "chatTemplateArgs",
  "chatTemplateKwargs",
  "forceAdaptiveThinking",
  "maxTokensField",
  "openRouterRouting",
  "supportsDeveloperRole",
  "supportsReasoningEffort",
  "thinkingFormat",
  "vercelGatewayRouting",
];

function parseArgs(argv) {
  const args = {
    config: join(ROOT, "mappings/pi-catalog-config.json"),
    output: join(ROOT, "dist/pi-model-catalog.json"),
    offline: false,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--offline") args.offline = true;
    else if (arg === "--config" || arg === "--output") args[arg.slice(2)] = argv[++index];
    else throw new Error(`Unknown argument: ${arg}`);
  }
  return args;
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(value) {
  return `sha256:${createHash("sha256").update(canonicalJson(value)).digest("hex")}`;
}

function cleanObject(value) {
  if (Array.isArray(value)) return value.map(cleanObject);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, item]) => item !== undefined)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, cleanObject(item)]),
  );
}

function supportedThinkingLevels(model) {
  if (!model.reasoning) return ["off"];
  const levelMap = model.thinkingLevelMap ?? {};
  return LEVELS.filter((level) => {
    if (Object.hasOwn(levelMap, level)) return levelMap[level] !== null;
    return STANDARD_LEVELS.has(level);
  });
}

function deploymentFingerprint(baseUrl) {
  if (!baseUrl) return null;
  try {
    const url = new URL(baseUrl);
    url.username = "";
    url.password = "";
    url.search = "";
    url.hash = "";
    return sha256(url.toString());
  } catch {
    return null;
  }
}

function normalizeRoute(model) {
  const compatibility = Object.fromEntries(
    COMPAT_FIELDS.filter((field) => model.compat?.[field] !== undefined).map((field) => [field, model.compat[field]]),
  );
  const route = cleanObject({
    provider: model.provider,
    modelId: model.id,
    name: model.name,
    api: model.api,
    reasoning: model.reasoning === true,
    thinkingLevelMap: model.thinkingLevelMap ?? {},
    supportedThinkingLevels: supportedThinkingLevels(model),
    input: [...model.input].sort(),
    contextWindow: model.contextWindow,
    maxTokens: model.maxTokens,
    samplingParams: model.samplingParams,
    compatibility,
    deploymentFingerprint: deploymentFingerprint(model.baseUrl),
  });
  const fingerprintInput = Object.fromEntries(
    Object.entries(route).filter(([field]) => !NON_BEHAVIORAL_ROUTE_FIELDS.has(field)),
  );
  return { ...route, fingerprint: sha256(fingerprintInput) };
}

async function packageVersion() {
  const entry = fileURLToPath(import.meta.resolve("@earendil-works/pi-coding-agent"));
  const metadata = JSON.parse(await readFile(join(dirname(entry), "../package.json"), "utf8"));
  return metadata.version;
}

function normalizeCatalogBaseUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Invalid remote catalog base URL");
  }
  if (!["http:", "https:"].includes(url.protocol)) throw new Error(`Unsupported remote catalog protocol: ${url.protocol}`);
  url.username = "";
  url.password = "";
  url.pathname = "/";
  url.search = "";
  url.hash = "";
  return url.toString();
}

function remoteCatalogModels(providerId, value) {
  let entries;
  if (Array.isArray(value)) entries = value;
  else if (value && typeof value === "object" && Array.isArray(value.models)) entries = value.models;
  else if (value && typeof value === "object") entries = Object.values(value);
  else throw new Error(`Invalid remote catalog for provider ${providerId}`);

  const ids = new Set();
  return entries.map((model, index) => {
    if (!model || typeof model !== "object" || typeof model.id !== "string" || !model.id.trim()) {
      throw new Error(`Invalid model at index ${index} in remote catalog for ${providerId}`);
    }
    if (ids.has(model.id)) throw new Error(`Duplicate model ${model.id} in remote catalog for ${providerId}`);
    ids.add(model.id);
    return { ...model, provider: providerId };
  });
}

async function seedRemoteCatalogs(runtime, storePath, baseUrl, version) {
  const signal = AbortSignal.timeout(REMOTE_CATALOG_TIMEOUT_MS);
  const providers = runtime
    .getProviders()
    .map((provider) => provider.id)
    .filter((providerId) => !PROVIDERS_WITHOUT_REMOTE_CATALOGS.has(providerId))
    .sort();
  const checkedAt = Date.now();
  const catalogs = await Promise.all(
    providers.map(async (providerId) => {
      const url = new URL(`/api/models/providers/${encodeURIComponent(providerId)}`, baseUrl);
      const response = await fetch(url, {
        headers: {
          accept: "application/json",
          "User-Agent": `ds-catalog-digest/pi-catalog-export (Pi ${version})`,
        },
        signal,
      });
      if (response.status === 404 || response.status === 501) return null;
      if (!response.ok) throw new Error(`Remote catalog request failed for ${providerId}: ${response.status}`);

      const lastModified = Date.parse(response.headers.get("last-modified") ?? "");
      if (Number.isNaN(lastModified)) {
        throw new Error(`Remote catalog for ${providerId} has no valid Last-Modified header`);
      }
      return [
        providerId,
        {
          models: remoteCatalogModels(providerId, await response.json()),
          checkedAt,
          lastModified,
          etag: response.headers.get("etag") ?? undefined,
        },
      ];
    }),
  );
  await writeFile(storePath, `${JSON.stringify(Object.fromEntries(catalogs.filter(Boolean)), null, 2)}\n`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const configPath = resolve(args.config);
  const config = JSON.parse(await readFile(configPath, "utf8"));
  if (config.schemaVersion !== 1) throw new Error("Pi catalog config must use schemaVersion 1");

  const version = await packageVersion();
  if (version !== config.piVersion) {
    throw new Error(`Installed Pi version ${version} does not match configured version ${config.piVersion}`);
  }
  const refreshRemoteCatalogs = !args.offline;
  if (refreshRemoteCatalogs && !config.remoteCatalogBaseUrl) {
    throw new Error("Pi catalog config must define remoteCatalogBaseUrl");
  }
  const remoteCatalogBaseUrl = refreshRemoteCatalogs
    ? normalizeCatalogBaseUrl(config.remoteCatalogBaseUrl)
    : undefined;

  const agentDir = resolve(ROOT, config.agentDir);
  const cwd = resolve(ROOT, config.cwd);
  const temporary = await mkdtemp(join(tmpdir(), "ds-pi-catalog-"));
  let session;
  try {
    const modelsStorePath = join(temporary, "models-store.json");
    const runtime = await ModelRuntime.create({
      authPath: join(temporary, "no-auth.json"),
      modelsPath: join(agentDir, "models.json"),
      modelsStorePath,
      allowModelNetwork: false,
      refreshOnCreate: false,
    });
    if (runtime.getError()) throw new Error(runtime.getError());

    const result = await createAgentSession({
      cwd,
      agentDir,
      modelRuntime: runtime,
      model: runtime.getModels()[0],
      noTools: "all",
      sessionManager: SessionManager.inMemory(cwd),
    });
    session = result.session;
    if (result.extensionsResult.errors.length) {
      throw new Error(`Pi extensions failed to load: ${JSON.stringify(result.extensionsResult.errors)}`);
    }
    if (refreshRemoteCatalogs) {
      await seedRemoteCatalogs(runtime, modelsStorePath, remoteCatalogBaseUrl, version);
      const refresh = await runtime.refresh({ allowNetwork: false });
      if (refresh.aborted || refresh.errors.size) {
        const errors = [...refresh.errors].map(([provider, error]) => `${provider}: ${error.message}`).join("; ");
        throw new Error(`Could not load remote Pi catalogs${errors ? `: ${errors}` : ""}`);
      }
    }

    const routes = runtime
      .getModels()
      .map(normalizeRoute)
      .sort((left, right) => left.provider.localeCompare(right.provider) || left.modelId.localeCompare(right.modelId));
    const keys = routes.map((route) => `${route.provider}\0${route.modelId}`);
    if (new Set(keys).size !== keys.length) throw new Error("Pi catalog contains duplicate provider/model IDs");

    const snapshot = {
      schemaVersion: 1,
      source: {
        package: config.piPackage,
        version,
        remoteCatalogsRefreshed: refreshRemoteCatalogs,
        remoteCatalogBaseUrl,
        modelsConfigHash: sha256(JSON.parse(await readFile(join(agentDir, "models.json"), "utf8"))),
        extensions: result.extensionsResult.extensions
          .map((extension) => relative(ROOT, extension.resolvedPath))
          .sort(),
      },
      catalogHash: sha256(routes),
      routes,
    };
    const output = resolve(args.output);
    await mkdir(dirname(output), { recursive: true });
    await writeFile(output, `${JSON.stringify(snapshot, null, 2)}\n`);
    console.log(`Exported ${routes.length} Pi Provider Routes from Pi ${version}`);
  } finally {
    session?.dispose();
    await rm(temporary, { recursive: true, force: true });
  }
}

await main();
