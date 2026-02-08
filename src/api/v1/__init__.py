from flask import Blueprint

v1 = Blueprint('v1', __name__)

# Import v1 modules to register routes
from src.api.v1 import (  # noqa: F401
    agents,
    inboxiq,
    auth,
    billing,
    search,
    testimonials,
    feedback,
    intake,
    admin,
    admin_funnel,
    admin_content,
    blog,
    feedback_export,
    uploads,
    publishing,
    leads,
    twilio,
    source_connections,
    funnel_analytics,
    content,
    outreach,
)
