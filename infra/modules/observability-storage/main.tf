resource "aws_security_group" "efs" {
  name_prefix = "inboxiq-observability-efs-"
  description = "Allow NFS access to observability EFS from InboxIQ VPC"
  vpc_id      = var.vpc_id

  ingress {
    description = "NFS from InboxIQ VPC"
    from_port   = 2049
    to_port     = 2049
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "inboxiq-observability-efs"
  }
}

resource "aws_efs_file_system" "observability" {
  creation_token  = "inboxiq-observability"
  encrypted       = true
  throughput_mode = "elastic"

  lifecycle_policy {
    transition_to_ia = "AFTER_30_DAYS"
  }

  tags = {
    Name = "inboxiq-observability"
  }
}

resource "aws_efs_mount_target" "observability" {
  for_each = toset(var.private_subnet_ids)

  file_system_id  = aws_efs_file_system.observability.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}
