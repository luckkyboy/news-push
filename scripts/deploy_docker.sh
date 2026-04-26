#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${REPO_ROOT}/.env"
ENV_EXAMPLE_FILE="${REPO_ROOT}/.env.example"
DATA_DIR="${REPO_ROOT}/data"
STATE_DB_FILE="${DATA_DIR}/state.db"

DEFAULT_IMAGE_BASE_URL="https://raw.githubusercontent.com/luckkyboy/news-data/main/static/images"
DEFAULT_TZ="Asia/Shanghai"
DEFAULT_OIL_CALENDAR_DATA_DIR="/data/oil-calendar"

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
  local webhook_url="$1"
  local image_base_url="$2"
  local oil_calendar_data_dir="$3"
  local timezone="$4"
  cat > "${ENV_FILE}" <<EOF
WECOM_WEBHOOK_URL=${webhook_url}
NEWS_IMAGE_BASE_URL=${image_base_url}
OIL_CALENDAR_DATA_DIR=${oil_calendar_data_dir}
TZ=${timezone}
EOF
}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found"
  exit 1
fi

mkdir -p "${DATA_DIR}"
touch "${STATE_DB_FILE}"
chmod 0777 "${DATA_DIR}"
chmod 0666 "${STATE_DB_FILE}"

if [[ ! -f "${ENV_EXAMPLE_FILE}" ]]; then
  cat > "${ENV_EXAMPLE_FILE}" <<EOF
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=replace-me
NEWS_IMAGE_BASE_URL=${DEFAULT_IMAGE_BASE_URL}
OIL_CALENDAR_DATA_DIR=${DEFAULT_OIL_CALENDAR_DATA_DIR}
TZ=${DEFAULT_TZ}
EOF
fi

resolved_webhook_url=""
resolved_image_base_url=""
resolved_oil_calendar_data_dir=""
resolved_timezone=""
if [[ -f "${ENV_FILE}" ]]; then
  resolved_webhook_url="$(resolve_env_value "WECOM_WEBHOOK_URL" "")"
  resolved_image_base_url="$(resolve_env_value "NEWS_IMAGE_BASE_URL" "${DEFAULT_IMAGE_BASE_URL}")"
  resolved_oil_calendar_data_dir="$(resolve_env_value "OIL_CALENDAR_DATA_DIR" "${DEFAULT_OIL_CALENDAR_DATA_DIR}")"
  resolved_timezone="$(resolve_env_value "TZ" "${DEFAULT_TZ}")"
  write_env_file "${resolved_webhook_url}" "${resolved_image_base_url}" "${resolved_oil_calendar_data_dir}" "${resolved_timezone}"
  echo "updated .env file: ${ENV_FILE}"
else
  if [[ -z "${WECOM_WEBHOOK_URL:-}" ]]; then
    echo "WECOM_WEBHOOK_URL is required when .env does not exist"
    echo "set the webhook value, then rerun:"
    echo "  WECOM_WEBHOOK_URL='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=your-key' bash scripts/deploy_docker.sh"
    exit 1
  fi
  resolved_webhook_url="$(resolve_env_value "WECOM_WEBHOOK_URL" "")"
  resolved_image_base_url="$(resolve_env_value "NEWS_IMAGE_BASE_URL" "${DEFAULT_IMAGE_BASE_URL}")"
  resolved_oil_calendar_data_dir="$(resolve_env_value "OIL_CALENDAR_DATA_DIR" "${DEFAULT_OIL_CALENDAR_DATA_DIR}")"
  resolved_timezone="$(resolve_env_value "TZ" "${DEFAULT_TZ}")"
  write_env_file "${resolved_webhook_url}" "${resolved_image_base_url}" "${resolved_oil_calendar_data_dir}" "${resolved_timezone}"
  echo "generated .env file: ${ENV_FILE}"
fi

cd "${REPO_ROOT}"
docker compose up -d --build
docker image prune -f

echo "deployment started"
echo "health check: curl http://127.0.0.1:8000/health"
echo "logs: docker compose logs -f"
