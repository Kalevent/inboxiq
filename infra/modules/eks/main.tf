resource "aws_eks_cluster" "inboxiq" {
  name     = "inboxiq-eks"
  version  = "1.34"
  role_arn = var.cluster_role_arn

  vpc_config {
    subnet_ids              = concat(var.public_subnet_ids, var.private_subnet_ids)
    endpoint_public_access  = true
    endpoint_private_access = true
  }

  tags = { Name = "inboxiq-eks" }

  lifecycle {
    # Prevent replacement — eksctl manages bootstrap settings and tags we don't own
    ignore_changes = [
      bootstrap_self_managed_addons,
      access_config,
      kubernetes_network_config,
      upgrade_policy,
      tags,
    ]
  }
}

# Nodes run in public subnets (eksctl default) with private IPs via security groups
resource "aws_eks_node_group" "medium" {
  cluster_name    = aws_eks_cluster.inboxiq.name
  node_group_name = "inboxiq-ng-medium"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.public_subnet_ids
  instance_types  = ["t3.medium"]

  scaling_config {
    desired_size = var.node_desired
    min_size     = var.node_min
    max_size     = var.node_max
  }

  update_config {
    max_unavailable = 1
  }

  tags = {
    Name                                              = "inboxiq-ng-medium"
    "k8s.io/cluster-autoscaler/enabled"               = "true"
    "k8s.io/cluster-autoscaler/inboxiq-eks"           = "owned"
  }

  lifecycle {
    # Prevent replacement — eksctl manages launch template and labels we don't own
    ignore_changes = [
      launch_template,
      labels,
      tags,
      release_version,
    ]
  }
}
