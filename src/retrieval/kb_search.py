"""Knowledge Base semantic search using vector embeddings."""

from __future__ import annotations
import logging
from typing import List, Optional
from sqlalchemy import text

from src.models import KBArticle, KBArticleEmbedding, KBIntegration
from src.embeddings import embed_text
from src.extensions import db

logger = logging.getLogger(__name__)


def search_kb_articles(
    query: str,
    account_id: int,
    limit: int = 3,
    similarity_threshold: float = 0.6,
    language: Optional[str] = None,
) -> List[dict]:
    """
    Search KB articles using semantic similarity.

    Args:
        query: Customer question/email content
        account_id: Account ID (integer)
        limit: Max number of articles to return (default 3)
        similarity_threshold: Min cosine similarity (0.6 = medium, 0.8 = high)
        language: Filter by language code (e.g., "en")

    Returns:
        List of article dicts with keys: id, title, content, url, similarity_score
    """
    # 1. Get active KB integration for account
    integration = KBIntegration.query.filter_by(
        account_id=account_id,
        status="active"
    ).first()

    if not integration:
        logger.debug(f"No active KB integration for account {account_id}")
        return []

    # 2. Generate query embedding
    try:
        query_embedding = embed_text(query, account_id=str(account_id))
        if not query_embedding:
            logger.warning(f"Failed to generate embedding for query: {query[:50]}")
            return []
    except Exception as e:
        logger.error(f"Error embedding query: {e}")
        return []

    # 3. Perform vector similarity search
    try:
        # Use pgvector cosine similarity (1 - cosine_distance)
        sql = text("""
            SELECT
                a.id,
                a.title,
                a.content,
                a.url,
                a.category,
                1 - (e.embedding_vector <=> :query_vector) AS similarity_score
            FROM kb_articles a
            JOIN kb_article_embeddings e ON e.article_id = a.id
            WHERE a.integration_id = :integration_id
                AND (:language IS NULL OR a.language = :language)
                AND 1 - (e.embedding_vector <=> :query_vector) >= :threshold
            ORDER BY e.embedding_vector <=> :query_vector
            LIMIT :limit
        """)

        results = db.session.execute(sql, {
            "query_vector": query_embedding,
            "integration_id": integration.id,
            "language": language,
            "threshold": similarity_threshold,
            "limit": limit,
        }).fetchall()

        articles = []
        for row in results:
            articles.append({
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "url": row.url,
                "category": row.category,
                "similarity_score": float(row.similarity_score),
            })

        logger.info(f"KB search found {len(articles)} articles for account {account_id}")
        return articles

    except Exception as e:
        logger.error(f"KB search failed: {e}", exc_info=True)
        return []


def format_kb_context_for_prompt(articles: List[dict]) -> str:
    """Format retrieved KB articles for LLM context."""
    if not articles:
        return ""

    context_parts = ["Relevant knowledge base articles:"]
    for i, article in enumerate(articles, 1):
        context_parts.append(f"\n[Article {i}] {article['title']}")
        if article.get("url"):
            context_parts.append(f"URL: {article['url']}")
        # Truncate content to avoid token limits (first 500 chars)
        content_preview = article["content"][:500]
        if len(article["content"]) > 500:
            content_preview += "..."
        context_parts.append(f"Content: {content_preview}")
        context_parts.append("")  # Blank line

    return "\n".join(context_parts)
