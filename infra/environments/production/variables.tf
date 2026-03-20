variable "db_password" {
  description = "RDS master password — pass via TF_VAR_db_password env var, never in tfvars"
  type        = string
  sensitive   = true
}
