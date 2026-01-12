# infra/terraform/neo4j.tf
resource "aws_security_group" "neo4j_sg" {
  name        = "neo4j-access-sg"
  vpc_id      = module.vpc.vpc_id

ingress {
    description = "Internal Bolt Protocol"
    from_port   = 7687
    to_port     = 7687
    protocol    = "tcp"
    cidr_blocks = [module.vpc.vpc_cidr_block]
  }
}