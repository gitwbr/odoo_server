#!/bin/bash
set -euo pipefail

docker stop odoo16e-web odoo16e-ai-gateway odoo16e-db 2>/dev/null || true
