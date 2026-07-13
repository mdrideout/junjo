#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO="${UPSTREAM_REPO:-mdrideout/junjo-ai-studio}"
MINIMAL_REPO="${MINIMAL_REPO:-mdrideout/junjo-ai-studio-minimal-build}"
LOCAL_REPO_ROOT="${LOCAL_REPO_ROOT:-$(pwd)}"

TARGET_TAG="${1:-}"
BASE_TAG="${2:-}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Error: required command not found: $1" >&2
    exit 1
  }
}

need_cmd git
need_cmd curl
need_cmd jq
need_cmd rg
need_cmd sed

if [[ -z "$TARGET_TAG" ]]; then
  TARGET_TAG="$(curl -fsSL "https://api.github.com/repos/${UPSTREAM_REPO}/releases/latest" | jq -r '.tag_name')"
fi

if [[ -z "$TARGET_TAG" || "$TARGET_TAG" == "null" ]]; then
  echo "Error: unable to determine target tag." >&2
  exit 1
fi

if [[ -z "$BASE_TAG" ]]; then
  BASE_TAG="$(curl -fsSL "https://api.github.com/repos/${UPSTREAM_REPO}/tags?per_page=20" \
    | jq -r --arg t "$TARGET_TAG" '
      map(.name) as $tags
      | ($tags | index($t)) as $idx
      | if $idx == null or ($idx + 1) >= ($tags | length) then "" else $tags[$idx + 1] end
    ')"
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
TMP_DIR="$(mktemp -d "/tmp/junjo-release-audit-${STAMP}-XXXXXX")"
UPSTREAM_DIR="${TMP_DIR}/upstream"
MINIMAL_DIR="${TMP_DIR}/minimal"

cleanup() {
  echo
  echo "Temporary data kept at: ${TMP_DIR}"
}
trap cleanup EXIT

echo "== Junjo Release Audit =="
echo "Upstream repo: ${UPSTREAM_REPO}"
echo "Minimal repo:  ${MINIMAL_REPO}"
echo "Target tag:    ${TARGET_TAG}"
echo "Base tag:      ${BASE_TAG:-<not resolved>}"
echo

echo "== Release metadata =="
curl -fsSL "https://api.github.com/repos/${UPSTREAM_REPO}/releases/tags/${TARGET_TAG}" \
  | jq -r '"Name: \(.name)\nTag: \(.tag_name)\nPublished: \(.published_at)\nURL: \(.html_url)"'
echo

echo "== Clone references =="
git clone --depth 1 --branch "${TARGET_TAG}" "https://github.com/${UPSTREAM_REPO}.git" "${UPSTREAM_DIR}" >/dev/null
git clone --depth 1 "https://github.com/${MINIMAL_REPO}.git" "${MINIMAL_DIR}" >/dev/null
echo "Cloned upstream at ${UPSTREAM_DIR}"
echo "Cloned minimal-build at ${MINIMAL_DIR}"
echo

if [[ -n "${BASE_TAG}" ]]; then
  echo "== Upstream changed files (${BASE_TAG}...${TARGET_TAG}) =="
  curl -fsSL "https://api.github.com/repos/${UPSTREAM_REPO}/compare/${BASE_TAG}...${TARGET_TAG}" \
    | jq -r '.files[]? | "\(.status)\t\(.filename)"'
  echo
fi

show_matches() {
  local header="$1"
  local file="$2"
  local pattern="$3"
  echo "-- ${header}: ${file}"
  if [[ -f "${file}" ]]; then
    rg -n "${pattern}" "${file}" || true
  else
    echo "missing"
  fi
  echo
}

echo "== Minimal-build reference signals =="
show_matches \
  "compose" \
  "${MINIMAL_DIR}/docker-compose.yml" \
  "image: mdrideout/junjo-ai-studio-(backend|ingestion|frontend)|mem_reservation|mem_limit|memswap_limit|pids_limit|MALLOC_ARENA_MAX|MALLOC_TRIM_THRESHOLD_|JUNJO_DF_"
show_matches \
  "env" \
  "${MINIMAL_DIR}/.env.example" \
  "JUNJO_BUILD_TARGET|JUNJO_BACKEND_MEM_|JUNJO_MALLOC_|JUNJO_DF_|CLOUDFLARE_API_TOKEN|JUNJO_PROD_"
show_matches \
  "setup script" \
  "${MINIMAL_DIR}/scripts/junjo" \
  "JUNJO_BUILD_TARGET|CLOUDFLARE|--hostname|--cloudflare-token|JUNJO_PROD_FRONTEND_URL|COMMENTED_ENV_KEY_RE"
show_matches \
  "readme" \
  "${MINIMAL_DIR}/README.md" \
  "scripts/junjo setup|CLOUDFLARE|JUNJO_BUILD_TARGET|0\\.[0-9]+\\.[0-9]+"

echo "== Local repo signals =="
show_matches \
  "compose" \
  "${LOCAL_REPO_ROOT}/docker-compose.yml" \
  "image: mdrideout/junjo-ai-studio-(backend|ingestion|frontend)|mem_reservation|mem_limit|memswap_limit|pids_limit|MALLOC_ARENA_MAX|MALLOC_TRIM_THRESHOLD_|JUNJO_DF_|caddy|junjo-app"
show_matches \
  "env" \
  "${LOCAL_REPO_ROOT}/.env.example" \
  "JUNJO_BUILD_TARGET|JUNJO_BACKEND_MEM_|JUNJO_MALLOC_|JUNJO_DF_|CLOUDFLARE_API_TOKEN|JUNJO_PROD_"
show_matches \
  "setup script" \
  "${LOCAL_REPO_ROOT}/scripts/junjo" \
  "JUNJO_BUILD_TARGET|CLOUDFLARE|--hostname|--cloudflare-token|JUNJO_PROD_FRONTEND_URL|COMMENTED_ENV_KEY_RE"
show_matches \
  "readme" \
  "${LOCAL_REPO_ROOT}/README.md" \
  "scripts/junjo setup|CLOUDFLARE|JUNJO_BUILD_TARGET|0\\.[0-9]+\\.[0-9]+|caddy/Caddyfile|junjo-app"

echo "== Suggested next step =="
echo "Diff local files against minimal/upstream references and apply only the changes compatible with deployment-example constraints."
