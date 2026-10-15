#!/bin/bash
# 企業版測試環境重啟腳本（不是正式環境）
#
# 訪問網址：
#   首頁：https://coinimaging.euhon.com
#   後台登入：https://coinimaging.euhon.com/web/login
#   會員圖片檢測：https://coinimaging.euhon.com/my/ai-check
#   伺服器本機：http://127.0.0.1:8070
#
# 使用方式（在伺服器終端執行，依需求擇一）：
#   1. 僅重啟，不執行模組升級；Python 程式修改（如 RGB 攔截）使用此方式。
#      sudo bash /home/odoo/odoo16/odoo16E/restart_odoo16e.sh
#   2. 升級 dtsc 模組並重啟；XML 視圖／頁面說明文字修改也要生效時使用。
#      此方式會正常更新 coinimaging 資料庫中的 dtsc 模組。
#      sudo bash /home/odoo/odoo16/odoo16E/restart_odoo16e.sh --upgrade dtsc
#
# 其他選項：
#   --upgrade 模組1,模組2  升級指定模組；省略模組名稱時預設為 dtsc。
#   --full                升級 dtsc,dtsc_ai_gateway,dtsc_ai_assistant 並重啟。
#   --refresh-groups      重啟後重新產生使用者群組視圖，會寫入資料庫。
#   --db 資料庫名稱       指定升級／群組視圖更新使用的資料庫，預設 coinimaging。
#   --wait 秒數           設定每項服務健康檢查的等待上限，預設 120 秒。
#   --help                顯示完整用法，不執行重啟。
#
# 腳本會重啟企業版 Web、AI Gateway 與資料庫，並等待服務健康檢查通過。
# 終端顯示「Restart completed.」表示完成；若顯示錯誤或逾時，請查看輸出日誌。
#
set -euo pipefail

BASE_DIR="/home/odoo/odoo16/odoo16E"
DB_CONTAINER="odoo16e-db"
WEB_NAME="odoo16e-web"
IMAGE_NAME="odoo16e-runner"
DB_NAME="${DB_NAME:-coinimaging}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8070/web/login}"
AI_GATEWAY_HEALTH_URL="${AI_GATEWAY_HEALTH_URL:-http://127.0.0.1:8071/health}"
WAIT_SECONDS="${WAIT_SECONDS:-120}"

UPGRADE_MODULES=""
REFRESH_GROUPS=false
FULL_UPGRADE_MODULES="dtsc,dtsc_ai_gateway,dtsc_ai_assistant"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") [options]

Options:
  --upgrade [modules]   Upgrade modules before starting web. Default module is dtsc.
  --refresh-groups      Refresh dynamic user groups view after restart.
  --full                Equivalent to: --upgrade ${FULL_UPGRADE_MODULES}
  --db NAME             Override database name. Default: ${DB_NAME}
  --wait SECONDS        Wait timeout for web health check. Default: ${WAIT_SECONDS}
  -h, --help            Show this help.

Examples:
  $(basename "$0")
  $(basename "$0") --upgrade dtsc
  $(basename "$0") --refresh-groups
  $(basename "$0") --full
  $(basename "$0") --full --refresh-groups
EOF
}

ensure_db_and_image() {
  local runner_definition_hash
  local image_definition_hash

  mkdir -p "$BASE_DIR/postgresql" "$BASE_DIR/data" "$BASE_DIR/logs" "$BASE_DIR/run"

  if ! docker ps -a --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    docker run -d \
      --name "$DB_CONTAINER" \
      -e POSTGRES_DB=postgres \
      -e POSTGRES_USER=odoo \
      -e POSTGRES_PASSWORD=odoo \
      -e PGDATA=/var/lib/postgresql/data/pgdata \
      -v "$BASE_DIR/postgresql:/var/lib/postgresql/data" \
      -p 127.0.0.1:5433:5432 \
      postgres:15
  fi

  if ! docker ps --format '{{.Names}}' | grep -qx "$DB_CONTAINER"; then
    docker start "$DB_CONTAINER"
  fi

  runner_definition_hash="$(sha256sum "$BASE_DIR/Dockerfile.runner" | awk '{print $1}')"
  image_definition_hash="$(
    docker image inspect \
      --format '{{index .Config.Labels "com.coinimaging.runner-definition-sha256"}}' \
      "$IMAGE_NAME" 2>/dev/null || true
  )"

  if [[ "$image_definition_hash" != "$runner_definition_hash" ]]; then
    echo "Rebuilding stale Odoo 16E runner image..."
    docker build \
      --label "com.coinimaging.runner-definition-sha256=$runner_definition_hash" \
      -t "$IMAGE_NAME" \
      -f "$BASE_DIR/Dockerfile.runner" \
      "$BASE_DIR"
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
      UPGRADE_MODULES="$FULL_UPGRADE_MODULES"
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

echo "Waiting for AI gateway service..."
deadline=$((SECONDS + WAIT_SECONDS))
until curl -fsS "$AI_GATEWAY_HEALTH_URL" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for $AI_GATEWAY_HEALTH_URL" >&2
    docker logs --tail 100 odoo16e-ai-gateway >&2 || true
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
