locals {
  etiquetas = {
    proyecto    = var.proyecto
    clasificacion = "restringido"
    gestionado  = "terraform"
  }
}

data "aws_availability_zones" "disponibles" { state = "available" }

# ---------------------------------------------------------------- Claves de cifrado (KMS) con rotación
resource "aws_kms_key" "principal" {
  description             = "${var.proyecto}: cifrado de EBS, ECR y respaldos"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}
resource "aws_kms_alias" "principal" {
  name          = "alias/${var.proyecto}"
  target_key_id = aws_kms_key.principal.id
}
resource "aws_kms_key" "dr" {
  provider                = aws.dr
  description             = "${var.proyecto}: cifrado de la réplica de respaldos (DR)"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}

# ---------------------------------------------------------------- Red
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = "${var.proyecto}-vpc"
  cidr = var.vpc_cidr
  azs  = slice(data.aws_availability_zones.disponibles.names, 0, 3)

  private_subnets = [for i in range(3) : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i in range(3) : cidrsubnet(var.vpc_cidr, 8, 200 + i)]

  enable_nat_gateway   = true
  single_nat_gateway   = false
  enable_vpn_gateway   = true # puerta de enlace para la VPN hacia el centro de datos
  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_cloudwatch_iam_role  = true

  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }
  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
}

# ---------------------------------------------------------------- Clúster Kubernetes gestionado
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = "${var.proyecto}-eks"
  cluster_version = "1.31"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets

  cluster_endpoint_public_access           = false
  enable_cluster_creator_admin_permissions = true
  cluster_encryption_config                = { resources = ["secrets"], provider_key_arn = aws_kms_key.principal.arn }
  cluster_enabled_log_types                = ["api", "audit", "authenticator"]

  eks_managed_node_groups = {
    general = {
      instance_types = ["m6i.large"]
      min_size       = 3
      max_size       = 12
      desired_size   = 3
      block_device_mappings = {
        xvda = { device_name = "/dev/xvda", ebs = { volume_size = 50, volume_type = "gp3", encrypted = true, kms_key_id = aws_kms_key.principal.arn } }
      }
    }
  }
}

# ---------------------------------------------------------------- Registro de contenedores
resource "aws_ecr_repository" "servicio" {
  for_each             = toset(var.servicios)
  name                 = "${var.proyecto}-${each.key}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.principal.arn
  }
}

# ---------------------------------------------------------------- Respaldos con réplica en la región DR
resource "aws_s3_bucket" "respaldos" {
  bucket_prefix = "${var.proyecto}-respaldos-"
}
resource "aws_s3_bucket_versioning" "respaldos" {
  bucket = aws_s3_bucket.respaldos.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "respaldos" {
  bucket = aws_s3_bucket.respaldos.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.principal.arn
    }
  }
}
resource "aws_s3_bucket_public_access_block" "respaldos" {
  bucket                  = aws_s3_bucket.respaldos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "respaldos_dr" {
  provider      = aws.dr
  bucket_prefix = "${var.proyecto}-respaldos-dr-"
}
resource "aws_s3_bucket_versioning" "respaldos_dr" {
  provider = aws.dr
  bucket   = aws_s3_bucket.respaldos_dr.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "respaldos_dr" {
  provider = aws.dr
  bucket   = aws_s3_bucket.respaldos_dr.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.dr.arn
    }
  }
}
resource "aws_s3_bucket_public_access_block" "respaldos_dr" {
  provider                = aws.dr
  bucket                  = aws_s3_bucket.respaldos_dr.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_iam_policy_document" "replica_asume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }
  }
}
resource "aws_iam_role" "replica" {
  name               = "${var.proyecto}-replica-s3"
  assume_role_policy = data.aws_iam_policy_document.replica_asume.json
}
data "aws_iam_policy_document" "replica_permisos" {
  statement {
    actions   = ["s3:GetReplicationConfiguration", "s3:ListBucket"]
    resources = [aws_s3_bucket.respaldos.arn]
  }
  statement {
    actions   = ["s3:GetObjectVersionForReplication", "s3:GetObjectVersionAcl", "s3:GetObjectVersionTagging"]
    resources = ["${aws_s3_bucket.respaldos.arn}/*"]
  }
  statement {
    actions   = ["s3:ReplicateObject", "s3:ReplicateDelete", "s3:ReplicateTags"]
    resources = ["${aws_s3_bucket.respaldos_dr.arn}/*"]
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.principal.arn]
  }
  statement {
    actions   = ["kms:Encrypt"]
    resources = [aws_kms_key.dr.arn]
  }
}
resource "aws_iam_role_policy" "replica" {
  role   = aws_iam_role.replica.id
  policy = data.aws_iam_policy_document.replica_permisos.json
}
# ------------------------------------------- Rol para que el CronJob de respaldo escriba en S3
# El clúster del centro de datos asume este rol por OIDC (IRSA): no hay llaves de larga duración.
data "aws_iam_policy_document" "respaldo_confianza" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [module.eks.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${module.eks.oidc_provider}:sub"
      values   = ["system:serviceaccount:tramites-datos:respaldo"]
    }
  }
}
resource "aws_iam_role" "respaldo" {
  name               = "${var.proyecto}-respaldo-s3"
  assume_role_policy = data.aws_iam_policy_document.respaldo_confianza.json
  tags               = local.etiquetas
}
data "aws_iam_policy_document" "respaldo_permisos" {
  statement {                                   # solo subir, nunca borrar ni leer otros objetos
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.respaldos.arn}/postgres/*"]
  }
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.respaldos.arn]
  }
  statement {
    effect    = "Allow"
    actions   = ["kms:Encrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.principal.arn]
  }
}
resource "aws_iam_role_policy" "respaldo" {
  role   = aws_iam_role.respaldo.id
  policy = data.aws_iam_policy_document.respaldo_permisos.json
}

resource "aws_s3_bucket_lifecycle_configuration" "respaldos" {
  bucket = aws_s3_bucket.respaldos.id
  rule {
    id     = "retencion"
    status = "Enabled"
    filter { prefix = "postgres/" }
    noncurrent_version_expiration { noncurrent_days = 30 }
    expiration { days = var.retencion_respaldos_dias }
  }
}

resource "aws_s3_bucket_replication_configuration" "respaldos" {
  depends_on = [aws_s3_bucket_versioning.respaldos, aws_s3_bucket_versioning.respaldos_dr]
  role       = aws_iam_role.replica.arn
  bucket     = aws_s3_bucket.respaldos.id
  rule {
    id     = "replicar-a-dr"
    status = "Enabled"
    source_selection_criteria {
      sse_kms_encrypted_objects { status = "Enabled" }
    }
    destination {
      bucket        = aws_s3_bucket.respaldos_dr.arn
      storage_class = "STANDARD_IA"
      encryption_configuration { replica_kms_key_id = aws_kms_key.dr.arn }
    }
  }
}

# ---------------------------------------------------------------- Enlace híbrido: VPN site-to-site hacia el centro de datos
resource "aws_customer_gateway" "onprem" {
  bgp_asn    = 65000
  ip_address = var.onprem_ip_publica
  type       = "ipsec.1"
}
resource "aws_vpn_connection" "onprem" {
  vpn_gateway_id      = module.vpc.vgw_id
  customer_gateway_id = aws_customer_gateway.onprem.id
  type                = "ipsec.1"
  static_routes_only  = true
}
resource "aws_vpn_connection_route" "onprem" {
  vpn_connection_id      = aws_vpn_connection.onprem.id
  destination_cidr_block = var.onprem_cidr
}
# El enlace dedicado (Direct Connect o equivalente del operador) se contrata aparte y reemplaza a la VPN como ruta primaria.

# ---------------------------------------------------------------- WAF regional (se asocia al balanceador desde el Ingress)
resource "aws_wafv2_web_acl" "portal" {
  name  = "${var.proyecto}-portal"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.proyecto}-waf"
    sampled_requests_enabled   = true
  }

  rule {
    name     = "limite-por-ip"
    priority = 1
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "limite-por-ip"
      sampled_requests_enabled   = true
    }
  }

  dynamic "rule" {
    for_each = { "AWSManagedRulesCommonRuleSet" = 2, "AWSManagedRulesKnownBadInputsRuleSet" = 3, "AWSManagedRulesAmazonIpReputationList" = 4 }
    content {
      name     = rule.key
      priority = rule.value
      override_action {
        none {}
      }
      statement {
        managed_rule_group_statement {
          name        = rule.key
          vendor_name = "AWS"
        }
      }
      visibility_config {
        cloudwatch_metrics_enabled = true
        metric_name                = rule.key
        sampled_requests_enabled   = true
      }
    }
  }
}

# ---------------------------------------------------------------- DNS con conmutación por error (failover)
data "aws_route53_zone" "zona" {
  count = var.dominio == "" ? 0 : 1
  name  = var.dominio
}
resource "aws_route53_health_check" "principal" {
  count             = var.dominio == "" || var.alb_principal_dns == "" ? 0 : 1
  fqdn              = var.alb_principal_dns
  port              = 443
  type              = "HTTPS"
  resource_path     = "/healthz"
  failure_threshold = 3
  request_interval  = 10
}
resource "aws_route53_record" "primario" {
  count           = var.dominio == "" || var.alb_principal_dns == "" ? 0 : 1
  zone_id         = data.aws_route53_zone.zona[0].zone_id
  name            = "tramites.${var.dominio}"
  type            = "CNAME"
  ttl             = 30
  records         = [var.alb_principal_dns]
  set_identifier  = "primario"
  health_check_id = aws_route53_health_check.principal[0].id
  failover_routing_policy { type = "PRIMARY" }
}
resource "aws_route53_record" "secundario" {
  count          = var.dominio == "" || var.alb_dr_dns == "" ? 0 : 1
  zone_id        = data.aws_route53_zone.zona[0].zone_id
  name           = "tramites.${var.dominio}"
  type           = "CNAME"
  ttl            = 30
  records        = [var.alb_dr_dns]
  set_identifier = "secundario"
  failover_routing_policy { type = "SECONDARY" }
}
