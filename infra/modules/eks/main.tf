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
    ignore_changes = [
      bootstrap_self_managed_addons,
      access_config,
      kubernetes_network_config,
      upgrade_policy,
      tags,
    ]
  }
}

# m5.xlarge nodes: 4 vCPU / 16Gi RAM
# Replaced t3.medium (2 vCPU / 4Gi) — small nodes OOM-killed under memory pressure.
# Launch template applies kubelet eviction thresholds so pods are evicted gracefully
# before the OS OOM killer can take out the kubelet.
resource "aws_eks_node_group" "xlarge" {
  cluster_name    = aws_eks_cluster.inboxiq.name
  node_group_name = "inboxiq-ng-xlarge"
  node_role_arn   = var.node_role_arn
  subnet_ids      = var.public_subnet_ids
  instance_types  = ["m5.xlarge"]

  scaling_config {
    desired_size = var.node_desired
    min_size     = var.node_min
    max_size     = var.node_max
  }

  update_config {
    max_unavailable = 1
  }

  tags = {
    Name                                              = "inboxiq-ng-xlarge"
    "k8s.io/cluster-autoscaler/enabled"               = "true"
    "k8s.io/cluster-autoscaler/inboxiq-eks"           = "owned"
  }

  lifecycle {
    create_before_destroy = true
    ignore_changes = [
      labels,
      tags,
      release_version,
      launch_template,  # managed by eksctl; kubelet eviction config applied via AWS CLI (lt-0c6bf935b42f2676a v2)
    ]
  }
}
