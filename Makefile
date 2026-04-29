# On-demand AI context helpers.
# Run after model changes — not required before every edit.

PYTHON   := python3
OUT      := docs/ai_context
SCRIPT   := .claude/skills/ai_context/scripts/generate_relationships.py

.PHONY: ai-context install-hooks clean

ai-context: $(OUT)
	$(PYTHON) $(SCRIPT) > $(OUT)/sqlalchemy_relationships.md
	@echo "Refreshed $(OUT)/sqlalchemy_relationships.md"

# Wire up a git pre-commit hook so the relationship map never goes stale.
# Run once: make install-hooks
install-hooks:
	@mkdir -p .git/hooks
	@printf '#!/bin/sh\nmake ai-context\ngit add $(OUT)/sqlalchemy_relationships.md\n' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "Pre-commit hook installed — relationship map will auto-refresh on every commit"

$(OUT):
	mkdir -p $(OUT)

clean:
	rm -rf $(OUT)
