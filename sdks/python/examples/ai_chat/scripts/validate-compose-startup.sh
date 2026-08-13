#!/usr/bin/env bash

set -euo pipefail

readonly SCRIPT_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly EXAMPLE_DIRECTORY="$(cd "${SCRIPT_DIRECTORY}/.." && pwd)"
readonly COMPOSE_FILE="${EXAMPLE_DIRECTORY}/compose.yaml"
readonly TEMPORARY_DIRECTORY="$(mktemp -d)"
readonly ENVIRONMENT_FILE="${TEMPORARY_DIRECTORY}/ai-chat-smoke.env"
readonly PROJECT_NAME="junjo-ai-chat-smoke-${GITHUB_RUN_ID:-local}-${RANDOM}"
readonly FRONTEND_PORT="${AI_CHAT_SMOKE_FRONTEND_PORT:-36251}"
readonly BACKEND_PORT="${AI_CHAT_SMOKE_BACKEND_PORT:-36252}"

compose() {
  docker compose \
    --project-name "${PROJECT_NAME}" \
    --file "${COMPOSE_FILE}" \
    --env-file "${ENVIRONMENT_FILE}" \
    "$@"
}

write_environment() {
  local provider="$1"

  {
    printf 'AI_CHAT_FRONTEND_PORT=%s\n' "${FRONTEND_PORT}"
    printf 'AI_CHAT_BACKEND_PORT=%s\n' "${BACKEND_PORT}"
    printf 'AI_CHAT_MODEL_PROVIDER=%s\n' "${provider}"
    printf 'GEMINI_API_KEY=synthetic-not-a-provider-credential\n'
    printf 'XAI_API_KEY=synthetic-not-a-provider-credential\n'
    printf 'JUNJO_AI_STUDIO_OTLP_ENDPOINT=localhost:26155\n'
    printf 'JUNJO_AI_STUDIO_OTLP_INSECURE=true\n'
    printf 'JUNJO_AI_STUDIO_BACKEND_BASE_URL=http://localhost:26154\n'
    printf 'JUNJO_AI_STUDIO_CLI_TOKEN=jcli_not-for-the-application\n'
    printf 'JUNJO_AI_STUDIO_FRONTEND_BASE_URL=http://localhost:26151\n'
  } >"${ENVIRONMENT_FILE}"
}

clean_stack() {
  compose down --volumes --remove-orphans --timeout 5 >/dev/null 2>&1 || true
}

clean_artifacts() {
  compose down --volumes --remove-orphans --rmi local --timeout 5 >/dev/null 2>&1 || true
}

assert_frontend_dependencies_are_image_owned() {
  local frontend_container_id
  local mount_destinations

  frontend_container_id="$(compose ps --quiet frontend)"
  if [[ -z "${frontend_container_id}" ]]; then
    echo "Unable to identify the running frontend container." >&2
    return 1
  fi

  mount_destinations="$(docker inspect --format '{{ range .Mounts }}{{ println .Destination }}{{ end }}' "${frontend_container_id}")"
  if grep -Fxq '/app/node_modules' <<<"${mount_destinations}"; then
    echo "Frontend dependencies are shadowed by a mount at /app/node_modules." >&2
    return 1
  fi
}

report_failure() {
  local exit_code="$?"

  trap - EXIT
  if (( exit_code != 0 )); then
    compose ps || true
    compose logs --no-color || true
  fi
  clean_artifacts
  rm -rf "${TEMPORARY_DIRECTORY}"
  exit "${exit_code}"
}

trap report_failure EXIT

echo "AI Chat Compose infrastructure smoke"
echo "This proves configuration, container lifecycle, health, and HTTP wiring only."
echo "It uses synthetic non-secret keys and does not call or evaluate either provider."

write_environment gemini
compose config --quiet
compose build

for provider in gemini grok; do
  echo "Starting clean ${provider} composition..."
  clean_stack
  write_environment "${provider}"
  compose config --quiet
  compose up --detach --wait --wait-timeout 120 --no-build

  compose exec -T backend sh -c \
    "test \"\${AI_CHAT_MODEL_PROVIDER}\" = '${provider}'"
  compose exec -T backend sh -c \
    'test "${JUNJO_AI_STUDIO_OTLP_ENDPOINT}" = "host.docker.internal:26155"'
  compose exec -T backend sh -c \
    'test "${JUNJO_AI_STUDIO_OTLP_INSECURE}" = "true"'
  compose exec -T backend sh -c \
    'test -z "${JUNJO_AI_STUDIO_BACKEND_BASE_URL+x}"'
  compose exec -T backend sh -c \
    'test -z "${JUNJO_AI_STUDIO_CLI_TOKEN+x}"'
  curl --fail --silent --show-error \
    "http://localhost:${BACKEND_PORT}/api/healthz" >/dev/null
  curl --fail --silent --show-error \
    "http://localhost:${BACKEND_PORT}/api/config" >/dev/null
  curl --fail --silent --show-error \
    "http://localhost:${FRONTEND_PORT}/" >/dev/null

  if [[ "${provider}" == "gemini" ]]; then
    compose exec -T backend sh -c \
      "printf preserved > /data/compose-rebuild-preservation-marker"
    compose up --detach --wait --wait-timeout 120 --build
    assert_frontend_dependencies_are_image_owned
    compose exec -T frontend npm ls --all >/dev/null
    compose exec -T backend sh -c \
      "test \"\$(cat /data/compose-rebuild-preservation-marker)\" = preserved"
    echo "Frontend dependencies are image-owned and internally consistent; chat storage survived rebuild."
  fi

  echo "${provider} composition is healthy; no provider request was made."
  clean_stack
done

clean_artifacts
rm -rf "${TEMPORARY_DIRECTORY}"
trap - EXIT

echo "AI Chat Compose infrastructure smoke passed."
