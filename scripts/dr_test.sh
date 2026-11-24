#!/usr/bin/env bash
# Simulacro de desastre en el centro de datos (Docker Compose): pérdida total de la base de datos.
# Mide el tiempo de recuperación real (RTO) y verifica que los datos restaurados siguen siendo legibles.
# Uso: BACKUP_PASSPHRASE=... scripts/dr_test.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${BACKUP_PASSPHRASE:?Defina BACKUP_PASSPHRASE}"
BASE="${BASE_URL:-http://localhost:8080}"
paso() { printf '\n== %s\n' "$*"; }

paso "1. Estado inicial: prueba de humo"
python3 scripts/e2e.py "$BASE" >/dev/null && echo "OK"

paso "2. Respaldo cifrado (punto de recuperación)"
scripts/backup.sh
ultimo=$(ls -1t backups/tramites_*.sql.enc | head -1)

paso "3. DESASTRE: se destruye la base de datos y su volumen"
inicio=$(date +%s)
docker compose stop datos-privados postgres
docker compose rm -f -v postgres
docker volume rm tramites_pgdata >/dev/null 2>&1 || true

paso "4. Recuperación: nuevo PostgreSQL + restauración + capa de datos"
docker compose up -d postgres
until docker compose exec -T postgres pg_isready -U tramites >/dev/null 2>&1; do sleep 1; done
scripts/restore.sh "$ultimo"
docker compose up -d datos-privados
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q datos-privados)")" = "healthy" ]; do sleep 2; done
fin=$(date +%s)

paso "5. Verificación funcional posterior a la recuperación"
python3 scripts/e2e.py "$BASE"
echo
echo "RTO medido: $((fin-inicio)) segundos (objetivo del diseño: 7200 s)"
echo "RPO: datos posteriores al último respaldo ($(date -u -r "$ultimo" +%FT%TZ)) se pierden; objetivo del diseño: 15 min con respaldos cada 15 min"
