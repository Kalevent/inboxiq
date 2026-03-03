"""Knowledge base integration handlers."""

from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime
from typing import List
from werkzeug.datastructures import FileStorage

from src.models import KBIntegration, KBArticle, KBArticleEmbedding
from src.embeddings import embed_text
from src.extensions import db
from src.sanitize import sanitize_html
from src.uploads import upload_bytes

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".md", ".txt", ".html", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_UPLOAD = 100


def create_file_upload_integration(account_id: int) -> KBIntegration:
    """Create or get file upload integration for account."""
    integration = KBIntegration.query.filter_by(
        account_id=account_id,
        integration_type="file_upload"
    ).first()

    if not integration:
        integration = KBIntegration(
            id=str(uuid.uuid4()),
            account_id=account_id,
            integration_type="file_upload",
            status="active",
            config_json={},
        )
        db.session.add(integration)
        db.session.commit()
        logger.info(f"Created file upload integration for account {account_id}")

    return integration


def process_uploaded_files(
    files: List[FileStorage],
    account_id: int,
) -> dict:
    """
    Process uploaded KB article files.

    Returns:
        {"success": int, "failed": int, "errors": [str]}
    """
    if len(files) > MAX_FILES_PER_UPLOAD:
        return {
            "success": 0,
            "failed": len(files),
            "errors": [f"Too many files (max {MAX_FILES_PER_UPLOAD})"]
        }

    integration = create_file_upload_integration(account_id)

    success_count = 0
    failed_count = 0
    errors = []

    for file in files:
        try:
            # Validate file
            if not file.filename:
                errors.append("Empty filename")
                failed_count += 1
                continue

            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in SUPPORTED_FORMATS:
                errors.append(f"{file.filename}: Unsupported format")
                failed_count += 1
                continue

            # Read file bytes
            content_bytes = file.read()
            if len(content_bytes) > MAX_FILE_SIZE:
                errors.append(f"{file.filename}: File too large")
                failed_count += 1
                continue

            # Upload original file to S3 (files.kalevent.com for security isolation)
            try:
                from werkzeug.utils import secure_filename
                safe_filename = secure_filename(file.filename)
                s3_key = f"kb/{account_id}/{uuid.uuid4().hex}_{safe_filename}"

                # Determine content type
                content_type_map = {
                    ".md": "text/markdown",
                    ".txt": "text/plain",
                    ".html": "text/html",
                    ".pdf": "application/pdf",
                }
                content_type = content_type_map.get(ext, "application/octet-stream")

                # Upload to S3 with security headers
                file_url = upload_bytes(
                    key=s3_key,
                    data=content_bytes,
                    content_type=content_type,
                    content_disposition=f'attachment; filename="{safe_filename}"',
                )
            except Exception as e:
                logger.error(f"S3 upload failed for {file.filename}: {e}")
                errors.append(f"{file.filename}: Upload failed")
                failed_count += 1
                continue

            # Extract text content for embeddings (sanitized version stored in DB)
            if ext == ".pdf":
                text_content = extract_text_from_pdf(content_bytes)
            else:
                text_content = content_bytes.decode("utf-8", errors="ignore")

            if not text_content.strip():
                errors.append(f"{file.filename}: Empty content")
                failed_count += 1
                continue

            # Sanitize HTML and Markdown files to prevent XSS attacks
            # TXT and PDF files are plain text, so no sanitization needed
            if ext in {".html", ".md"}:
                text_content = sanitize_html(text_content)

            # Sanitize title (from filename) to prevent XSS in UI
            title = os.path.splitext(file.filename)[0]
            title = sanitize_html(title)

            # Create article with both URL (original file) and content (sanitized text)
            article = KBArticle(
                id=str(uuid.uuid4()),
                integration_id=integration.id,
                title=title,
                content=text_content,  # Sanitized text for embeddings
                url=file_url,  # Original file on files.kalevent.com
                language="en",  # Default, can detect later
            )
            db.session.add(article)
            db.session.flush()  # Get article.id

            # Generate embedding from sanitized text content
            embedding_vector = embed_text(text_content, account_id=str(account_id))
            if embedding_vector:
                embedding = KBArticleEmbedding(
                    id=str(uuid.uuid4()),
                    article_id=article.id,
                    embedding_vector=embedding_vector,
                )
                db.session.add(embedding)

            success_count += 1

        except Exception as e:
            logger.error(f"Failed to process {file.filename}: {e}")
            errors.append(f"{file.filename}: {str(e)}")
            failed_count += 1
            db.session.rollback()
            continue

    # Update integration metadata
    if success_count > 0:
        integration.article_count = KBArticle.query.filter_by(
            integration_id=integration.id
        ).count()
        integration.last_sync_at = datetime.utcnow()
        integration.last_sync_status = "success"
        db.session.commit()

    return {
        "success": success_count,
        "failed": failed_count,
        "errors": errors,
    }


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF (basic implementation)."""
    try:
        import PyPDF2
        from io import BytesIO

        pdf_file = BytesIO(pdf_bytes)
        reader = PyPDF2.PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text())
        return "\n".join(text_parts)
    except ImportError:
        logger.warning("PyPDF2 not installed, skipping PDF extraction")
        return ""
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        return ""


def delete_kb_article(article_id: str, account_id: int) -> bool:
    """Delete KB article and its embeddings."""
    article = KBArticle.query.join(KBIntegration).filter(
        KBArticle.id == article_id,
        KBIntegration.account_id == account_id,
    ).first()

    if not article:
        return False

    db.session.delete(article)  # Cascade deletes embeddings
    db.session.commit()
    return True
