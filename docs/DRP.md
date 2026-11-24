# Plan de continuidad y recuperación ante desastres (DRP)

## Objetivos de diseño (propuestos, a validar con la entidad)
| Servicio | Criticidad | RTO | RPO |
|---|---|---|---|
| RHE, declaraciones, pagos a cuenta | Muy alta | 2 h | 15 min |
| RUC, alertas, fraccionamiento, identidad | Alta | 4 h | 15 min |
| Simulador, calendario público | Media | 8 h | no aplica (sin datos propios) |

## Estrategia
| Componente | Medida |
|---|---|
| Portal y microservicios (nube pública) | ≥ 3 réplicas en varias zonas (topologySpread + PDB); imágenes en el registro, redespliegue desde cero con `kubectl apply -k` o el flujo de CI/CD |
| Región de recuperación | Clúster "pilot light" en la región DR (mínimo de réplicas) y DNS con *failover* (`infra/terraform/main.tf`, TTL 30 s) |
| Base de datos tributaria (nube privada) | Respaldo cifrado cada 15 min (`50-cronjob-respaldo.yaml`): un *initContainer* vuelca y cifra en disco y el contenedor principal **sube la copia al bucket de respaldos**, que replica a la región DR. El acceso es por rol IRSA con permiso de solo escritura sobre `postgres/` (`infra/terraform/main.tf`). Pendiente en producción: réplica síncrona/asíncrona de PostgreSQL y archivado WAL para un RPO menor |
| Claves de cifrado | **Depósito de claves** separado (KMS_KEYS y BACKUP_PASSPHRASE): sin ellas los respaldos no se pueden leer |
| Configuración | Todo versionado (IaC, manifiestos, CI/CD): la reconstrucción es automática |

## Escenarios y respuesta
1. **Falla de un pod o nodo:** Kubernetes reprograma; sin acción humana (RTO de segundos).
2. **Despliegue defectuoso:** `kubectl rollout undo` (el flujo de CI/CD lo hace automáticamente si `rollout status` falla).
3. **Caída de la zona o región pública:** declarar incidente → DNS conmuta a la región DR → escalar réplicas → verificar con `scripts/e2e.py`. Los datos sensibles siguen en el centro de datos; el túnel VPN de la región DR debe estar preconfigurado.
4. **Pérdida del enlace híbrido:** los servicios que no usan datos personales (calendario, simulador) siguen operando; el resto responde 503 de forma controlada. Activar el enlace/VPN de respaldo.
5. **Pérdida del centro de datos:** levantar `k8s/onprem` en el sitio alterno, restaurar el último respaldo y apuntar el `Endpoints` de `datos-privados` a la nueva IP.
6. **Corrupción o ransomware:** restaurar desde una versión previa del bucket (versionado habilitado) tras verificar la cadena de auditoría.

## Procedimiento de restauración de la base (Compose)
```bash
export BACKUP_PASSPHRASE=...            # del depósito de claves
scripts/restore.sh backups/tramites_<fecha>.sql.enc
```

## Pruebas
| Prueba | Frecuencia | Cómo |
|---|---|---|
| Restauración de respaldo | Mensual | `scripts/dr_test.sh` |
| Conmutación a la región DR | Semestral | Reducir peso DNS del primario, ejecutar `scripts/e2e.py` sobre DR |
| Carga del día de vencimiento | Antes de cada campaña | `tests/load/pico_vencimiento.js`, observar `kubectl get hpa -w` |
| Verificar cadena de auditoría | Tras cada restauración | `GET /internal/auditoria/verificar` |

Registrar cada prueba con el RTO/RPO medido y las acciones correctivas.
