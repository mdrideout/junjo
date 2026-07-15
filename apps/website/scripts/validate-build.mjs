import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const websiteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = join(websiteRoot, "dist");

const obsoleteSourcePatterns = [
  /github\.com\/mdrideout\/junjo-ai-studio(?:[\s)"'/?#]|$)/,
  /github\.com\/mdrideout\/junjo-website(?:[\s)"'/?#]|$)/,
];

function requireCondition(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function filesBelow(root) {
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const path = join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...filesBelow(path));
    } else if (entry.isFile()) {
      files.push(path);
    }
  }
  return files;
}

function displayPath(path) {
  return relative(websiteRoot, path).split(sep).join("/");
}

function resolveInternalTarget(sourcePath, rawTarget) {
  const target = rawTarget.split("#", 1)[0].split("?", 1)[0];
  if (!target) return null;

  let decoded;
  try {
    decoded = decodeURIComponent(target);
  } catch {
    throw new Error(`${displayPath(sourcePath)} contains an invalid encoded URL: ${rawTarget}`);
  }

  const resolvedTarget = decoded.startsWith("/")
    ? join(outputRoot, decoded.slice(1))
    : resolve(dirname(sourcePath), decoded);
  const outputRelativeTarget = relative(outputRoot, resolvedTarget);
  requireCondition(
    outputRelativeTarget !== ".." &&
      !outputRelativeTarget.startsWith(`..${sep}`) &&
      !isAbsolute(outputRelativeTarget),
    `${displayPath(sourcePath)} references a path outside website build output: ${rawTarget}`,
  );
  return resolvedTarget;
}

function targetExists(target) {
  if (existsSync(target) && statSync(target).isFile()) return true;
  if (existsSync(target) && statSync(target).isDirectory()) {
    return existsSync(join(target, "index.html"));
  }
  if (!extname(target) && existsSync(`${target}.html`)) return true;
  return !extname(target) && existsSync(join(target, "index.html"));
}

function readJson(path) {
  requireCondition(existsSync(path), `${displayPath(path)} is missing from the website build`);
  return JSON.parse(readFileSync(path, "utf8"));
}

function routeHtmlPath(route) {
  requireCondition(route.startsWith("/"), `documentation route must be absolute: ${route}`);
  const target = join(outputRoot, route.slice(1));
  if (existsSync(target) && statSync(target).isFile()) return target;
  if (existsSync(`${target}.html`)) return `${target}.html`;
  return join(target, "index.html");
}

function htmlIds(path, cache) {
  if (!cache.has(path)) {
    requireCondition(existsSync(path), `documentation route output is missing: ${displayPath(path)}`);
    const ids = new Set();
    const html = readFileSync(path, "utf8");
    for (const match of html.matchAll(/\sid=(?:"([^"]+)"|'([^']+)')/g)) {
      ids.add(match[1] ?? match[2]);
    }
    cache.set(path, ids);
  }
  return cache.get(path);
}

requireCondition(existsSync(outputRoot), "website build output is missing; run npm run build first");

for (const sourcePath of filesBelow(websiteRoot).filter(
  (path) => !path.startsWith(`${outputRoot}${sep}`) && !path.includes(`${sep}node_modules${sep}`),
)) {
  const source = readFileSync(sourcePath, "utf8");
  for (const pattern of obsoleteSourcePatterns) {
    requireCondition(!pattern.test(source), `${displayPath(sourcePath)} references an obsolete source repository`);
  }
}

const htmlFiles = filesBelow(outputRoot).filter((path) => path.endsWith(".html"));
requireCondition(htmlFiles.length > 0, "website build contains no HTML pages");
requireCondition(existsSync(join(outputRoot, "pagefind/pagefind.js")), "Pagefind search index is missing");
requireCondition(existsSync(join(outputRoot, "sitemap-index.xml")), "sitemap index is missing");

const missing = [];
const referencePattern = /(?:href|src)=(?:"([^"]+)"|'([^']+)')/g;
for (const htmlPath of htmlFiles) {
  const html = readFileSync(htmlPath, "utf8");
  for (const match of html.matchAll(referencePattern)) {
    const reference = match[1] ?? match[2];
    if (
      reference.startsWith("#") ||
      reference.startsWith("//") ||
      /^(?:data|https?|mailto|tel):/i.test(reference)
    ) {
      continue;
    }
    const target = resolveInternalTarget(htmlPath, reference);
    if (target !== null && !targetExists(target)) {
      missing.push(`${displayPath(htmlPath)} -> ${reference}`);
    }
  }
}

requireCondition(missing.length === 0, `website build has broken internal references:\n${missing.join("\n")}`);

const manifestRoot = join(outputRoot, "docs-manifests/generated/python");
const apiManifest = readJson(join(manifestRoot, "api-manifest.json"));
const sphinxBaseline = readJson(join(manifestRoot, "sphinx-api-baseline.json"));
const contentMigration = readJson(join(manifestRoot, "content-migration.json"));
const legacyRoutes = readJson(join(manifestRoot, "legacy-routes.json"));
const legacyApiMap = readJson(join(manifestRoot, "legacy-api-map.json"));
const publicationManifest = readJson(join(manifestRoot, "publication-manifest.json"));

requireCondition(apiManifest.version === 1, "unsupported Python API manifest version");
requireCondition(apiManifest.sdk === "python", "API manifest is not for the Python SDK");
requireCondition(apiManifest.docstring_parser === "auto", "API manifest does not support automatic docstring styles");
requireCondition(["next", "stable"].includes(apiManifest.channel), "API manifest has an invalid documentation channel");
requireCondition(/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(apiManifest.sdk_version), "invalid SDK version");
requireCondition(/^[0-9a-f]{40}$/.test(apiManifest.source_revision), "API source revision is not a full commit SHA");
requireCondition(apiManifest.symbol_count === apiManifest.symbols.length, "API symbol count is inconsistent");
requireCondition(publicationManifest.version === 1, "unsupported publication manifest version");
requireCondition(
  publicationManifest.documentation_channel === apiManifest.channel,
  "publication and API documentation channels differ",
);
requireCondition(
  new Set(publicationManifest.routes).size === publicationManifest.routes.length,
  "publication manifest contains duplicate routes",
);
requireCondition(
  publicationManifest.python.version === apiManifest.sdk_version &&
    publicationManifest.python.source_revision === apiManifest.source_revision,
  "publication and API Python sources differ",
);
if (apiManifest.channel === "stable") {
  requireCondition(
    /^sdk-python-v\d+\.\d+\.\d+/.test(publicationManifest.python.release_tag),
    "stable publication has no Python release tag",
  );
  requireCondition(
    /^studio-v\d+\.\d+\.\d+/.test(publicationManifest.studio.release_tag),
    "stable publication has no Studio release tag",
  );
}
requireCondition(
  apiManifest.page_count === apiManifest.symbol_page_count + apiManifest.module_page_count + 1,
  "API page count is inconsistent",
);
requireCondition(
  apiManifest.symbol_page_count ===
    new Set(
      apiManifest.symbols
        .filter((symbol) => symbol.kind !== "py:module")
        .map((symbol) => symbol.target_route),
    ).size,
  "API symbol page count is inconsistent",
);
requireCondition(
  apiManifest.module_page_count ===
    new Set(
      apiManifest.symbols
        .filter((symbol) => symbol.kind === "py:module")
        .map((symbol) => symbol.target_route),
    ).size,
  "API module page count is inconsistent",
);
requireCondition(existsSync(routeHtmlPath("/docs/python/api/")), "API index route is missing");

const baselineObjects = new Set(
  sphinxBaseline.objects.map((object) => `${object.kind}\0${object.name}\0${object.legacy_uri}`),
);
const exportedObjects = new Set(
  apiManifest.symbols.map((symbol) => `${symbol.kind}\0${symbol.public_name}\0${symbol.legacy_uri}`),
);
requireCondition(baselineObjects.size === sphinxBaseline.objects.length, "Sphinx baseline contains duplicate objects");
requireCondition(exportedObjects.size === apiManifest.symbols.length, "API manifest contains duplicate objects");
requireCondition(
  baselineObjects.size === exportedObjects.size && [...baselineObjects].every((object) => exportedObjects.has(object)),
  "generated API manifest does not exactly cover the Sphinx API baseline",
);

const idCache = new Map();
for (const symbol of apiManifest.symbols) {
  const outputPath = routeHtmlPath(symbol.target_route);
  requireCondition(existsSync(outputPath), `API route is missing: ${symbol.target_route}`);
  requireCondition(
    htmlIds(outputPath, idCache).has(symbol.target_anchor),
    `API anchor is missing: ${symbol.target_route}#${symbol.target_anchor}`,
  );
}

for (const route of publicationManifest.routes) {
  requireCondition(existsSync(routeHtmlPath(route)), `published content route is missing: ${route}`);
}
if (apiManifest.channel === "next") {
  for (const page of contentMigration.pages) {
    requireCondition(existsSync(routeHtmlPath(page.target_route)), `migrated content route is missing: ${page.target_route}`);
  }
  for (const route of legacyRoutes.routes) {
    requireCondition(existsSync(routeHtmlPath(route.target_route)), `legacy route target is missing: ${route.target_route}`);
  }
}

const expectedLegacyApiMap = new Map();
for (const symbol of apiManifest.symbols) {
  const target = `${symbol.target_route}#${symbol.target_anchor}`;
  requireCondition(
    !expectedLegacyApiMap.has(symbol.legacy_anchor) || expectedLegacyApiMap.get(symbol.legacy_anchor) === target,
    `legacy API anchor has conflicting targets: ${symbol.legacy_anchor}`,
  );
  expectedLegacyApiMap.set(symbol.legacy_anchor, target);
}
requireCondition(
  Object.keys(legacyApiMap.symbols).length === expectedLegacyApiMap.size,
  "legacy API map does not cover every unique Sphinx anchor",
);
for (const [anchor, target] of expectedLegacyApiMap) {
  requireCondition(legacyApiMap.symbols[anchor] === target, `legacy API mapping is stale: ${anchor}`);
}

const unconvertedMarkup = /\{(?:py|doc|ref|class|func|meth|attr):[^}]+\}|:::\s*\{(?:note|warning|toctree)/;
for (const htmlPath of htmlFiles) {
  requireCondition(
    !unconvertedMarkup.test(readFileSync(htmlPath, "utf8")),
    `${displayPath(htmlPath)} contains unconverted Sphinx/MyST markup`,
  );
}

console.log(
  `Validated ${htmlFiles.length} website pages, ${publicationManifest.routes.length} published routes, ` +
    `and ${apiManifest.symbol_count} Python API objects.`,
);
