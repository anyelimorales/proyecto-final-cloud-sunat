terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
}

provider "aws" {
  region = var.region_principal
  default_tags { tags = local.etiquetas }
}

# Región de recuperación ante desastres (réplica de respaldos y de la imagen de contenedores)
provider "aws" {
  alias  = "dr"
  region = var.region_dr
  default_tags { tags = local.etiquetas }
}
