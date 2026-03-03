"""
Marketing Celery tasks — entry point for autodiscover_tasks.

Celery's autodiscover_tasks() looks for a tasks.py in each registered package.
This file imports from all marketing sub-modules so their @celery.task decorators
register with the Celery app when the worker starts.
"""
# noqa: F401  (imports are side-effect only — they register tasks)
from src.marketing.nurture_campaigns import (
    send_discovery_nurture,
    send_consideration_nurture,
)
from src.marketing.content_distribution import (
    auto_publish_ready_posts,
    publish_blog_post,
    distribute_to_social,
    send_blog_newsletter,
    submit_to_search_engines,
)
from src.marketing.crm_social_sync import sync_social_crm_leads
from src.marketing.ab_testing import evaluate_nurture_ab_tests
from src.marketing.behavior_triggers import check_behavior_triggers
from src.marketing.monthly_reports import send_enterprise_value_reports
