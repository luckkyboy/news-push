#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE_FILE="${REPO_ROOT}/.env.example"
DATA_DIR="${REPO_ROOT}/data"

DEFAULT_IMAGE_BASE_URL="https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images"
DEFAULT_TZ="Asia/Shanghai"

read_env_value() {
  local key="$1"
  local file="$2"
  if [[ ! -f "${file}" ]]; then
    return 0
  fi
  grep -E "^${key}=" "${file}" | tail -n 1 | cut -d= -f2-
}

resolve_env_value() {
  local key="$1"
  local default_value="$2"
  local current_value="${!key:-}"

  if [[ -n "${current_value}" ]]; then
    printf '%s\n' "${current_value}"
    return 0
  fi

  local existing_value
  existing_value="$(read_env_value "${key}" "${ENV_FILE}")"
  if [[ -n "${existing_value}" ]]; then
    printf '%s\n' "${existing_value}"
    return 0
  fi

  printf '%s\n' "${default_value}"
}

write_env_file() {
  cat > "${ENV_FILE}" <<EOF
WECOM_WEBHOOK_URL=$(resolve_env_value "WECOM_WEBHOOK_URL" "")
NEWS_IMAGE_BASE_URL=$(resolve_env_value "NEWS_IMAGE_BASE_URL" "${DEFAULT_IMAGE_BASE_URL}")
TZ=$(resolve_env_value "TZ" "${DEFAULT_TZ}")
EOF
}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found"
  exit 1
fi

mkdir -p "${DATA_DIR}"

if [[ ! -f "${ENV_EXAMPLE_FILE}" ]]; then
  cat > "${ENV_EXAMPLE_FILE}" <<EOF
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=replace-me
NEWS_IMAGE_BASE_URL=${DEFAULT_IMAGE_BASE_URL}
TZ=${DEFAULT_TZ}
EOF
fi

if [[ -f "${ENV_FILE}" ]]; then
  write_env_file
  echo "updated .env file: ${ENV_FILE}"
else
  write_env_file
  echo "generated .env file: ${ENV_FILE}"
fi

if ! grep -Eq '^WECOM_WEBHOOK_URL=.+' "${ENV_FILE}"; then
  echo "WECOM_WEBHOOK_URL is missing in ${ENV_FILE}"
  echo "fill the webhook value, then rerun:"
  echo "  bash scripts/deploy_docker.sh"
  exit 1
fi

cd "${REPO_ROOT}"
docker compose up -d --build

echo "deployment started"
echo "health check: curl http://127.0.0.1:8000/health"
echo "logs: docker compose logs -f"
