#!/bin/bash
# 啟動心跳循環，放到背景
while true; do
    echo "Heartbeat at $(date)"
    sleep 5
done &

# 啟動原本的 entrypoint.sh
if [ $# -eq 0 ]; then
    exec /entrypoint.sh odoo
else
    exec /entrypoint.sh "$@"
fi