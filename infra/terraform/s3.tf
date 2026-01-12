# infra/terraform/s3.tf
resource "aws_s3_bucket" "documents" {
  bucket = "rag-platform-documents-prod"
}

resource "aws_s3_bucket_accelerate_configuration" "docs_accel" {
  bucket = aws_s3_bucket.documents.id
  status = "Enabled"
}

resource "aws_s3_bucket_lifecycle_configuration" "docs_lifecycle" {
  bucket = aws_s3_bucket.documents.id
  rule {
    id     = "archive-old-files"
    status = "Enabled"
    transition {
      days          = 30
      storage_class = "INTELLIGENT_TIERING" # Auto-optimizes cost
    }
  }
}