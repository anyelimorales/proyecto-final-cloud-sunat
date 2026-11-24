output "cluster_eks" { value = module.eks.cluster_name }
output "repositorios_ecr" { value = { for k, r in aws_ecr_repository.servicio : k => r.repository_url } }
output "bucket_respaldos" { value = aws_s3_bucket.respaldos.bucket }
output "bucket_respaldos_dr" { value = aws_s3_bucket.respaldos_dr.bucket }
output "waf_acl_arn" { value = aws_wafv2_web_acl.portal.arn }
output "vpn_tunel_1" {
  value     = aws_vpn_connection.onprem.tunnel1_address
  sensitive = false
}
output "rol_respaldo_arn" {
  description = "Anotar en la ServiceAccount 'respaldo' de k8s/onprem/50-cronjob-respaldo.yaml"
  value       = aws_iam_role.respaldo.arn
}
output "kms_principal_arn" { value = aws_kms_key.principal.arn }
