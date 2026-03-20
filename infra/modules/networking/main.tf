resource "aws_vpc" "main" {
  cidr_block           = "192.168.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/VPC" }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_subnet" "public_2a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "192.168.32.0/19"
  availability_zone       = "us-west-2a"
  map_public_ip_on_launch = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPublicUSWEST2A" }

  lifecycle {
    ignore_changes = [tags]   # ALB controller adds kubernetes.io/role/elb — do not remove
  }
}

resource "aws_subnet" "public_2c" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "192.168.0.0/19"
  availability_zone       = "us-west-2c"
  map_public_ip_on_launch = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPublicUSWEST2C" }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_subnet" "public_2d" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "192.168.64.0/19"
  availability_zone       = "us-west-2d"
  map_public_ip_on_launch = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPublicUSWEST2D" }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_subnet" "private_2a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "192.168.128.0/19"
  availability_zone = "us-west-2a"
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPrivateUSWEST2A" }

  lifecycle {
    ignore_changes = [tags]   # ALB controller adds kubernetes.io/role/internal-elb
  }
}

resource "aws_subnet" "private_2c" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "192.168.96.0/19"
  availability_zone = "us-west-2c"
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPrivateUSWEST2C" }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_subnet" "private_2d" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "192.168.160.0/19"
  availability_zone = "us-west-2d"
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPrivateUSWEST2D" }

  lifecycle {
    ignore_changes = [tags]
  }
}

resource "aws_db_subnet_group" "inboxiq" {
  name        = "inboxiq-subnets"
  description = "InboxIQ DB"
  subnet_ids = [
    aws_subnet.private_2a.id,
    aws_subnet.private_2c.id,
    aws_subnet.private_2d.id,
  ]
  tags = { Name = "inboxiq-subnets" }
}
