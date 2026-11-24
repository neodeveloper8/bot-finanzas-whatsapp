#!/usr/bin/env bash
# Respaldo diario de la BD (cron de botfin). Guarda 14 días.
set -euo pipefail

DB=/home/botfin/datos/db.sqlite3
DESTINO=/home/botfin/backups
mkdir -p "$DESTINO"

# Usa la API de backup de SQLite: copia consistente aunque el bot esté escribiendo.
# (Un simple `cp` con WAL activo podría copiar la BD a medio actualizar.)
/home/botfin/bot-finanzas/.venv/bin/python - "$DB" "$DESTINO/db-$(date +%F).sqlite3" <<'PY'
import sqlite3, sys
origen, destino = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
origen.backup(destino)
destino.close(); origen.close()
PY

find "$DESTINO" -name 'db-*.sqlite3' -mtime +14 -delete
