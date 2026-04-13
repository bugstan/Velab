#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

POSTGRES_HOST="127.0.0.1"
POSTGRES_PORT="5432"
POSTGRES_DB="fota_db"
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="fota_password"

if [[ -f "$ENV_FILE" ]]; then
    set -a
    source "$ENV_FILE"
    set +a
    POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
    POSTGRES_PORT="${POSTGRES_PORT:-5432}"
    POSTGRES_DB="${POSTGRES_DB:-fota_db}"
    POSTGRES_USER="${POSTGRES_USER:-postgres}"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-fota_password}"
fi

if [[ "${1:-}" != "--yes" ]]; then
    echo "This will DROP and recreate database '$POSTGRES_DB'."
    echo "Run: $0 --yes"
    exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
    echo "psql not found"
    exit 1
fi

if ! sudo -n true >/dev/null 2>&1; then
    echo "passwordless sudo is required to recreate PostgreSQL database"
    exit 1
fi

if command -v pg_ctlcluster >/dev/null 2>&1; then
    cluster_info="$(pg_lsclusters | awk '$1 ~ /^[0-9]+$/ && $3 == 5432 {print $1, $2, $4; exit}')"
    if [[ -n "$cluster_info" ]]; then
        cluster_version="$(echo "$cluster_info" | awk '{print $1}')"
        cluster_name="$(echo "$cluster_info" | awk '{print $2}')"
        cluster_status="$(echo "$cluster_info" | awk '{print $3}')"
        if [[ "$cluster_status" != "online" ]]; then
            sudo pg_ctlcluster "$cluster_version" "$cluster_name" start
        fi
    fi
fi

sudo -u postgres psql -v ON_ERROR_STOP=1 --dbname postgres <<EOSQL
ALTER ROLE ${POSTGRES_USER} WITH PASSWORD '${POSTGRES_PASSWORD}';
DROP DATABASE IF EXISTS ${POSTGRES_DB} WITH (FORCE);
CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};
EOSQL

cd "$ROOT_DIR"

if [[ ! -d venv ]]; then
    python3 -m venv venv
fi

source venv/bin/activate

python - <<'PY'
from database import db_manager
from models import Case, RawLogFile, DiagnosisEvent
from models.diagnosis import ConfirmedDiagnosis

db_manager.initialize()
db_manager.create_tables()
db_manager.close()
print("Database recreated successfully")
PY

echo "Reset complete: ${POSTGRES_DB}"