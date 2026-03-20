resource "aws_db_instance" "inboxiq" {
  identifier        = "inboxiq-db"
  engine            = "postgres"
  engine_version    = "18.1"
  instance_class    = var.instance_class
  allocated_storage = 20
  storage_type      = "gp2"
  storage_encrypted = true
  multi_az          = false

  db_name  = "inboxiq"
  username = "inboxiq"
  password = var.db_password   # Pass from secrets manager in CI — never hardcode

  db_subnet_group_name   = var.db_subnet_group_name
  vpc_security_group_ids = var.security_group_ids

  backup_retention_period   = 7
  deletion_protection       = true   # Must be disabled manually before destroy
  skip_final_snapshot       = false
  final_snapshot_identifier = "inboxiq-db-final"

  tags = { Name = "inboxiq-db" }
}
