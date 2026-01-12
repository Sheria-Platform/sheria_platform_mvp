# infra/terraform/main.tf
terraform {
  required_version = ">= 1.5.0"
  
  backend "s3" {
    bucket         = "rag-platform-terraform-state-prod-001"
    key            = "platform/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }

required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.23" }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = { Project = "Enterprise-RAG", ManagedBy = "Terraform" }
  }
}