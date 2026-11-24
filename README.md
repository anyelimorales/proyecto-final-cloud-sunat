# Plataforma de trámites tributarios para trabajadores independientes (nube híbrida)

Implementación de referencia del caso **"Modernización de Trámites Digitales para una Entidad de Gobierno"**
(curso de Cloud Computing). Prototipo funcional académico: los valores tributarios son referenciales
(ver `src/tramites/common/parametros.json`) y no sustituyen la normativa vigente.

## Qué contiene

| Requisito del caso | Implementación |
|---|---|
| Nube híbrida con datos sensibles bajo control reforzado | `docker-compose.yml` (redes `publica` / `enlace` / `privada`), `k8s/publica` y `k8s/onprem`, `infra/terraform` |
| Seguridad, cifrado e identidades | MFA (TOTP) + JWT, cifrado por campo AES-256-GCM con rotación de claves, bitácora con cadena de hashes de un solo escritor, red privada aislada, NetworkPolicies, WAF (ver `docs/SEGURIDAD.md`) |
| Contenerización y actualizaciones sin caída | `docker/`, despliegue *rolling* con `maxUnavailable: 0`, HPA, PDB, CI/CD con reversión automática |
| Plan de continuidad y DRP | `docs/DRP.md`, `scripts/backup.sh`, `restore.sh`, `dr_test.sh`, réplica de respaldos y DNS con failover |

Trámites implementados (microservicios): **auth** (Clave SOL simulada + MFA), **ruc**, **rhe**, **declaraciones**,
**pagos** (pagos a cuenta mensuales), **documentos** (gestión documental del expediente), **alertas**,
**simulador**, **fraccionamiento**, más **datos-privados** (única capa con acceso a la base de datos) y el
**portal** web.

## Arquitectura

```
Ciudadano ─► portal (nginx: TLS en el balanceador, límites de tasa, CSP) ─► microservicios (nube pública)
                                                                              │  red "enlace" (VPN/enlace dedicado)
                                                                              ▼
                                                       datos-privados ─► PostgreSQL   (nube privada, red aislada)
```

## Inicio rápido

### Opción A: Docker Compose (recomendada)
```bash
cp .env.example .env
python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"   # pegue el resultado en KMS_KEYS
# edite .env (contraseñas y claves) y luego:
docker compose up --build -d
python3 scripts/e2e.py http://localhost:8080      # prueba de humo extremo a extremo
```
Portal: <http://localhost:8080>. Usuario demo (`SEED_DEMO=1`): RUC `10123456789`, usuario `PSICOLOGA1`, clave `Demo#2026`.
El segundo factor es TOTP con el secreto `JBSWY3DPEHPK3PXP` (agréguelo a una app autenticadora o ejecute `python3 scripts/totp.py`).

### Opción B: sin Docker (depuración)
```bash
pip install -r requirements-dev.txt
bash scripts/run_local.sh        # datos + 9 servicios + portal en http://localhost:8080 (SQLite)
```

### Pruebas
```bash
pip install -r requirements-dev.txt
python -m pytest -q              # 28 pruebas: negocio, flujos de 5 pasos, seguridad, cifrado y auditoría
python scripts/e2e.py            # contra el portal desplegado
k6 run tests/load/pico_vencimiento.js   # carga de un día de vencimiento
```

### Kubernetes
```bash
python scripts/gen_k8s.py                       # regenera manifiestos (tras cambiar servicios)
kubectl apply -k k8s/onprem                     # en el clúster del centro de datos
kubectl apply -k k8s/publica                    # en el clúster de la nube pública (ajustar REGISTRO, IP 10.20.0.10, ARNs)
```

### Simulacro de desastre (Compose)
```bash
export BACKUP_PASSPHRASE='una-frase-larga'
scripts/dr_test.sh        # respalda, destruye la base, restaura y reporta el RTO medido
```

## Estructura
```
src/tramites/       código (common, auth, ruc, rhe, declaraciones, alertas, simulador, fraccionamiento, datos)
portal/             sitio web estático y nginx (puerta de enlace)
docker/             Dockerfiles        k8s/    manifiestos       infra/terraform/   nube pública (AWS)
scripts/            e2e, DRP, generador de manifiestos          monitoring/        métricas y alertas
tests/              pruebas unitarias/integración y de carga     docs/              seguridad y DRP
```

## Estado de verificación
Verificado en el entorno de desarrollo: 28 pruebas automatizadas (con las versiones fijadas en `requirements.txt`) y una
prueba de humo extremo a extremo con los servicios como procesos separados comunicándose por HTTP.
**No ejecutado aquí** (sin Docker, clúster ni cuenta de nube): construcción de imágenes, `docker compose up`, manifiestos
de Kubernetes (solo validada su estructura YAML), Terraform (`plan/apply`), el flujo de CI/CD y `dr_test.sh`.
Esos artefactos son la configuración propuesta; conviene validarlos en su entorno antes de presentarlos como probados.

## Limitaciones del prototipo
Autenticación simulada (sin integración con la Clave SOL real); JWT HS256 con secreto compartido (en producción: IdP con
RS256/OIDC); bloqueo por intentos en memoria (en producción: almacén compartido); la clave de cifrado llega por variable de
entorno (en producción: KMS/HSM); TLS lo termina el balanceador (en Compose es HTTP local); cronograma de vencimientos ilustrativo.
