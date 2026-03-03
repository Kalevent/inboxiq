from datetime import datetime
from uuid import uuid4
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import TSVECTOR
from src.extensions import db

try:  # Optional pgvector support
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:
    Vector = None

class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    __table_args__ = (
        db.UniqueConstraint("slug", name="uq_blog_slug"),
        db.Index("idx_blog_posts_generated", "generated_content_id"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="draft")  # draft|queued|generating|ready|failed|published
    funnel_stage = db.Column(db.String(16), nullable=True)
    primary_keyword = db.Column(db.String(255), nullable=True)
    secondary_keywords = db.Column(db.JSON, nullable=False, default=list)
    summary = db.Column(db.Text, nullable=True)
    excerpt = db.Column(db.Text, nullable=True)
    content_html = db.Column(db.Text, nullable=True)
    markdown = db.Column(db.Text, nullable=True)
    rendered_html = db.Column(db.Text, nullable=True)
    brief_json = db.Column(db.JSON, nullable=True)
    last_prompt = db.Column(db.Text, nullable=True)
    meta_description = db.Column(db.Text, nullable=True)
    canonical_url = db.Column(db.String(512), nullable=True)
    hero_image_url = db.Column(db.String(1024), nullable=True)
    hero_image_alt = db.Column(db.String(255), nullable=True)
    word_count = db.Column(db.Integer, nullable=True)
    read_time_minutes = db.Column(db.SmallInteger, nullable=True)
    internal_links = db.Column(db.JSON, nullable=False, default=list)

    # Funnel v2.0: Link to generated_content table
    generated_content_id = db.Column(db.String(64), db.ForeignKey("generated_content.id"), nullable=True)
    auto_generated = db.Column(db.Boolean, server_default="false")
    dspy_quality_score = db.Column(db.Float, nullable=True)

    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "slug": self.slug,
            "status": self.status,
            "funnel_stage": self.funnel_stage,
            "primary_keyword": self.primary_keyword,
            "secondary_keywords": self.secondary_keywords or [],
            "summary": self.summary,
            "excerpt": self.excerpt,
            "content_html": self.content_html,
            "markdown": self.markdown,
            "rendered_html": self.rendered_html,
            "brief_json": self.brief_json or {},
            "last_prompt": self.last_prompt,
            "meta_description": self.meta_description,
            "canonical_url": self.canonical_url,
            "hero_image_url": self.hero_image_url,
            "hero_image_alt": self.hero_image_alt,
            "word_count": self.word_count,
            "read_time_minutes": self.read_time_minutes,
            "internal_links": self.internal_links or [],
            "generated_content_id": self.generated_content_id,
            "auto_generated": self.auto_generated,
            "dspy_quality_score": self.dspy_quality_score,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KBIntegration(db.Model):
    """Knowledge base integration configuration (per account)."""
    __tablename__ = "kb_integrations"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False, index=True)
    integration_type = db.Column(db.String(50), nullable=False)  # "file_upload", "zendesk", "notion", etc.
    status = db.Column(db.String(20), default="active")  # "active", "paused", "error"

    # Configuration (JSON)
    config_json = db.Column("config", db.JSON, nullable=False, default=dict)

    # Sync metadata
    last_sync_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_sync_status = db.Column(db.String(20), nullable=True)  # "success", "failed"
    last_sync_error = db.Column(db.Text, nullable=True)
    article_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    account = db.relationship("Account", backref="kb_integrations")
    articles = db.relationship("KBArticle", backref="integration", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "account_id": self.account_id,
            "integration_type": self.integration_type,
            "status": self.status,
            "config": self.config_json or {},
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
            "last_sync_error": self.last_sync_error,
            "article_count": self.article_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KBArticle(db.Model):
    """Knowledge base article content."""
    __tablename__ = "kb_articles"
    __table_args__ = (
        db.Index("ix_kb_articles_integration_title", "integration_id", "title"),
        db.Index("ix_kb_articles_external_id", "external_id"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    integration_id = db.Column(db.String(64), db.ForeignKey("kb_integrations.id"), nullable=False, index=True)

    # Article metadata
    external_id = db.Column(db.String(255), nullable=True)  # ID from external system (Zendesk, etc.)
    title = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(1000), nullable=True)

    # Categorization
    category = db.Column(db.String(255), nullable=True)
    tags_json = db.Column("tags", db.JSON, nullable=True)  # ["billing", "refunds"]
    language = db.Column(db.String(10), default="en")

    # Sync tracking
    external_updated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    synced_at = db.Column(db.DateTime(timezone=True), server_default=func.now())

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    embeddings = db.relationship("KBArticleEmbedding", backref="article", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "integration_id": self.integration_id,
            "external_id": self.external_id,
            "title": self.title,
            "content": self.content,
            "url": self.url,
            "category": self.category,
            "tags": self.tags_json or [],
            "language": self.language,
            "external_updated_at": self.external_updated_at.isoformat() if self.external_updated_at else None,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KBArticleEmbedding(db.Model):
    """Vector embeddings for KB articles (semantic search)."""
    __tablename__ = "kb_article_embeddings"

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    article_id = db.Column(db.String(64), db.ForeignKey("kb_articles.id"), nullable=False, index=True)

    # Embedding data (same pattern as TicketEmbedding)
    embedding_model = db.Column(db.String(100), default="text-embedding-3-small")
    embedding_vector = db.Column(Vector(1536)) if Vector else db.Column(db.JSON, nullable=True)
    embedding_json = db.Column(db.JSON, nullable=True)  # JSON fallback if pgvector unavailable

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Vector index for cosine similarity search
    if Vector:
        __table_args__ = (
            db.Index(
                "ix_kb_article_embeddings_vector",
                "embedding_vector",
                postgresql_using="ivfflat",
                postgresql_with={"lists": 100},
                postgresql_ops={"embedding_vector": "vector_cosine_ops"},
            ),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "article_id": self.article_id,
            "embedding_model": self.embedding_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class GeneratedContent(db.Model):
    """
    Tracks all DSPy-generated content (blogs, emails, case studies, landing pages).
    Stores full generation pipeline outputs and quality metrics.
    """
    __tablename__ = "generated_content"
    __table_args__ = (
        db.Index("idx_generated_content_type", "content_type", "status"),
        db.Index("idx_generated_content_published", "published_at", postgresql_where=db.text("published_at IS NOT NULL")),
        db.Index("idx_generated_content_funnel_stage", "funnel_stage"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    content_type = db.Column(db.String(50), nullable=False, comment="blog_post | email | case_study | landing_page | social_post")
    title = db.Column(db.String(500), nullable=True)
    slug = db.Column(db.String(200), nullable=True)
    content = db.Column(db.Text, nullable=False)
    meta_data = db.Column(db.JSON, nullable=True, comment="{meta_title, meta_description, target_keywords, seo_score, word_count}")
    generation_pipeline = db.Column(db.JSON, nullable=True, comment="{topic_module_output, outline_module_output, writer_output, editor_output, seo_output}")
    dspy_version = db.Column(db.String(50), nullable=True, comment="Track which DSPy model version generated this")
    quality_score = db.Column(db.Float, nullable=True, comment="Human feedback: 0-10")
    status = db.Column(db.String(50), server_default="draft", comment="draft | published | archived")
    published_at = db.Column(db.DateTime(timezone=True), nullable=True)
    funnel_stage = db.Column(db.String(50), nullable=True, comment="Which funnel stage this content supports")
    target_audience_json = db.Column("target_audience", db.JSON, nullable=True, comment="ICP characteristics")
    performance_metrics = db.Column(db.JSON, nullable=True, comment="{views, engagement_rate, conversions, seo_ranking}")
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content_type": self.content_type,
            "title": self.title,
            "slug": self.slug,
            "content": self.content,
            "meta_data": self.meta_data or {},
            "generation_pipeline": self.generation_pipeline or {},
            "dspy_version": self.dspy_version,
            "quality_score": self.quality_score,
            "status": self.status,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "funnel_stage": self.funnel_stage,
            "target_audience": self.target_audience_json or {},
            "performance_metrics": self.performance_metrics or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PitchedBlogTopic(db.Model):
    """
    Manually pitched blog topics that can be used for content generation.
    Allows users to submit topic ideas in addition to auto-generated topics.
    """
    __tablename__ = "pitched_blog_topics"
    __table_args__ = (
        db.Index("idx_pitched_topics_status", "status"),
        db.Index("idx_pitched_topics_created", "created_at"),
    )

    id = db.Column(db.String(64), primary_key=True, default=lambda: str(uuid4()), nullable=False)
    title = db.Column(db.String(500), nullable=False, comment="Working title or topic idea")
    description = db.Column(db.Text, nullable=True, comment="Optional description or angle")
    target_keyword = db.Column(db.String(255), nullable=True, comment="Primary keyword to target")
    secondary_keywords = db.Column(db.JSON, nullable=False, default=list, comment="Additional keywords")
    funnel_stage = db.Column(db.String(50), nullable=True, comment="discovery | consideration | decision")
    target_audience = db.Column(db.String(500), nullable=True, comment="Target audience/persona")
    niche = db.Column(db.String(255), nullable=True, comment="Blog niche (e.g., Revenue Operations)")
    pitch_notes = db.Column(db.Text, nullable=True, comment="Additional notes from submitter")

    status = db.Column(db.String(50), nullable=False, default="pending", comment="pending | approved | rejected | generated")
    priority = db.Column(db.SmallInteger, nullable=False, default=3, comment="1=high, 2=medium, 3=low")

    # Tracking fields
    submitted_by = db.Column(db.String(255), nullable=True, comment="Email of submitter")
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    generated_content_id = db.Column(db.String(64), db.ForeignKey("generated_content.id"), nullable=True, comment="Link to generated content if used")

    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "target_keyword": self.target_keyword,
            "secondary_keywords": self.secondary_keywords or [],
            "funnel_stage": self.funnel_stage,
            "target_audience": self.target_audience,
            "niche": self.niche,
            "pitch_notes": self.pitch_notes,
            "status": self.status,
            "priority": self.priority,
            "submitted_by": self.submitted_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "generated_content_id": self.generated_content_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


