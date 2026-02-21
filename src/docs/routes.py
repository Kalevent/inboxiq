"""
Documentation controllers (migrated from legacy MCP blueprint).
"""
import os
import logging
import markdown
from flask import render_template, abort, current_app, send_from_directory, g, request, redirect, url_for
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from markupsafe import Markup

from src.docs import bp
from src.sanitize import sanitize_html

logger = logging.getLogger(__name__)


class DocSearcher:
    """
    Simple document search utility for documentation.
    """

    def __init__(self):
        # Primary docs live under app/docs/documentation to decouple from app/mcp.
        docs_root = current_app.config.get(
            "DOCS_CONTENT_PATH",
            os.path.join(current_app.root_path, "docs", "documentation"),
        )
        # Fallback to legacy mcp/docs if the new path is missing.
        if not os.path.isdir(docs_root):
            docs_root = os.path.join(current_app.root_path, "mcp", "docs")
        self.docs_dir = docs_root
        self.doc_cache = {}
        self._load_documents()

    def _load_documents(self):
        """Load all markdown documents into a searchable cache"""
        try:
            for filename in os.listdir(self.docs_dir):
                if filename.endswith(".md"):
                    doc_path = os.path.join(self.docs_dir, filename)
                    with open(doc_path, "r") as file:
                        content = file.read()
                        doc_id = filename.replace(".md", "")

                        # Extract title from first heading
                        title = doc_id.replace("_", " ").title()
                        if content.startswith("# "):
                            title_line = content.split("\n")[0]
                            title = title_line.replace("# ", "")

                        self.doc_cache[doc_id] = {
                            "id": doc_id,
                            "title": title,
                            "content": content,
                            "path": f"/docs/{doc_id}",
                        }
        except Exception as e:
            logger.error("Error loading documents for search: %s", e)

    def query(self, search_term):
        """Search for documents containing the search term."""
        if not search_term or search_term.strip() == "":
            return []

        search_term = search_term.lower()
        results = []

        for doc_id, doc in self.doc_cache.items():
            content = doc["content"].lower()
            title = doc["title"].lower()

            if search_term in content or search_term in title:
                title_matches = title.count(search_term) * 3
                content_matches = content.count(search_term)
                score = title_matches + content_matches
                snippet = self._extract_snippet(content, search_term)

                results.append(
                    {
                        "id": doc_id,
                        "title": doc["title"],
                        "snippet": snippet,
                        "url": doc["path"],
                        "score": score,
                    }
                )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _extract_snippet(self, content, search_term, context_length=60):
        """Extract a text snippet around the first occurrence of the search term"""
        idx = content.find(search_term)
        if idx == -1:
            return content[:100] + "..."

        start = max(0, idx - context_length)
        end = min(len(content), idx + len(search_term) + context_length)

        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet


def _require_auth():
    """Require JWT; redirect to login with next + signup hint when missing."""
    try:
        verify_jwt_in_request()
        _ = get_jwt_identity()
        return None
    except Exception:
        login_url = url_for("login_page")
        next_param = request.path
        signup_hint = url_for("root")
        return redirect(f"{login_url}?next={next_param}&signup_hint={signup_hint}")


@bp.route("/")
@bp.route("")
def docs_index(lc=None):
    maybe_redirect = _require_auth()
    if maybe_redirect:
        return maybe_redirect
    if not hasattr(g, "search"):
        g.search = DocSearcher()
    try:
        docs_dir = g.search.docs_dir
        index_path = os.path.join(docs_dir, "index.md")
        if not os.path.exists(index_path):
            logger.error("Documentation index file not found at %s", index_path)
            abort(404, "Documentation index not found")

        with open(index_path, "r") as file:
            content = file.read()
            html_content = markdown.markdown(
                content,
                extensions=["markdown.extensions.fenced_code", "markdown.extensions.tables"],
            )
            html_content = Markup(sanitize_html(html_content))

        return render_template(
            "docs/document.html",
            title="Documentation",
            content=html_content,
            lc=lc,
            url_endpoints={},
            doc_name="index",
            current_page="introduction",
        )

    except Exception as e:
        logger.exception("Error rendering documentation index: %s", e)
        abort(500, f"Error loading documentation: {str(e)}")


@bp.route("/<doc_name>")
def docs_page(doc_name, lc=None):
    maybe_redirect = _require_auth()
    if maybe_redirect:
        return maybe_redirect
    if not hasattr(g, "search"):
        g.search = DocSearcher()
    try:
        if not doc_name.endswith(".md"):
            doc_name = f"{doc_name}.md"

        docs_dir = g.search.docs_dir
        doc_path = os.path.join(docs_dir, doc_name)

        if not os.path.exists(doc_path):
            logger.error("Documentation file not found: %s", doc_path)
            abort(404, f"Documentation '{doc_name}' not found")

        with open(doc_path, "r") as file:
            content = file.read()
            html_content = markdown.markdown(
                content,
                extensions=["markdown.extensions.fenced_code", "markdown.extensions.tables"],
            )
            html_content = Markup(sanitize_html(html_content))

        title = doc_name.replace(".md", "").replace("_", " ").title()
        if content.startswith("# "):
            title_line = content.split("\n")[0]
            title = title_line.replace("# ", "")

        # Related docs: only show InboxIQ-relevant pages (whitelist) and never legacy MCP entries.
        whitelist = ["index", "users_guide", "developer_guide", "intake_api", "email_outreach_postman_guide", "unified_intake_postman_guide", "service_integrations", "channel_intake_guide", "invite_teammates", "security_auth", "automation_studio_accounting"]
        base_id = doc_name.replace(".md", "")
        related = []
        related_ids = whitelist
        # For publishing brief docs, surface the live brief example alongside the standard links.
        if base_id == "publishing_brief_templates":
            related_ids = ["publishing_brief_example"] + whitelist

        for doc_id in related_ids:
            if doc_id == base_id:
                continue
            doc = g.search.doc_cache.get(doc_id)
            if not doc:
                continue
            related.append({"id": doc_id, "title": doc.get("title") or doc_id.replace("_", " ").title()})

        return render_template(
            "docs/document.html",
            title=title,
            content=html_content,
            lc=lc,
            url_endpoints={},
            doc_name=doc_name.replace(".md", ""),
            current_page=doc_name.replace(".md", ""),
            related_docs=related,
        )

    except Exception as e:
        logger.exception("Error rendering documentation page %s: %s", doc_name, e)
        abort(500, f"Error loading documentation: {str(e)}")


@bp.route("/search")
def docs_search(lc=None):
    maybe_redirect = _require_auth()
    if maybe_redirect:
        return maybe_redirect
    try:
        if not hasattr(g, "search"):
            g.search = DocSearcher()

        query = request.args.get("q", "")
        results = g.search.query(query) if query else []

        return render_template(
            "docs/search.html",
            title="Search Results",
            query=query,
            results=results,
            lc=lc,
            url_endpoints={},
        )

    except Exception as e:
        logger.exception("Error processing documentation search: %s", e)
        abort(500, f"Error searching documentation: {str(e)}")
