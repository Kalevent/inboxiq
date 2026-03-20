PROD_DIR := environments/production
TF      := terraform -chdir=$(PROD_DIR)

# Prompt for password if not already set
ifndef TF_VAR_db_password
  export TF_VAR_db_password := $(shell read -sp "RDS password: " pw && echo $$pw)
endif

.PHONY: init plan apply destroy unlock import

init:
	$(TF) init

plan:
	$(TF) plan

apply:
	$(TF) apply

apply-auto:
	$(TF) apply -auto-approve

destroy:
	@echo "⚠️  This will destroy production infrastructure. Are you sure? [yes/N]"; \
	read ans; [ "$$ans" = "yes" ] || (echo "Aborted."; exit 1)
	$(TF) destroy

unlock:
	@LOCK_ID=$$($(TF) force-unlock -force 2>&1 | grep -oE '[a-f0-9-]{36}' | head -1); \
	$(TF) force-unlock -force $$LOCK_ID

import:
	bash scripts/import.sh
