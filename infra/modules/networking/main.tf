resource "aws_vpc" "main" {
  cidr_block           = "192.168.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/VPC" }
}

resource "aws_subnet" "public_2a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "192.168.32.0/19"
  availability_zone       = "us-west-2a"
  map_public_ip_on_launch = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPublicUSWEST2A" }
}

resource "aws_subnet" "public_2c" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "192.168.0.0/19"
  availability_zone       = "us-west-2c"
  map_public_ip_on_launch = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPublicUSWEST2C" }
}

resource "aws_subnet" "public_2d" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "192.168.64.0/19"
  availability_zone       = "us-west-2d"
  map_public_ip_on_launch = true
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPublicUSWEST2D" }
}

resource "aws_subnet" "private_2a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "192.168.128.0/19"
  availability_zone = "us-west-2a"
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPrivateUSWEST2A" }
}

resource "aws_subnet" "private_2c" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "192.168.96.0/19"
  availability_zone = "us-west-2c"
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPrivateUSWEST2C" }
}

resource "aws_subnet" "private_2d" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "192.168.160.0/19"
  availability_zone = "us-west-2d"
  tags = { Name = "eksctl-inboxiq-eks-cluster/SubnetPrivateUSWEST2D" }
}

resource "aws_db_subnet_group" "inboxiq" {
  name       = "inboxiq-subnets"
  subnet_ids = [
    aws_subnet.private_2a.id,
    aws_subnet.private_2c.id,
    aws_subnet.private_2d.id,
  ]
  tags = { Name = "inboxiq-subnets" }
}
