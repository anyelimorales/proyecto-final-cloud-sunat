# Guía de ejecución y pruebas

Instrucciones para levantar la plataforma y reproducir las pruebas que sustentan el informe.
Todas las órdenes se ejecutan desde la raíz del repositorio.

---

## 1. Requisitos

| Vía de ejecución | Requisitos |
|---|---|
| Local (recomendada para la sustentación) | Python 3.11 o superior |
| Contenedores | Docker y Docker Compose |
| Kubernetes | `kubectl` y un clúster; para la nube, Terraform y credenciales del proveedor |

La vía local no necesita Docker ni cuenta de nube: usa SQLite y levanta cada microservicio como
un proceso independiente que se comunica por HTTP, igual que lo haría dentro del clúster.

---

## 2. Levantar la plataforma en local

```bash
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
bash scripts/run_local.sh
```

El guion arranca la capa de datos privada, los nueve microservicios y la pasarela que hace de
portal. Cuando termine, abrir **http://localhost:8080**.

Credenciales de demostración:

| Dato | Valor |
|---|---|
| RUC | `10123456789` |
| Usuario | `PSICOLOGA1` |
| Clave | `Demo#2026` |
| Código de verificación | el que imprima `python scripts/totp.py` |

El código del segundo factor cambia cada 30 segundos: generarlo justo antes de escribirlo.

Para detener la plataforma, `Ctrl+C` en la terminal donde corre el guion.

### Con contenedores

```bash
cp .env.example .env     # revisar las claves antes de usarlo fuera de desarrollo
docker compose up --build
```

El portal queda en **http://localhost:8080** y PostgreSQL reemplaza a SQLite.

### En Kubernetes

```bash
kubectl apply -k k8s/onprem     # nube privada: base de datos y capa de datos
kubectl apply -k k8s/publica    # nube pública: portal y microservicios
kubectl get pods -A
```

Los manifiestos se generan con `python scripts/gen_k8s.py`; no se editan a mano.

---

## 3. Ejecutar las pruebas

### 3.1 Pruebas automatizadas

```bash
python -m pytest -q
```

Resultado esperado: **28 pruebas correctas**. No requieren que la plataforma esté levantada:
cada prueba monta los servicios en memoria contra una base de datos temporal.

| Archivo | Qué comprueba |
|---|---|
| `tests/test_flujos.py` | Los flujos completos de cada trámite, paso por paso |
| `tests/test_tramites.py` | Reglas de cálculo, seguridad, cifrado, auditoría y concurrencia |

Para ver el nombre de cada prueba:

```bash
python -m pytest -v
```

### 3.2 El flujo de referencia: emitir un recibo por honorarios

Es la prueba que recorre las cinco etapas del caso. Se ejecuta sola con:

```bash
python -m pytest tests/test_flujos.py::test_flujo_emitir_recibo_por_honorarios -v
```

| Paso | Qué verifica la prueba |
|---|---|
| 1. Identidad | Sin credencial, o con una falsificada, la emisión responde 401 |
| 2. Borde | Un RUC mal formado o un monto negativo se rechazan con 422 antes de llegar al negocio |
| 3. Nube pública | El microservicio calcula la retención del 8 % y el neto, sin tocar la base de datos |
| 4. Nube privada | La constancia se archiva en la gestión documental, se descarga como PDF y en la base figura cifrada (prefijo `v2$`, sin el texto en claro) |
| 5. Notificación | Queda una confirmación en la bandeja del contribuyente; el despachador la entrega una sola vez |
| Transversal | Los tres recursos quedan en la bitácora y la cadena de hashes sigue enlazada |

Los demás trámites siguen el mismo patrón y tienen su propia prueba: pago a cuenta,
declaración anual, fraccionamiento y cambio de régimen.

### 3.3 Prueba de humo contra la plataforma levantada

Con `run_local.sh` o `docker compose` en marcha, en otra terminal:

```bash
python scripts/e2e.py
```

Recorre diecinueve comprobaciones sobre los servicios reales por HTTP: ingreso con segundo
factor, emisión y anulación de recibos, cálculo de renta, fraccionamiento, pago a cuenta,
archivo y descarga de la constancia, rechazo de un archivo que no es PDF, y notificaciones.
Termina con `Resultado: TODO CORRECTO`.

### 3.4 Verificar la bitácora de auditoría

```bash
curl -H "X-Internal-Key: clave-local-insegura" \
     http://localhost:8100/internal/auditoria/verificar
```

Devuelve `{"integra": true, "registros": N}`. Si alguien altera una fila de la bitácora,
`integra` pasa a `false` e indica el primer registro roto.

### 3.5 Simulacro de recuperación ante desastres

Requiere Docker Compose en marcha, porque usa PostgreSQL:

```bash
bash scripts/dr_test.sh
```

Genera un respaldo cifrado, borra la base, la restaura y mide el tiempo empleado, que debe
quedar por debajo del objetivo de recuperación declarado en `docs/DRP.md`.

### 3.6 Prueba de carga

```bash
k6 run tests/load/pico_vencimiento.js
```

Simula el pico de un día de vencimiento sobre los servicios públicos. Requiere
[k6](https://k6.io) instalado.

---

## 4. Qué mirar en la interfaz

| Pantalla | Qué demuestra |
|---|---|
| Inicio | Indicadores del contribuyente y próximos vencimientos |
| Recibos por honorarios | Emisión con cálculo automático de la retención y resumen del ejercicio |
| Pagos a cuenta | Determinación del importe a partir de los recibos del periodo |
| Mi expediente | Constancias en PDF de cada trámite y adjuntado de sustentos |
| Mis alertas | Calendario, suscripción a avisos y bandeja de notificaciones |

---

## 5. Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `Código de verificación inválido` al ingresar | El código del segundo factor caducó. Volver a generarlo con `python scripts/totp.py` |
| El portal responde pero los trámites fallan | La capa de datos privada no arrancó. Revisar el puerto 8100 |
| `Address already in use` | Quedó una ejecución anterior. Cerrarla con `pkill -f "uvicorn tramites"` |
| `ModuleNotFoundError` | Falta activar el entorno virtual o instalar `requirements.txt` |
| La descarga del PDF no inicia | El navegador bloqueó la ventana emergente. Permitir descargas del sitio |
