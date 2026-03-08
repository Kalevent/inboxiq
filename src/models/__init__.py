"""
SQLAlchemy models — organised by domain.

All classes are re-exported here so callers can import from either
`src.models.<domain>` (preferred) or `src.models` (backwards compat).
"""
from src.models.core import Account, User, InboxConnection, AccountFeatureFlags, AccountLLMConfig, ALLOWED_LLM_PROVIDERS, MailboxSyncPreference
from src.models.auth import AuthEvent, Passkey, TOTPDevice, AuditLog
from src.models.tickets import Ticket, TicketEmbedding, TriageLabelConfig, DraftReplyFeedback, TriageConfig, SenderProfile, ClassificationCorrection
from src.models.ai import DspyTrainingMetric, AgentEvent, AgentModel, MCPServerCatalog
from src.models.leads import Lead, LeadFunnelStage, LeadEngagementEvent, LeadAttribution, FunnelMetricsDaily
from src.models.content import BlogPost, KBIntegration, KBArticle, KBArticleEmbedding, GeneratedContent, PitchedBlogTopic
from src.models.campaigns import CampaignSender, HunterDomainCache, EmailCampaign, EmailOutreach, NurtureEmailSend
from src.models.automation import AutomationStudioWaitlist, AutomationRule, AutomationRuleExecution, WebhookProvider, AutomationSuggestion
from src.models.marketing import Referral, InAppMessage, InAppMessageDismissal, LandingPage, MarketingSpend, EnterpriseInquiry
from src.models.misc import Testimonial, Feedback
from src.models.developer import DeveloperAccessRequest, RegisteredApp
from src.models.billing import (
    PaymentProviderAccount, CustomerBillingProfile, PaymentMethod,
    Plan, Subscription, Invoice, ChargeAttempt, AccountUsageCounter,
    table_exists,
)
from src.models.publishing import NewsletterDraft, WhitepaperDraft

__all__ = [
    # core
    "Account", "User", "InboxConnection", "AccountFeatureFlags", "AccountLLMConfig", "ALLOWED_LLM_PROVIDERS", "MailboxSyncPreference",
    # auth
    "AuthEvent", "Passkey", "TOTPDevice", "AuditLog",
    # tickets
    "Ticket", "TicketEmbedding", "TriageLabelConfig", "DraftReplyFeedback", "TriageConfig", "SenderProfile", "ClassificationCorrection",
    # ai
    "DspyTrainingMetric", "AgentEvent", "AgentModel", "MCPServerCatalog",
    # leads
    "Lead", "LeadFunnelStage", "LeadEngagementEvent", "LeadAttribution", "FunnelMetricsDaily",
    # content
    "BlogPost", "KBIntegration", "KBArticle", "KBArticleEmbedding", "GeneratedContent", "PitchedBlogTopic",
    # campaigns
    "CampaignSender", "HunterDomainCache", "EmailCampaign", "EmailOutreach", "NurtureEmailSend",
    # automation
    "AutomationStudioWaitlist", "AutomationRule", "AutomationRuleExecution", "WebhookProvider", "AutomationSuggestion",
    # marketing
    "Referral", "InAppMessage", "InAppMessageDismissal", "LandingPage", "MarketingSpend", "EnterpriseInquiry",
    # misc
    "Testimonial", "Feedback",
    # developer
    "DeveloperAccessRequest", "RegisteredApp",
    # billing
    "PaymentProviderAccount", "CustomerBillingProfile", "PaymentMethod",
    "Plan", "Subscription", "Invoice", "ChargeAttempt", "AccountUsageCounter",
    "table_exists",
    # publishing
    "NewsletterDraft", "WhitepaperDraft",
]
