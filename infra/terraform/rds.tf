# infra/terraform/rds.tf
module "aurora" {
  source  = "terraform-aws-modules/rds-aurora/aws"
  
  name           = "${var.cluster_name}-postgres"
  engine         = "aurora-postgresql"
  instance_class = "db.serverless" 
  
  instances = {
    one = {}
    two = {} # HA Multi-AZ
  }

serverlessv2_scaling_configuration = {
    min_capacity = 2
    max_capacity = 64
  }
  vpc_id               = module.vpc.vpc_id
  db_subnet_group_name = module.vpc.database_subnet_group_name
  
  # Only allow traffic from within the VPC
  security_group_rules = {
    vpc_ingress = { cidr_blocks = [module.vpc.vpc_cidr_block] }
  }
}
