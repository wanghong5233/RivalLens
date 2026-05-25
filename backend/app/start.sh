#!/usr/bin/env bash
set -euo pipefail

until python -c "import socket; socket.create_connection((\"rivallens_db\", 5432), timeout=2)" 2>/dev/null; do
  echo "waiting for postgres ..."
  sleep 2
done

alembic upgrade head
exec "$@"
