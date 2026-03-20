variable "instance_class" {
  default = "db.t4g.micro"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "db_subnet_group_name" {
  type = string
}

variable "security_group_ids" {
  type = list(string)
}
