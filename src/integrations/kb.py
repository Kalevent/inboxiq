"""Knowledge base integration handlers."""

from __future__ import annotations
import ipaddress
import logging
import os
import re
import socket
import uuid
from datetime import datetime
from html.parser import HTMLParser
from typing import List
from urllib.parse import urlparse
from werkzeug.datastructures import FileStorage

from src.models.content import KBIntegration, KBArticle, KBArticleEmbedding
from src.embeddings import embed_text
from src.extensions import db
from src.sanitize import sanitize_html
from src.uploads import upload_bytes

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {".md", ".txt", ".html", ".pdf"}
MAX_URL_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
_PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


class _TextExtractor(HTMLParser):
    """Strip HTML tags and return visible text, skipping script/style/nav."""

    _SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside"}

    def __init__(self):
        super().__init__()
        self._depth = 0
        self._skip_depth: int | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._skip_depth is not None:
            self._depth += 1
        elif tag in self._SKIP_TAGS:
            self._skip_depth = self._depth
        self._depth += 1

    def handle_endtag(self, tag):
        self._depth -= 1
        if self._skip_depth is not None and self._depth <= self._skip_depth:
            self._skip_depth = None

    def handle_data(self, data):
        if self._skip_depth is None:
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self.parts)


def _validate_url(url: str) -> str | None:
    """Return error string if URL is invalid or targets a private/internal host, else None."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL"
    if parsed.scheme not in ("http", "https"):
        return "URL must start with http:// or https://"
    if not parsed.hostname:
        return "URL has no hostname"
    try:
        addr = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
        if any(addr in net for net in _PRIVATE_RANGES):
            return "URL resolves to a private/internal address"
    except Exception:
        pass  # DNS failure is handled by requests itself
    return None


def _extract_text_from_html(html: str) -> str:
    """Return plain text extracted from HTML, collapsing whitespace."""
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    text = parser.get_text()
    return re.sub(r"\s{2,}", " ", text).strip()


def get_or_create_url_integration(account_id: int) -> KBIntegration:
    """Get or create the shared URL KB integration for an account."""
    integration = KBIntegration.query.filter_by(
        account_id=account_id,
        integration_type="url",
    ).first()
    if not integration:
        integration = KBIntegration(
            id=str(uuid.uuid4()),
            account_id=account_id,
            integration_type="url",
            status="active",
            config_json={},
        )
        db.session.add(integration)
        db.session.commit()
    return integration


def process_url_source(account_id: int, url: str, title: str) -> dict:
    """
    Fetch a public URL, extract text, and add it to the account's KB.

    Returns {"success": bool, "error": str | None}
    """
    import requests as req

    url = url.strip()
    err = _validate_url(url)
    if err:
        return {"success": False, "error": err}

    title = sanitize_html(title.strip()) if title.strip() else url

    # Check for duplicate URL in this account's url integration
    existing_integration = KBIntegration.query.filter_by(
        account_id=account_id, integration_type="url"
    ).first()
    if existing_integration:
        dup = KBArticle.query.filter_by(
            integration_id=existing_integration.id,
            external_id=url,
        ).first()
        if dup:
            return {"success": False, "error": "This URL is already in your knowledge base"}

    try:
        resp = req.get(
            url,
            timeout=15,
            headers={"User-Agent": "InboxIQ-KB/1.0 (+https://kalevent.com)"},
            stream=True,
        )
        resp.raise_for_status()

        # Safety: cap download size
        content = b""
        for chunk in resp.iter_content(chunk_size=65536):
            content += chunk
            if len(content) > MAX_URL_CONTENT_LENGTH:
                break

        content_type = resp.headers.get("content-type", "")
        if "html" in content_type:
            raw_text = _extract_text_from_html(content.decode("utf-8", errors="ignore"))
        else:
            raw_text = content.decode("utf-8", errors="ignore")

        raw_text = raw_text.strip()
        if not raw_text:
            return {"success": False, "error": "Page returned no readable text"}

        # Truncate to a sensible embedding size (~100k chars)
        if len(raw_text) > 100_000:
            raw_text = raw_text[:100_000]

    except req.exceptions.Timeout:
        return {"success": False, "error": "URL timed out (15s limit)"}
    except req.exceptions.RequestException as exc:
        return {"success": False, "error": f"Could not fetch URL: {exc}"}

    integration = get_or_create_url_integration(account_id)

    try:
        article = KBArticle(
            id=str(uuid.uuid4()),
            integration_id=integration.id,
            external_id=url,
            title=title,
            content=raw_text,
            url=url,
            language="en",
        )
        db.session.add(article)
        db.session.flush()

        embedding_vector = embed_text(raw_text, account_id=str(account_id))
        if embedding_vector:
            db.session.add(KBArticleEmbedding(
                id=str(uuid.uuid4()),
                article_id=article.id,
                embedding_vector=embedding_vector,
            ))

        integration.article_count = KBArticle.query.filter_by(
            integration_id=integration.id
        ).count()
        integration.last_sync_at = datetime.utcnow()
        integration.last_sync_status = "success"
        db.session.commit()
        return {"success": True, "error": None}

    except Exception as exc:
        db.session.rollback()
        logger.error("process_url_source failed for %s: %s", url, exc)
        return {"success": False, "error": "Failed to save article"}
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
        import pypdf
        from io import BytesIO

        pdf_file = BytesIO(pdf_bytes)
        reader = pypdf.PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text())
        return "\n".join(text_parts)
    except ImportError:
        logger.warning("pypdf not installed, skipping PDF extraction")
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
