output "vpc_id"              { value = aws_vpc.main.id }
output "public_subnet_ids"   { value = [aws_subnet.public_2a.id, aws_subnet.public_2c.id, aws_subnet.public_2d.id] }
output "private_subnet_ids"  { value = [aws_subnet.private_2a.id, aws_subnet.private_2c.id, aws_subnet.private_2d.id] }
output "db_subnet_group_name" { value = aws_db_subnet_group.inboxiq.name }
