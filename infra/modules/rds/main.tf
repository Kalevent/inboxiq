resource "aws_db_instance" "inboxiq" {
  identifier        = "inboxiq-db-encrypted"
  engine            = "postgres"
  engine_version    = "18.3"
  instance_class    = var.instance_class
  allocated_storage = 20
  storage_type      = "gp2"
  storage_encrypted = true
  # TODO(eu-west-2-migration): replace with new KMS key ARN after running Step 1 of migration runbook
  # Command: aws kms create-key --description "RDS encryption key" --region eu-west-2
  kms_key_id        = "arn:aws:kms:eu-west-2:094985084741:key/fc876e24-fdfa-4719-aba7-1f259163f382"
  multi_az          = false

  db_name  = "inboxiq"
  username = "inboxiqapp"   # Actual username in production — do not change
  password = var.db_password

  db_subnet_group_name   = var.db_subnet_group_name
  vpc_security_group_ids = var.security_group_ids

  max_allocated_storage     = 100  # Autogrow up to 100Gi — prevents "no space" outages

  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "inboxiq-db-encrypted-final"

  tags = { Name = "inboxiq-db-encrypted" }

  lifecycle {
    # Prevent accidental replacement — password changes are allowed but not applied in-place
    ignore_changes  = [password, engine_version]
    prevent_destroy = true
  }
}
