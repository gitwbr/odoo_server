#!/bin/bash
set -euo pipefail

BASE_DIR="/home/odoo/odoo16/odoo16E"
DB_NAME="odoo16e-db"
WEB_NAME="odoo16e-web"
IMAGE_NAME="odoo16e-runner"

mkdir -p "$BASE_DIR/postgresql" "$BASE_DIR/data" "$BASE_DIR/logs" "$BASE_DIR/run"

if ! docker ps -a --format '{{.Names}}' | grep -qx "$DB_NAME"; then
  docker run -d \
    --name "$DB_NAME" \
    -e POSTGRES_DB=postgres \
    -e POSTGRES_USER=odoo \
    -e POSTGRES_PASSWORD=odoo \
    -e PGDATA=/var/lib/postgresql/data/pgdata \
    -v "$BASE_DIR/postgresql:/var/lib/postgresql/data" \
    -p 5433:5432 \
    postgres:15
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$DB_NAME"; then
  docker start "$DB_NAME"
fi

if ! docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
  docker build -t "$IMAGE_NAME" -f "$BASE_DIR/Dockerfile.runner" "$BASE_DIR"
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$WEB_NAME"; then
  if ! docker ps --format '{{.Names}}' | grep -qx "$WEB_NAME"; then
    docker start "$WEB_NAME"
  fi
else
  docker run -d \
    --name "$WEB_NAME" \
    --network host \
    -v "$BASE_DIR:$BASE_DIR" \
    "$IMAGE_NAME" \
    python3 "$BASE_DIR/src/odooE/odoo-bin" -c "$BASE_DIR/odoo.conf"
fi

echo "Odoo 16E is available at http://127.0.0.1:8070"
