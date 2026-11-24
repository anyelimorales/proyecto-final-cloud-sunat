"""Genera los manifiestos de Kubernetes (k8s/publica y k8s/onprem) a partir de una descripción única.
Uso: python scripts/gen_k8s.py      (requiere pyyaml)"""
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1] / "k8s"
NS = "tramites"
ETQ = {"app.kubernetes.io/part-of": "tramites-tributarios"}

# nombre: (min_replicas, max_replicas, cpu_req, mem_req, requiere_datos)
SERVICIOS = {
    "auth": (3, 20, "100m", "128Mi", True), "ruc": (2, 10, "100m", "128Mi", True),
    "rhe": (3, 30, "150m", "128Mi", True), "declaraciones": (3, 30, "150m", "128Mi", True),
    "alertas": (2, 20, "100m", "128Mi", True), "simulador": (2, 20, "100m", "128Mi", False),
    "fraccionamiento": (2, 10, "100m", "128Mi", True), "pagos": (3, 30, "150m", "128Mi", True), "documentos": (2, 12, "150m", "192Mi", True),
}


def dump(ruta: Path, *docs):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("\n---\n".join(yaml.dump(d, sort_keys=False, allow_unicode=True, width=120) for d in docs), encoding="utf-8")


def seguridad(uid=10001):
    return {"runAsNonRoot": True, "runAsUser": uid, "allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]}, "seccompProfile": {"type": "RuntimeDefault"}}


def deployment(nombre, imagen, puerto, minr, cpu, mem, env_from=True, uid=10001, ruta_salud="/health"):
    et = {"app": nombre, **ETQ}
    cont = {
        "name": nombre, "image": imagen, "imagePullPolicy": "IfNotPresent", "ports": [{"containerPort": puerto, "name": "http"}],
        "securityContext": seguridad(uid),
        "resources": {"requests": {"cpu": cpu, "memory": mem}, "limits": {"cpu": "500m", "memory": "256Mi"}},
        "readinessProbe": {"httpGet": {"path": ruta_salud, "port": "http"}, "periodSeconds": 5, "failureThreshold": 3},
        "livenessProbe": {"httpGet": {"path": ruta_salud, "port": "http"}, "initialDelaySeconds": 10, "periodSeconds": 10},
        "lifecycle": {"preStop": {"exec": {"command": ["sleep", "10"]}}},   # drenaje de conexiones en despliegues
        "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
    }
    if env_from:
        cont["envFrom"] = [{"configMapRef": {"name": "tramites-config"}}, {"secretRef": {"name": "tramites-secretos"}}]
    return {
        "apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": nombre, "namespace": NS, "labels": et},
        "spec": {
            "replicas": minr, "revisionHistoryLimit": 5,
            "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": 0}},  # sin caída de servicio
            "selector": {"matchLabels": {"app": nombre}},
            "template": {"metadata": {"labels": et}, "spec": {
                "terminationGracePeriodSeconds": 30, "automountServiceAccountToken": False,
                "topologySpreadConstraints": [{"maxSkew": 1, "topologyKey": "topology.kubernetes.io/zone", "whenUnsatisfiable": "ScheduleAnyway",
                                               "labelSelector": {"matchLabels": {"app": nombre}}}],
                "containers": [cont], "volumes": [{"name": "tmp", "emptyDir": {}}]}},
        },
    }


def servicio(nombre, puerto_dest):
    return {"apiVersion": "v1", "kind": "Service", "metadata": {"name": nombre, "namespace": NS, "labels": {"app": nombre, **ETQ}},
            "spec": {"selector": {"app": nombre}, "ports": [{"name": "http", "port": puerto_dest if nombre == "portal" else 8000, "targetPort": "http"}]}}


def hpa(nombre, minr, maxr):
    return {"apiVersion": "autoscaling/v2", "kind": "HorizontalPodAutoscaler", "metadata": {"name": nombre, "namespace": NS},
            "spec": {"scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": nombre},
                     "minReplicas": minr, "maxReplicas": maxr,
                     "metrics": [{"type": "Resource", "resource": {"name": "cpu", "target": {"type": "Utilization", "averageUtilization": 60}}}],
                     "behavior": {"scaleUp": {"stabilizationWindowSeconds": 0, "policies": [{"type": "Percent", "value": 100, "periodSeconds": 30}]},
                                  "scaleDown": {"stabilizationWindowSeconds": 300}}}}


def pdb(nombre):
    return {"apiVersion": "policy/v1", "kind": "PodDisruptionBudget", "metadata": {"name": nombre, "namespace": NS},
            "spec": {"minAvailable": 1, "selector": {"matchLabels": {"app": nombre}}}}


# ------------------------------------------------------------------ NUBE PÚBLICA (clúster Kubernetes gestionado)
pub = RAIZ / "publica"
dump(pub / "00-namespace.yaml", {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": NS, "labels": {
    "pod-security.kubernetes.io/enforce": "restricted", "pod-security.kubernetes.io/audit": "restricted", **ETQ}}})

dump(pub / "10-config-secretos.yaml",
     {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "tramites-config", "namespace": NS},
      "data": {"DATOS_URL": "http://datos-privados:8000", "JWT_MINUTOS": "30"}},
     {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "tramites-secretos", "namespace": NS,
                                                         "annotations": {"nota": "PLANTILLA. En producción se sincroniza desde el gestor de secretos (External Secrets / CSI). No versionar valores reales."}},
      "type": "Opaque", "stringData": {"INTERNAL_API_KEY": "REEMPLAZAR", "JWT_SECRET": "REEMPLAZAR"}})

# Enlace híbrido: el servicio "datos-privados" apunta a la IP del centro de datos, alcanzable por VPN / enlace dedicado.
dump(pub / "20-enlace-datos-privados.yaml",
     {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "datos-privados", "namespace": NS},
      "spec": {"ports": [{"name": "http", "port": 8000, "targetPort": 8000}]}},
     {"apiVersion": "v1", "kind": "Endpoints", "metadata": {"name": "datos-privados", "namespace": NS},
      "subsets": [{"addresses": [{"ip": "10.20.0.10"}], "ports": [{"name": "http", "port": 8000}]}]})

for n, (mn, mx, cpu, mem, _) in SERVICIOS.items():
    dump(pub / f"30-{n}.yaml", deployment(n, f"tramites/{n}:latest", 8000, mn, cpu, mem), servicio(n, 8000), hpa(n, mn, mx), pdb(n))

dump(pub / "40-portal.yaml", deployment("portal", "tramites/portal:latest", 8080, 3, "100m", "64Mi", env_from=False, uid=101, ruta_salud="/healthz"),
     servicio("portal", 80), hpa("portal", 3, 30), pdb("portal"))

dump(pub / "50-ingress.yaml", {
    "apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
    "metadata": {"name": "portal", "namespace": NS, "annotations": {
        "alb.ingress.kubernetes.io/scheme": "internet-facing", "alb.ingress.kubernetes.io/target-type": "ip",
        "alb.ingress.kubernetes.io/listen-ports": '[{"HTTPS":443}]', "alb.ingress.kubernetes.io/ssl-policy": "ELBSecurityPolicy-TLS13-1-2-2021-06",
        "alb.ingress.kubernetes.io/healthcheck-path": "/healthz",
        "alb.ingress.kubernetes.io/wafv2-acl-arn": "REEMPLAZAR_ARN_WAF",
        "alb.ingress.kubernetes.io/certificate-arn": "REEMPLAZAR_ARN_CERTIFICADO"}},
    "spec": {"ingressClassName": "alb", "rules": [{"host": "tramites.ejemplo.gob.pe", "http": {"paths": [
        {"path": "/", "pathType": "Prefix", "backend": {"service": {"name": "portal", "port": {"number": 80}}}}]}}]}})

netpol = [
    {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "denegar-todo", "namespace": NS},
     "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}},
    {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "dns", "namespace": NS},
     "spec": {"podSelector": {}, "policyTypes": ["Egress"], "egress": [{"to": [{"namespaceSelector": {}}], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}},
    {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "portal-entrada-salida", "namespace": NS},
     "spec": {"podSelector": {"matchLabels": {"app": "portal"}}, "policyTypes": ["Ingress", "Egress"],
              "ingress": [{"ports": [{"port": 8080}]}],   # tráfico desde el balanceador (restringir al CIDR de la VPC en producción)
              "egress": [{"to": [{"podSelector": {"matchLabels": {"app": n}}}], "ports": [{"port": 8000}]} for n in SERVICIOS]}},
    {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "servicios-solo-desde-portal", "namespace": NS},
     "spec": {"podSelector": {"matchExpressions": [{"key": "app", "operator": "In", "values": list(SERVICIOS)}]}, "policyTypes": ["Ingress"],
              "ingress": [{"from": [{"podSelector": {"matchLabels": {"app": "portal"}}}], "ports": [{"port": 8000}]}]}},
    {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "servicios-hacia-datos-privados", "namespace": NS},
     "spec": {"podSelector": {"matchExpressions": [{"key": "app", "operator": "In", "values": [n for n, v in SERVICIOS.items() if v[4]]}]}, "policyTypes": ["Egress"],
              "egress": [{"to": [{"ipBlock": {"cidr": "10.20.0.0/24"}}], "ports": [{"port": 8000}]}]}},   # solo hacia el centro de datos
]
dump(pub / "60-networkpolicies.yaml", *netpol)

dump(pub / "70-cronjob-alertas.yaml", {
    "apiVersion": "batch/v1", "kind": "CronJob", "metadata": {"name": "alertas-despachador", "namespace": NS},
    "spec": {"schedule": "*/15 * * * *", "concurrencyPolicy": "Forbid", "successfulJobsHistoryLimit": 3, "failedJobsHistoryLimit": 3,
             "jobTemplate": {"spec": {"backoffLimit": 2, "template": {"metadata": {"labels": {"app": "alertas", **ETQ}}, "spec": {
                 "restartPolicy": "Never", "automountServiceAccountToken": False,
                 "containers": [{"name": "despachador", "image": "tramites/alertas:latest", "command": ["python", "-m", "tramites.alertas.dispatcher"],
                                 "envFrom": [{"configMapRef": {"name": "tramites-config"}}, {"secretRef": {"name": "tramites-secretos"}}],
                                 "securityContext": seguridad(), "resources": {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"cpu": "200m", "memory": "128Mi"}}}]}}}}}})

dump(pub / "kustomization.yaml", {
    "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "namespace": NS,
    "resources": sorted(p.name for p in pub.glob("*.yaml") if p.name != "kustomization.yaml"),
    "images": [{"name": f"tramites/{n}", "newName": f"REGISTRO/tramites-{n}", "newTag": "latest"} for n in [*SERVICIOS, "portal"]]})

# ------------------------------------------------------------------ NUBE PRIVADA (centro de datos, clúster local)
pri = RAIZ / "onprem"
dump(pri / "00-namespace.yaml", {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": "tramites-datos", "labels": {
    "pod-security.kubernetes.io/enforce": "restricted", **ETQ}}})
NSD = "tramites-datos"

dump(pri / "10-secretos.yaml", {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "datos-secretos", "namespace": NSD,
    "annotations": {"nota": "PLANTILLA. KMS_KEYS debe provenir del HSM/KMS institucional; POSTGRES_PASSWORD de la bóveda de secretos."}},
    "type": "Opaque", "stringData": {"POSTGRES_PASSWORD": "REEMPLAZAR", "INTERNAL_API_KEY": "REEMPLAZAR", "JWT_SECRET": "REEMPLAZAR", "KMS_KEYS": "REEMPLAZAR",
                                     "BACKUP_PASSPHRASE": "REEMPLAZAR"}})

postgres = {
    "apiVersion": "apps/v1", "kind": "StatefulSet", "metadata": {"name": "postgres", "namespace": NSD},
    "spec": {"serviceName": "postgres", "replicas": 1, "selector": {"matchLabels": {"app": "postgres"}},
             "template": {"metadata": {"labels": {"app": "postgres", **ETQ}}, "spec": {
                 "securityContext": {"runAsNonRoot": True, "runAsUser": 70, "fsGroup": 70, "seccompProfile": {"type": "RuntimeDefault"}},
                 "containers": [{"name": "postgres", "image": "postgres:16-alpine", "ports": [{"containerPort": 5432, "name": "pg"}],
                                 "env": [{"name": "POSTGRES_DB", "value": "tramites"}, {"name": "POSTGRES_USER", "value": "tramites"},
                                         {"name": "POSTGRES_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "datos-secretos", "key": "POSTGRES_PASSWORD"}}},
                                         {"name": "PGDATA", "value": "/var/lib/postgresql/data/pgdata"}],
                                 "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                                 "readinessProbe": {"exec": {"command": ["pg_isready", "-U", "tramites"]}, "periodSeconds": 5},
                                 "resources": {"requests": {"cpu": "500m", "memory": "1Gi"}, "limits": {"memory": "2Gi"}},
                                 "volumeMounts": [{"name": "datos", "mountPath": "/var/lib/postgresql/data"}]}]}},
             "volumeClaimTemplates": [{"metadata": {"name": "datos"}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "50Gi"}}}}]}}
dump(pri / "20-postgres.yaml", postgres, {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "postgres", "namespace": NSD},
                                          "spec": {"clusterIP": "None", "selector": {"app": "postgres"}, "ports": [{"port": 5432, "name": "pg"}]}})

datos_dep = deployment("datos-privados", "tramites/datos:latest", 8000, 2, "200m", "128Mi", env_from=False)
datos_dep["metadata"]["namespace"] = NSD
c = datos_dep["spec"]["template"]["spec"]["containers"][0]
sec = lambda k: {"valueFrom": {"secretKeyRef": {"name": "datos-secretos", "key": k}}}
c["env"] = [{"name": "DATABASE_URL", "value": "postgresql+psycopg2://tramites:$(POSTGRES_PASSWORD)@postgres:5432/tramites"},
            {"name": "POSTGRES_PASSWORD", **sec("POSTGRES_PASSWORD")}, {"name": "INTERNAL_API_KEY", **sec("INTERNAL_API_KEY")},
            {"name": "JWT_SECRET", **sec("JWT_SECRET")}, {"name": "KMS_KEYS", **sec("KMS_KEYS")}]
# DATABASE_URL referencia POSTGRES_PASSWORD: debe declararse después de ella
c["env"] = [c["env"][1]] + [c["env"][0]] + c["env"][2:]
svc = servicio("datos-privados", 8000)
svc["metadata"]["namespace"] = NSD
svc["spec"]["type"] = "LoadBalancer"
svc["metadata"]["annotations"] = {"nota": "Exponer solo por la red interna del centro de datos (balanceador interno) hacia el túnel VPN / enlace dedicado."}
dump(pri / "30-datos-privados.yaml", datos_dep, svc, {**pdb("datos-privados"), "metadata": {"name": "datos-privados", "namespace": NSD}})

dump(pri / "40-networkpolicies.yaml",
     {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "denegar-todo", "namespace": NSD}, "spec": {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}},
     {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "dns", "namespace": NSD},
      "spec": {"podSelector": {}, "policyTypes": ["Egress"], "egress": [{"to": [{"namespaceSelector": {}}], "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}]}]}},
     {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "datos-desde-nube-publica", "namespace": NSD},
      "spec": {"podSelector": {"matchLabels": {"app": "datos-privados"}}, "policyTypes": ["Ingress", "Egress"],
               "ingress": [{"from": [{"ipBlock": {"cidr": "10.10.0.0/16"}}], "ports": [{"port": 8000}]}],   # CIDR de la VPC de nube pública
               "egress": [{"to": [{"podSelector": {"matchLabels": {"app": "postgres"}}}], "ports": [{"port": 5432}]}]}},
     {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "respaldo-hacia-postgres-y-s3", "namespace": NSD},
      "spec": {"podSelector": {"matchLabels": {"app": "respaldo"}}, "policyTypes": ["Egress"],
               "egress": [{"to": [{"podSelector": {"matchLabels": {"app": "postgres"}}}], "ports": [{"port": 5432}]},
                          {"to": [{"ipBlock": {"cidr": "0.0.0.0/0", "except": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]}}],
                           "ports": [{"port": 443}]}]}},   # salida solo a los extremos de S3/KMS
     {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy", "metadata": {"name": "postgres-solo-desde-datos", "namespace": NSD},
      "spec": {"podSelector": {"matchLabels": {"app": "postgres"}}, "policyTypes": ["Ingress"],
               "ingress": [{"from": [{"podSelector": {"matchLabels": {"app": "datos-privados"}}}, {"podSelector": {"matchLabels": {"app": "respaldo"}}}], "ports": [{"port": 5432}]}]}})

# Respaldo en dos pasos: el initContainer vuelca y cifra en el disco local; el contenedor
# principal sube esa copia al bucket replicado. Sin la subida, perder el sitio sería perder
# los respaldos y el RPO de 15 min no se cumpliría.
VOLCADO = ("set -e; archivo=/respaldos/tramites_$(date -u +%Y%m%dT%H%M%SZ).sql.enc; "
           "pg_dump -h postgres -U tramites --no-owner --clean --if-exists tramites "
           "| openssl enc -aes-256-cbc -pbkdf2 -salt -pass env:BACKUP_PASSPHRASE -out \"$archivo\"; "
           "sha256sum \"$archivo\" > \"$archivo.sha256\"; "
           "echo -n \"$archivo\" > /respaldos/.ultimo; "
           "find /respaldos -name 'tramites_*.enc*' -mtime +14 -delete")
SUBIDA = ("set -e; archivo=$(cat /respaldos/.ultimo); "
          "aws s3 cp \"$archivo\" \"$BACKUP_S3_URI/$(basename \"$archivo\")\" --sse aws:kms --sse-kms-key-id \"$KMS_KEY_ARN\"; "
          "aws s3 cp \"$archivo.sha256\" \"$BACKUP_S3_URI/$(basename \"$archivo\").sha256\" --sse aws:kms --sse-kms-key-id \"$KMS_KEY_ARN\"; "
          "echo \"respaldo replicado: $(basename \"$archivo\")\"")
seg_respaldo = {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}}

dump(pri / "50-cronjob-respaldo.yaml",
     {"apiVersion": "v1", "kind": "PersistentVolumeClaim", "metadata": {"name": "respaldos", "namespace": NSD}, "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": "100Gi"}}}},
     {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": "respaldo", "namespace": NSD,
      "annotations": {"eks.amazonaws.com/role-arn": "REEMPLAZAR_ARN_ROL_RESPALDO",
                      "nota": "Rol IRSA con permiso de escritura solo sobre el bucket de respaldos (infra/terraform/main.tf)."}}},
     {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "respaldo-destino", "namespace": NSD},
      "data": {"BACKUP_S3_URI": "s3://REEMPLAZAR_BUCKET_RESPALDOS/postgres", "AWS_REGION": "sa-east-1",
               "KMS_KEY_ARN": "REEMPLAZAR_ARN_KMS"}},
     {"apiVersion": "batch/v1", "kind": "CronJob", "metadata": {"name": "respaldo-postgres", "namespace": NSD},
      "spec": {"schedule": "*/15 * * * *", "concurrencyPolicy": "Forbid", "successfulJobsHistoryLimit": 3, "failedJobsHistoryLimit": 5,
               "jobTemplate": {"spec": {"backoffLimit": 3, "template": {"metadata": {"labels": {"app": "respaldo"}}, "spec": {
                   "restartPolicy": "OnFailure", "serviceAccountName": "respaldo",
                   "securityContext": {"runAsNonRoot": True, "runAsUser": 70, "fsGroup": 70, "seccompProfile": {"type": "RuntimeDefault"}},
                   "initContainers": [{"name": "volcado", "image": "postgres:16-alpine", "command": ["sh", "-c", VOLCADO],
                                       "env": [{"name": "PGPASSWORD", **sec("POSTGRES_PASSWORD")}, {"name": "BACKUP_PASSPHRASE", **sec("BACKUP_PASSPHRASE")}],
                                       "securityContext": seg_respaldo,
                                       "volumeMounts": [{"name": "r", "mountPath": "/respaldos"}, {"name": "tmp", "mountPath": "/tmp"}]}],
                   "containers": [{"name": "subida", "image": "amazon/aws-cli:2.17.0", "command": ["sh", "-c", SUBIDA],
                                   "envFrom": [{"configMapRef": {"name": "respaldo-destino"}}],
                                   "securityContext": seg_respaldo,
                                   "volumeMounts": [{"name": "r", "mountPath": "/respaldos"}, {"name": "tmp", "mountPath": "/tmp"}]}],
                   "volumes": [{"name": "r", "persistentVolumeClaim": {"claimName": "respaldos"}}, {"name": "tmp", "emptyDir": {}}]}}}}}})
dump(pri / "kustomization.yaml", {"apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "namespace": NSD,
    "resources": sorted(p.name for p in pri.glob("*.yaml") if p.name != "kustomization.yaml"),
    "images": [{"name": "tramites/datos", "newName": "REGISTRO/tramites-datos", "newTag": "latest"}]})
print("Manifiestos generados en", RAIZ)
