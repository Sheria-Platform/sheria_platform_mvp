# infra/terraform/variables.tf
variable "aws_region" {
  description = "AWS region to deploy resources"
  default     = "us-east-1" # N. Virginia has the best GPU availability
}

variable "cluster_name" {
  description = "Name of the EKS Cluster"
  default     = "rag-platform-cluster"
}
variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  default     = "10.0.0.0/16"
}