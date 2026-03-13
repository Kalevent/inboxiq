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

# Default article limits by plan code (used until subscription wiring is complete)
_KB_LIMIT_BY_PLAN: dict[str, int | None] = {
    "pro": 50,
    "business": 200,
    "scale": None,  # unlimited
}
_KB_LIMIT_DEFAULT = 25  # trial / no plan


def _account_is_admin(account_id: int) -> bool:
    """Return True if the account has developer_access (admin/owner account)."""
    try:
        from src.models.core import Account
        account = Account.query.get(account_id)
        return bool(account and account.developer_access)
    except Exception:
        return False


def get_kb_article_limit(account_id: int) -> int | None:
    """Return the KB article limit for the account. None = unlimited.

    Admin accounts (developer_access=True) are always unlimited.
    Reads kb_articles_limit from the Plan row when set; falls back to
    _KB_LIMIT_BY_PLAN by plan code; defaults to _KB_LIMIT_DEFAULT.
    """
    if _account_is_admin(account_id):
        return None  # unlimited for admin/owner account
    try:
        from src.models.billing import CustomerBillingProfile, Plan
        profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
        if profile and profile.plan_choice:
            plan = Plan.query.filter_by(code=profile.plan_choice).first()
            if plan and plan.kb_articles_limit is not None:
                return plan.kb_articles_limit
            return _KB_LIMIT_BY_PLAN.get(profile.plan_choice, _KB_LIMIT_DEFAULT)
    except Exception:
        pass
    return _KB_LIMIT_DEFAULT


def count_kb_articles(account_id: int) -> int:
    """Count total KB articles across all integrations for the account."""
    integrations = KBIntegration.query.filter_by(account_id=account_id).all()
    return sum(i.article_count or 0 for i in integrations)


# Plans that can use the crawl feature
_KB_CRAWL_PLANS = {"business", "scale"}
# Max pages per crawl by plan (admin gets 200)
_KB_CRAWL_MAX: dict[str, int] = {"business": 50, "scale": 200}
_KB_CRAWL_MAX_DEFAULT = 200  # admin


def is_crawl_enabled(account_id: int) -> bool:
    """Return True if crawl mode is available for this account."""
    if _account_is_admin(account_id):
        return True
    try:
        from src.models.billing import CustomerBillingProfile
        profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
        return bool(profile and profile.plan_choice in _KB_CRAWL_PLANS)
    except Exception:
        return False


def get_crawl_max_pages(account_id: int) -> int:
    """Return the max pages this account can crawl in one job."""
    if _account_is_admin(account_id):
        return _KB_CRAWL_MAX_DEFAULT
    try:
        from src.models.billing import CustomerBillingProfile
        profile = CustomerBillingProfile.query.filter_by(account_id=account_id).first()
        if profile and profile.plan_choice:
            return _KB_CRAWL_MAX.get(profile.plan_choice, 0)
    except Exception:
        pass
    return 0


class _LinkExtractor(HTMLParser):
    """Extract all href values from anchor tags."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr, val in attrs:
                if attr == "href" and val:
                    self.links.append(val)


def _discover_same_domain_links(html: str, base_url: str, max_pages: int) -> list[str]:
    """
    Parse HTML and return same-domain absolute URLs found in anchor tags.
    Strips fragments and deduplicates. Caps at max_pages.
    """
    from urllib.parse import urljoin, urlparse
    base_parsed = urlparse(base_url)
    base_domain = base_parsed.netloc
    extractor = _LinkExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass

    seen: set[str] = set()
    links: list[str] = []
    for href in extractor.links:
        try:
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            clean = parsed._replace(fragment="").geturl()
            if (
                parsed.netloc == base_domain
                and parsed.scheme in ("http", "https")
                and clean not in seen
            ):
                seen.add(clean)
                links.append(clean)
                if len(links) >= max_pages:
                    break
        except Exception:
            continue
    return links


def crawl_kb_source(account_id: int, base_url: str) -> dict:
    """
    Crawl base_url and index all same-domain pages found (one level deep).

    Returns {"indexed": int, "skipped": int, "errors": [str]}
    """
    import requests as req

    if not is_crawl_enabled(account_id):
        return {
            "indexed": 0, "skipped": 0,
            "errors": ["Crawl mode is available on Business and Scale plans."],
        }

    err = _validate_url(base_url)
    if err:
        return {"indexed": 0, "skipped": 0, "errors": [err]}

    max_pages = get_crawl_max_pages(account_id)

    # Fetch base page
    try:
        session = req.Session()

        def _check_redirect(response, *args, **kwargs):
            location = response.headers.get("Location", "")
            if location:
                redir_parsed = urlparse(location)
                if redir_parsed.hostname and _is_private_ip(redir_parsed.hostname):
                    raise ValueError(f"Redirect to private address blocked: {location}")

        session.hooks["response"].append(_check_redirect)
        resp = session.get(
            base_url, timeout=15,
            headers={"User-Agent": "InboxIQ-KB/1.0 (+https://kalevent.com)"},
            stream=True,
        )
        resp.raise_for_status()
        content = b""
        for chunk in resp.iter_content(chunk_size=65536):
            content += chunk
            if len(content) > MAX_URL_CONTENT_LENGTH:
                break
        html_content = content.decode("utf-8", errors="ignore")
    except Exception as exc:
        return {"indexed": 0, "skipped": 0, "errors": [f"Could not fetch base URL: {exc}"]}

    # Build crawl queue: base URL + discovered same-domain links
    discovered = _discover_same_domain_links(html_content, base_url, max_pages - 1)
    urls_to_crawl = [base_url] + discovered

    indexed = 0
    skipped = 0
    errors: list[str] = []

    for url in urls_to_crawl:
        result = process_url_source(account_id, url, "")
        if result["success"]:
            indexed += 1
        elif result.get("error") == "This URL is already in your knowledge base":
            skipped += 1
        elif "limit reached" in (result.get("error") or ""):
            errors.append(result["error"])
            break  # no point continuing past the limit
        else:
            errors.append(f"{url}: {result.get('error', 'unknown error')}")

    logger.info(
        "crawl_kb_source account=%s base=%s indexed=%d skipped=%d errors=%d",
        account_id, base_url, indexed, skipped, len(errors),
    )
    return {"indexed": indexed, "skipped": skipped, "errors": errors}
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


def _is_private_ip(hostname: str) -> bool:
    """Return True if any resolved address for hostname is in a private/internal range."""
    try:
        results = socket.getaddrinfo(hostname, None)
        for result in results:
            addr_str = result[4][0]
            # Strip IPv6 zone ID if present (e.g. "fe80::1%eth0")
            addr_str = addr_str.split("%")[0]
            try:
                addr = ipaddress.ip_address(addr_str)
                if any(addr in net for net in _PRIVATE_RANGES):
                    return True
            except ValueError:
                pass
    except Exception:
        pass  # DNS failure is handled by requests itself
    return False


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
    if _is_private_ip(parsed.hostname):
        return "URL resolves to a private/internal address"
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

    limit = get_kb_article_limit(account_id)
    if limit is not None and count_kb_articles(account_id) >= limit:
        return {
            "success": False,
            "error": f"Article limit reached ({limit} articles on your plan). Upgrade to add more.",
        }

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
        # Validate each redirect destination before following it (prevents SSRF via open redirects)
        session = req.Session()

        def _check_redirect(response, *args, **kwargs):
            location = response.headers.get("Location", "")
            if location:
                try:
                    redir_parsed = urlparse(location)
                    if redir_parsed.hostname and _is_private_ip(redir_parsed.hostname):
                        raise ValueError(f"Redirect to private address blocked: {location}")
                except ValueError:
                    raise

        session.hooks["response"].append(_check_redirect)

        resp = session.get(
            url,
            timeout=15,
            headers={"User-Agent": "InboxIQ-KB/1.0 (+https://kalevent.com)"},
            stream=True,
            allow_redirects=True,
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

    except ValueError as exc:
        return {"success": False, "error": str(exc)}
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

        embedding_vector = embed_text(raw_text)
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

    limit = get_kb_article_limit(account_id)
    if limit is not None:
        current_count = count_kb_articles(account_id)
        remaining = limit - current_count
        if remaining <= 0:
            return {
                "success": 0,
                "failed": len(files),
                "errors": [f"Article limit reached ({limit} articles on your plan). Upgrade to add more."],
            }
        if len(files) > remaining:
            files = files[:remaining]
            logger.info("Trimmed upload batch to %d files (plan limit %d, current %d)", remaining, limit, current_count)

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
            embedding_vector = embed_text(text_content)
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
