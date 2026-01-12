# infra/terraform/outputs.tf
output "aurora_db_endpoint" {
  value = module.aurora.cluster_endpoint
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}
output "s3_bucket_name" {
  value = aws_s3_bucket.documents.id
}