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
console.log(`Validated ${htmlFiles.length} website pages and their internal references.`);
