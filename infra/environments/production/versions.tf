terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  backend "s3" {
    bucket         = "kalevent-terraform-state"
    key            = "inboxiq/production/terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = "us-west-2"

  # Safety: only operate on InboxIQ account, never policynumbers account
  allowed_account_ids = ["094985084741"]
}
