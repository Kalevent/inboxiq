output "cluster_name"     { value = aws_eks_cluster.inboxiq.name }
output "cluster_endpoint" { value = aws_eks_cluster.inboxiq.endpoint }
output "cluster_ca"       { value = aws_eks_cluster.inboxiq.certificate_authority[0].data }
