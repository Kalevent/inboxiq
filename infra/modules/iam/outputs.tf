output "node_instance_role_arn"  { value = data.aws_iam_role.node_instance.arn }
output "cluster_service_role_arn" { value = data.aws_iam_role.cluster_service.arn }
output "ebs_csi_role_arn"        { value = data.aws_iam_role.ebs_csi_irsa.arn }
