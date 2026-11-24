#!/usr/bin/env bash
# Restaura un respaldo cifrado en PostgreSQL (Docker Compose). Uso: scripts/restore.sh backups/tramites_<fecha>.sql.enc
set -euo pipefail
cd "$(dirname "$0")/.."
: "${BACKUP_PASSPHRASE:?Defina BACKUP_PASSPHRASE}"
archivo="${1:?Indique el archivo de respaldo}"
sha256sum -c "$archivo.sha256"                       # verifica integridad antes de restaurar
openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in "$archivo" \
  | docker compose exec -T postgres psql -U tramites -d tramites -v ON_ERROR_STOP=1 -q
echo "Restauración completada desde $archivo"
