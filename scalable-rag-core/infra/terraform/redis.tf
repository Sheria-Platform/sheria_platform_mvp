# infra/terraform/redis.tf
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "rag-redis-prod"
  description          = "Redis for RAG Semantic Cache"
  node_type            = "cache.t4g.medium"
  num_cache_clusters   = 2 # Primary + Replica
  port                 = 6379
  
  subnet_group_name    = aws_elasticache_subnet_group.redis_subnet.name
  security_group_ids   = [aws_security_group.redis_sg.id]
  
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}