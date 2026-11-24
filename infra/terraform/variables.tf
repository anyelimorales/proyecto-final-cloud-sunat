variable "proyecto" {
  type    = string
  default = "tramites"
}
variable "region_principal" {
  type    = string
  default = "sa-east-1" # São Paulo: región sudamericana más cercana; validar disponibilidad de servicios y residencia de datos
}
variable "region_dr" {
  type    = string
  default = "us-east-1"
}
variable "vpc_cidr" {
  type    = string
  default = "10.10.0.0/16"
}
variable "servicios" {
  type    = list(string)
  default = ["auth", "ruc", "rhe", "declaraciones", "alertas", "simulador", "fraccionamiento", "pagos", "documentos", "portal", "datos"]
}
variable "onprem_cidr" {
  description = "CIDR del centro de datos de la entidad (nube privada)"
  type        = string
  default     = "10.20.0.0/24"
}
variable "onprem_ip_publica" {
  description = "IP pública del equipo VPN del centro de datos"
  type        = string
  default     = "203.0.113.10" # IP de documentación; reemplazar
}
variable "dominio" {
  description = "Zona alojada en Route 53 (vacío = no crear registros DNS)"
  type        = string
  default     = ""
}
variable "alb_principal_dns" {
  type    = string
  default = ""
}
variable "alb_dr_dns" {
  type    = string
  default = ""
}
variable "retencion_respaldos_dias" {
  description = "Días que se conservan los respaldos en el bucket principal"
  type        = number
  default     = 35
}
