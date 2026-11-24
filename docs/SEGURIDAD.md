# Controles de seguridad implementados

Correspondencia con los requerimientos técnicos (RT) y normativos del informe.

| Control | Implementación | Requisito |
|---|---|---|
| Autenticación multifactor | `auth`: clave (PBKDF2-SHA256, 310 000 iteraciones) + TOTP; el token del primer factor (tipo `mfa`, 5 min) no sirve para acceder a la API | RT-06, RT-12 |
| Bloqueo por fuerza bruta | 5 fallos en 5 minutos → HTTP 429; además límite de tasa en nginx (`/api/auth/login`: 10/min) | RT-06, RT-07 |
| Autorización | Todos los endpoints con datos personales exigen JWT de acceso; el RUC se toma del token, nunca del cuerpo de la solicitud; recursos ajenos devuelven 404 | Ley 29733, reserva tributaria |
| Cifrado en reposo | `datos-privados` cifra cada documento con **AES-256-GCM** (cifrado autenticado) antes de escribirlo; la lista `KMS_KEYS` permite rotar claves (la primera cifra, todas descifran) y los documentos del formato anterior se siguen leyendo | RT-04, RT-05 |
| Custodia de claves | Claves por variable de entorno desde el gestor de secretos; en producción KMS/HSM institucional. Se prueban en `tests/test_tramites.py` (el texto plano no aparece en disco) | RT-05 |
| Cifrado en tránsito | TLS 1.2+/1.3 en el balanceador (`50-ingress.yaml`, política `TLS13-1-2`) y HSTS; VPN IPsec / enlace dedicado entre nubes | RT-04, RT-11 |
| Aislamiento híbrido | Compose: red `privada` interna y sin ruta al exterior. K8s: `NetworkPolicy` de denegación por defecto; los servicios solo salen hacia `10.20.0.0/24:8000` | RT-07, RT-14 |
| Acceso entre servicios | Clave interna `X-Internal-Key` hacia `datos-privados` (en producción añadir mTLS) | RT-06 |
| Gestión documental | Las constancias de cada trámite y los sustentos del contribuyente se guardan cifrados en la capa privada; el adjunto se valida por firma binaria (PDF/PNG/JPG) y se limita a 2 MB; solo el titular descarga su expediente | RT-04, RT-07 |
| Notificación | Cada trámite completado deja una confirmación persistente que el despachador entrega una sola vez; el RUC se enmascara en los registros | RT-08 |
| Auditoría | Cada lectura/escritura se registra (origen, usuario, acción, recurso) en una cadena de hashes SHA-256; `/internal/auditoria/verificar` detecta alteraciones. Con varias réplicas la escritura se serializa (cerrojo consultivo en PostgreSQL) y `hash_prev` es único, de modo que la cadena no se bifurca (probado con 30 escrituras concurrentes) | RT-08 |
| Registros sin datos personales | Los logs de aplicación no incluyen cuerpos; el despachador enmascara el RUC | Ley 29733 |
| Endurecimiento de contenedores | Usuario no root, sistema de archivos de solo lectura, `cap_drop: ALL`, `no-new-privileges`, seccomp `RuntimeDefault`, Pod Security `restricted` | RT-09 |
| Cadena de suministro | Imágenes escaneadas con Trivy en CI (falla con severidad alta/crítica), etiquetas inmutables en ECR, dependencias fijadas | RT-10 |
| Perímetro | CSP, X-Frame-Options, HSTS, nosniff; WAF administrado (`infra/terraform/main.tf`) | RT-07 |
| XSS | El portal inserta contenido con `textContent`; CSP sin scripts en línea | RT-07 |
| Observabilidad | `/health`, `/metrics` (Prometheus), logs JSON con identificador de solicitud; reglas en `monitoring/` | RT-13 |

## Pendiente para un entorno real
Integración con la Clave SOL/IdP institucional (OIDC, RS256); mTLS entre nubes; KMS/HSM; gestor de secretos con rotación;
SIEM; pruebas de penetración; registro del banco de datos personales y evaluación de impacto según la Ley 29733 y su reglamento;
revisión de que los datos sensibles no salgan del país (flujo transfronterizo).
