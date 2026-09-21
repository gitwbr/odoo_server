#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker compose --project-directory "$BASE_DIR" -f "$BASE_DIR/compose.yml" up -d --wait --wait-timeout 180
echo "Community test: http://127.0.0.1:8075/web/login"
