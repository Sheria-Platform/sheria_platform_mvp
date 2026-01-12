# infra/terraform/iam.tf
resource "aws_iam_policy" "ingestion_policy" {
  name        = "RAG_Ingestion_S3_Policy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Effect   = "Allow"
        Resource = [aws_s3_bucket.documents.arn, "${aws_s3_bucket.documents.arn}/*"]
      }
    ]
  })
}

module "ingestion_irsa_role" {
  source    = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-account-eks"
  role_name = "rag-ingestion-role"
  
  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["default:ray-worker"]
    }
  }
  role_policy_arns = { policy = aws_iam_policy.ingestion_policy.arn }
}
