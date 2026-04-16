#!/bin/bash
set -euo pipefail

BASE_DIR="/home/odoo/odoo16/odoo16E"
DB_CONTAINER="odoo16e-db"
WEB_NAME="odoo16e-web"
IMAGE_NAME="odoo16e-runner"
DB_NAME="${DB_NAME:-coinimaging}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8070/web/login}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

UPGRADE_MODULES=""
REFRESH_GROUPS=false

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [options]

Options:
  --upgrade [modules]   Upgrade modules before starting web. Default module is dtsc.
  --refresh-groups      Refresh dynamic user groups view after restart.
  --full                Equivalent to: --upgrade dtsc --refresh-groups
  --db NAME             Override database name. Default: ${DB_NAME}
  --wait SECONDS        Wait timeout for web health check. Default: ${WAIT_SECONDS}
  -h, --help            Show this help.

Examples:
  $(basename "$0")
  $(basename "$0") --upgrade dtsc
  $(basename "$0") --refresh-groups
  $(basename "$0") --full
EOF
}

ensure_db_and_image() {
  mkdir -p "$BASE_DIR/postgresql" "$BASE_DIR/data" "$BASE_DIR/logs" "$BASE_DIR/run"

  if ! docker ps -a --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    docker run -d \
      --name "$DB_CONTAINER" \
      -e POSTGRES_DB=postgres \
      -e POSTGRES_USER=odoo \
      -e POSTGRES_PASSWORD=odoo \
      -e PGDATA=/var/lib/postgresql/data/pgdata \
      -v "$BASE_DIR/postgresql:/var/lib/postgresql/data" \
      -p 5433:5432 \
      postgres:15
  fi

  if ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    docker start "$DB_CONTAINER"
  fi

  if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    docker build -t "$IMAGE_NAME" -f "$BASE_DIR/Dockerfile.runner" "$BASE_DIR"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upgrade)
      if [[ $# -ge 2 && "${2#--}" == "$2" ]]; then
        UPGRADE_MODULES="$2"
        shift 2
      else
        UPGRADE_MODULES="dtsc"
        shift
      fi
      ;;
    --refresh-groups)
      REFRESH_GROUPS=true
      shift
      ;;
    --full)
      UPGRADE_MODULES="dtsc"
      REFRESH_GROUPS=true
      shift
      ;;
    --db)
      DB_NAME="$2"
      shift 2
      ;;
    --wait)
      WAIT_SECONDS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

echo "[1/4] Stopping Odoo 16E..."
"$BASE_DIR/stop_odoo16e.sh"

if [[ -n "$UPGRADE_MODULES" ]]; then
  echo "[2/4] Ensuring database and image..."
  ensure_db_and_image

  echo "[3/4] Upgrading modules: $UPGRADE_MODULES"
  docker run --rm \
    --network host \
    -v "$BASE_DIR:$BASE_DIR" \
    "$IMAGE_NAME" \
    python3 "$BASE_DIR/src/odooE/odoo-bin" \
    -c "$BASE_DIR/odoo.conf" \
    -d "$DB_NAME" \
    -u "$UPGRADE_MODULES" \
    --stop-after-init
else
  echo "[2/4] Skipping module upgrade."
fi

echo "[4/4] Starting Odoo 16E..."
"$BASE_DIR/start_odoo16e.sh"

echo "Waiting for web service..."
deadline=$((SECONDS + WAIT_SECONDS))
until curl -fsS "$HEALTH_URL" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for $HEALTH_URL" >&2
    docker logs --tail 100 "$WEB_NAME" >&2 || true
    exit 1
  fi
  sleep 2
done

if [[ "$REFRESH_GROUPS" == true ]]; then
  echo "Refreshing dynamic user groups view..."
  docker exec -i "$WEB_NAME" \
    python3 "$BASE_DIR/src/odooE/odoo-bin" shell \
    -c "$BASE_DIR/odoo.conf" \
    -d "$DB_NAME" <<'PY'
env['res.groups']._update_user_groups_view()
env.cr.commit()
print("res.groups view refreshed")
PY
else
  echo "Skipping dynamic user groups refresh."
fi

echo "Restart completed."
