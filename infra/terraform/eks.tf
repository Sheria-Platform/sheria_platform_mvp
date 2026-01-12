# infra/terraform/eks.tf
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 19.0"

cluster_name    = var.cluster_name
  cluster_version = "1.29"
  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets
  enable_irsa = true

  # We only define a minimal system node group here.
  # Application scaling is handled by Karpenter later.
  eks_managed_node_groups = {
    system = {
      name           = "system-nodes"
      instance_types = ["m6i.large"]
      min_size       = 2
      max_size       = 5
      desired_size   = 2
    }
  }
}