#!/usr/bin/env bash
# Ejecuta toda la solución SIN Docker (útil para depurar): datos privados + 9 servicios + portal en http://localhost:8080
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD/src"
export DATABASE_URL="${DATABASE_URL:-sqlite:///./local.db}"
export KMS_KEYS="${KMS_KEYS:-$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')}"
export SEED_DEMO=1 INTERNAL_API_KEY=local-key JWT_SECRET=local-secret-para-desarrollo-0123456789
export DATOS_URL=http://127.0.0.1:8100
rm -f local.db
pids=()
trap 'kill ${pids[@]} 2>/dev/null || true' EXIT
python3 -m uvicorn tramites.datos.main:app --port 8100 --no-access-log & pids+=($!)
sleep 1.5
port=8101
for s in auth ruc rhe declaraciones alertas simulador fraccionamiento pagos documentos; do
  python3 -m uvicorn tramites.$s.main:app --port $port --no-access-log & pids+=($!)
  port=$((port+1))
done
python3 -m uvicorn tramites.gateway_dev:app --port 8080 --no-access-log & pids+=($!)
echo "Portal: http://localhost:8080   (demo: RUC 10123456789 / PSICOLOGA1 / Demo#2026 / TOTP secreto JBSWY3DPEHPK3PXP)"
wait
