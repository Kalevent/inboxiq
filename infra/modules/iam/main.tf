# ── Node instance role ──────────────────────────────────────
# Managed by eksctl — imported into Terraform for visibility and policy management.
# Do NOT delete or recreate — would break the EKS node group.

data "aws_iam_role" "node_instance" {
  name = "eksctl-inboxiq-eks-nodegroup-inbox-NodeInstanceRole-qJMYbgghTryP"
}

data "aws_iam_role" "cluster_service" {
  name = "eksctl-inboxiq-eks-cluster-ServiceRole-KWR8poR2DacO"
}

data "aws_iam_role" "ebs_csi_irsa" {
  name = "eksctl-inboxiq-eks-addon-iamserviceaccount-ku-Role1-qnY61JPaj1hr"
}

# ── S3 upload policy (attached to node instance role) ───────
resource "aws_iam_role_policy" "node_s3_uploads" {
  name = "S3-kalevent-uploads"
  role = data.aws_iam_role.node_instance.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:HeadObject"]
        Resource = "arn:aws:s3:::kalevent-uploads/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = "arn:aws:s3:::kalevent-uploads"
      }
    ]
  })
}

# ── Cluster Autoscaler policy ────────────────────────────────
resource "aws_iam_policy" "cluster_autoscaler" {
  name        = "inboxiq-cluster-autoscaler"
  description = "Allows Cluster Autoscaler to scale EKS node group"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "autoscaling:DescribeAutoScalingGroups",
          "autoscaling:DescribeAutoScalingInstances",
          "autoscaling:DescribeLaunchConfigurations",
          "autoscaling:DescribeScalingActivities",
          "autoscaling:DescribeTags",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeLaunchTemplateVersions",
          "eks:DescribeNodegroup"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:TerminateInstanceInAutoScalingGroup"
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/enabled"     = "true"
            "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/inboxiq-eks" = "owned"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "cluster_autoscaler" {
  role       = data.aws_iam_role.node_instance.name
  policy_arn = aws_iam_policy.cluster_autoscaler.arn
}

# ── SES send email policy ────────────────────────────────────
resource "aws_iam_role_policy" "node_ses" {
  name = "SES-SendEmail-kalevent"
  role = data.aws_iam_role.node_instance.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "*"
        Condition = {
          StringLike = {
            "ses:FromAddress" = "*@kalevent.com"
          }
        }
      }
    ]
  })
}
