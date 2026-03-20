resource "aws_eks_cluster" "inboxiq" {
  name     = "inboxiq-eks"
  version  = "1.34"
  role_arn = var.cluster_role_arn

  vpc_config {
    subnet_ids                = concat(var.public_subnet_ids, var.private_subnet_ids)
    cluster_security_group_id = var.cluster_security_group_id
    endpoint_public_access    = true
    endpoint_private_access   = true
  }

  tags = { Name = "inboxiq-eks" }
}

resource "aws_eks_node_group" "medium" {
  cluster_name    = aws_eks_cluster.inboxiq.name
  node_group_name = "inboxiq-ng-medium"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = ["t3.medium"]

  scaling_config {
    desired_size = var.node_desired
    min_size     = var.node_min
    max_size     = var.node_max
  }

  update_config {
    max_unavailable = 1
  }

  tags = { Name = "inboxiq-ng-medium" }
}
