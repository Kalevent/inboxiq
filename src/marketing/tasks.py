"""
Marketing Celery tasks — entry point for autodiscover_tasks.

Celery's autodiscover_tasks() looks for a tasks.py in each registered package.
This file imports from all marketing sub-modules so their @celery.task decorators
register with the Celery app when the worker starts.
"""
# noqa: F401  (imports are side-effect only — they register tasks)
