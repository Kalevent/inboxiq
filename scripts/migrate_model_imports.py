#!/usr/bin/env python3
"""
Migrate `from src.models import X` to `from src.models.<domain> import X`.
Also fixes `from src.models import db` → `from src.extensions import db`.

Usage:
    python scripts/migrate_model_imports.py --dry-run   # preview changes
    python scripts/migrate_model_imports.py             # apply changes
"""
import re
import sys
from pathlib import Path
from collections import defaultdict

SRC = Path(__file__).parent.parent / "src"

CLASS_TO_DOMAIN = {
    # core.py
    "Account": "core",
    "User": "core",
    "InboxConnection": "core",
    "AccountFeatureFlags": "core",
    # auth.py
    "AuthEvent": "auth",
    "Passkey": "auth",
    "TOTPDevice": "auth",
    # tickets.py
    "Ticket": "tickets",
    "TicketEmbedding": "tickets",
    "TriageLabelConfig": "tickets",
    "DraftReplyFeedback": "tickets",
    "TriageConfig": "tickets",
    # ai.py
    "DspyTrainingMetric": "ai",
    "AgentEvent": "ai",
    "AgentModel": "ai",
    "MCPServerCatalog": "ai",
    # leads.py
    "Lead": "leads",
    "LeadFunnelStage": "leads",
    "LeadEngagementEvent": "leads",
    "LeadAttribution": "leads",
    "FunnelMetricsDaily": "leads",
    # content.py
    "BlogPost": "content",
    "KBIntegration": "content",
    "KBArticle": "content",
    "KBArticleEmbedding": "content",
    "GeneratedContent": "content",
    "PitchedBlogTopic": "content",
    # campaigns.py
    "CampaignSender": "campaigns",
    "HunterDomainCache": "campaigns",
    "EmailCampaign": "campaigns",
    "EmailOutreach": "campaigns",
    "NurtureEmailSend": "campaigns",
    # automation.py
    "AutomationStudioWaitlist": "automation",
    "AutomationRule": "automation",
    "AutomationRuleExecution": "automation",
    "WebhookProvider": "automation",
    "AutomationSuggestion": "automation",
    # marketing.py
    "Referral": "marketing",
    "InAppMessage": "marketing",
    "InAppMessageDismissal": "marketing",
    "LandingPage": "marketing",
    "MarketingSpend": "marketing",
    "EnterpriseInquiry": "marketing",
    # misc.py
    "Testimonial": "misc",
    "Feedback": "misc",
    # developer.py
    "DeveloperAccessRequest": "developer",
    "RegisteredApp": "developer",
}

# Match single-line: from src.models import Foo, Bar  [# optional comment]
IMPORT_PATTERN = re.compile(
    r'^(from src\.models import )([^\n]+)$',
    re.MULTILINE,
)


def parse_names(names_str: str) -> tuple[list[str], str]:
    """Split 'Foo, Bar  # comment' into (['Foo', 'Bar'], '# comment')."""
    comment = ""
    if "#" in names_str:
        idx = names_str.index("#")
        comment = names_str[idx:].strip()
        names_str = names_str[:idx]
    names = [n.strip().rstrip(",") for n in names_str.split(",")]
    names = [n for n in names if n]
    return names, comment


def process_file(path: Path, dry_run: bool) -> bool:
    text = path.read_text()
    matches = list(IMPORT_PATTERN.finditer(text))
    if not matches:
        return False

    already_has_extensions_db = bool(
        re.search(r"from src\.extensions import[^\n]*\bdb\b", text)
    )

    new_text = text
    offset = 0  # cumulative offset after replacements
    changed = False

    for match in matches:
        names, comment = parse_names(match.group(2))
        has_db = "db" in names
        model_names = [n for n in names if n != "db"]

        by_domain: dict[str, list[str]] = defaultdict(list)
        unknown: list[str] = []
        for name in model_names:
            domain = CLASS_TO_DOMAIN.get(name)
            if domain:
                by_domain[domain].append(name)
            else:
                unknown.append(name)

        if unknown:
            print(f"  SKIP {path.relative_to(SRC.parent)}: unknown class(es): {unknown}")
            continue

        # Build replacement lines
        new_lines = []
        for domain in sorted(by_domain.keys()):
            classes = sorted(by_domain[domain], key=lambda c: model_names.index(c))
            new_lines.append(f"from src.models.{domain} import {', '.join(classes)}")

        if has_db and not already_has_extensions_db:
            new_lines.append("from src.extensions import db")
            already_has_extensions_db = True  # don't add again on later matches

        # Preserve trailing comment.
        # noqa comments must go on every line; regular comments go on the last.
        if comment:
            if "noqa" in comment:
                new_lines = [f"{line}  {comment}" for line in new_lines]
            elif new_lines:
                new_lines[-1] = f"{new_lines[-1]}  {comment}"

        replacement = "\n".join(new_lines)
        original = match.group(0)

        rel = path.relative_to(SRC.parent)
        print(f"  {rel}")
        print(f"    - {original}")
        for line in new_lines:
            print(f"    + {line}")

        if dry_run:
            changed = True  # count for summary
        else:
            start = match.start() + offset
            end = match.end() + offset
            new_text = new_text[:start] + replacement + new_text[end:]
            offset += len(replacement) - len(original)
            changed = True

    if changed and not dry_run:
        path.write_text(new_text)

    return changed


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no files will be modified\n")

    changed_files = 0
    for py_file in sorted(SRC.rglob("*.py")):
        if process_file(py_file, dry_run=dry_run):
            changed_files += 1

    print(f"\n{'Would update' if dry_run else 'Updated'} {changed_files} file(s)")


if __name__ == "__main__":
    main()
