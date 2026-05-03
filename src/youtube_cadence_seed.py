"""
Seed ICP pain points for the YouTube cadence.

Run once after the icp_pain_points migration:
  flask shell -c "from src.youtube_cadence_seed import seed; seed(account_id=2)"

Or from the project root:
  FLASK_APP=src/app.py flask shell
  >>> from src.youtube_cadence_seed import seed; seed(account_id=2)
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PAIN_POINTS = [
    {
        "priority": 10,
        "pain_point": "Support emails pile up unread over the weekend",
        "consequence": "Customers churn before Monday",
        "persona": "Head of Support",
    },
    {
        "priority": 9,
        "pain_point": "No way to tell which leads are warm vs cold",
        "consequence": "Sales team chases the wrong people",
        "persona": "Head of Sales",
    },
    {
        "priority": 8,
        "pain_point": "Outreach is manual — copy/paste, one by one",
        "consequence": "Hours wasted, inconsistent follow-up",
        "persona": "Operations Lead",
    },
    {
        "priority": 7,
        "pain_point": "Reply comes in, nobody sees it in time",
        "consequence": "Deal goes cold, prospect moves on",
        "persona": "Founder",
    },
    {
        "priority": 6,
        "pain_point": "No visibility into which channel drives signups",
        "consequence": "Budget spent blind",
        "persona": "Founder",
    },
    {
        "priority": 5,
        "pain_point": "Support team scales by hiring, not by tooling",
        "consequence": "Margins shrink as you grow",
        "persona": "Head of Support",
    },
]


def seed(account_id: int) -> None:
    from src.extensions import db
    from src.models.leads import ICPPainPoint
    from src.models.marketing import ICPConfig

    icp_config = ICPConfig.query.filter_by(account_id=account_id).first()
    if not icp_config:
        raise RuntimeError(
            f"No ICPConfig found for account_id={account_id}. "
            "Create an ICP config first via the settings UI."
        )

    inserted = 0
    skipped = 0

    for row in PAIN_POINTS:
        existing = ICPPainPoint.query.filter_by(
            account_id=account_id,
            pain_point=row["pain_point"],
        ).first()
        if existing:
            skipped += 1
            continue

        pain_point = ICPPainPoint(
            account_id=account_id,
            icp_config_id=icp_config.id,
            pain_point=row["pain_point"],
            consequence=row["consequence"],
            persona=row["persona"],
            priority=row["priority"],
            active=True,
        )
        db.session.add(pain_point)
        inserted += 1

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    logger.info("YouTube cadence seed: inserted=%d skipped=%d account=%d", inserted, skipped, account_id)
    print(f"Seeded {inserted} pain points ({skipped} already existed) for account_id={account_id}.")
