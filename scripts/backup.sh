#!/usr/bin/env bash
# Respaldo cifrado de PostgreSQL (Docker Compose). En Kubernetes lo ejecuta el CronJob k8s/onprem/50-cronjob-respaldo.yaml.
# IMPORTANTE: los datos sensibles están además cifrados por campo con KMS_KEYS; sin esas claves el respaldo es inutilizable.
# Custodie KMS_KEYS y BACKUP_PASSPHRASE por separado del respaldo (depósito de claves).
set -euo pipefail
cd "$(dirname "$0")/.."
: "${BACKUP_PASSPHRASE:?Defina BACKUP_PASSPHRASE}"
mkdir -p backups
ts=$(date -u +%Y%m%dT%H%M%SZ)
out="backups/tramites_${ts}.sql.enc"
docker compose exec -T postgres pg_dump -U tramites --no-owner --clean --if-exists tramites \
  | openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out "$out"
sha256sum "$out" > "$out.sha256"
find backups -name 'tramites_*.enc*' -mtime +"${RETENCION_DIAS:-14}" -delete
echo "Respaldo creado: $out ($(du -h "$out" | cut -f1))"

# Copia fuera del sitio: sin esto, perder el equipo es perder los respaldos.
# En Kubernetes lo hace el propio CronJob (k8s/onprem/50-cronjob-respaldo.yaml).
if [ -n "${BACKUP_S3_URI:-}" ]; then
  if command -v aws >/dev/null 2>&1; then
    aws s3 cp "$out" "$BACKUP_S3_URI/$(basename "$out")"
    aws s3 cp "$out.sha256" "$BACKUP_S3_URI/$(basename "$out").sha256"
    echo "Replicado en $BACKUP_S3_URI"
  else
    echo "AVISO: BACKUP_S3_URI está definido pero no hay cliente aws; el respaldo quedó solo en disco." >&2
    exit 1
  fi
else
  echo "AVISO: sin BACKUP_S3_URI el respaldo queda solo en este equipo (no cumple el RPO ante pérdida del sitio)." >&2
fi
