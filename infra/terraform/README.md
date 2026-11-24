# Infraestructura como código (referencia)

Describe la nube pública (AWS) de la arquitectura híbrida: red, clúster Kubernetes, registro de contenedores,
claves KMS, respaldos replicados a la región de recuperación, VPN hacia el centro de datos, WAF y DNS con failover.

> **Estado:** código de referencia para el informe. **No se ha ejecutado `terraform plan/apply`** en este entorno
> (sin credenciales de nube). Antes de aplicar: `terraform init && terraform validate && terraform plan`,
> revisar versiones de módulos y la disponibilidad de servicios en la región elegida.

Uso: `terraform init && terraform plan -var onprem_ip_publica=<IP> -var dominio=<zona>`
Costo: los recursos con cobro continuo son NAT Gateways, nodos EKS, VPN, WAF y almacenamiento replicado.
