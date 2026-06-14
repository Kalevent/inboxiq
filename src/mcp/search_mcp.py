"""
Local search MCP server that reuses Kalevent's internet search logic without
pulling in pydantic dependencies. All required search utilities live inline to
keep the server lightweight.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

try:
    from fastmcp import FastMCP, Context
    from fastmcp.exceptions import ToolError
except ImportError:  # pragma: no cover - fallback for environments without fastmcp
    try:
        from fastmcp import FastMCP, Context
        class ToolError(Exception):  # type: ignore
            """Fallback ToolError."""
            pass
    except ImportError:
        from mcp.server.fastmcp import FastMCP, Context  # type: ignore
        class ToolError(Exception):  # type: ignore
            """Fallback ToolError."""
            pass

# Provide an aiohttp stub if it's missing to keep the server lightweight.
try:
    import aiohttp  # type: ignore
except ImportError:  # pragma: no cover - minimal stub
    import types as _types

    aiohttp = _types.ModuleType("aiohttp")

    class _DummyResponse:
        def __init__(self):
            self._json = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, exc, tb):
            return False

        def raise_for_status(self):
            return None

        async def json(self):
            return self._json

    class _DummySession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, exc, tb):
            return False

        def get(self, *_, **__):
            return _DummyResponse()

    aiohttp.ClientSession = _DummySession  # type: ignore[attr-defined]
    sys.modules["aiohttp"] = aiohttp


logger = logging.getLogger("ranger.search_mcp")
mcp = FastMCP("ranger-search")

SEARXNG_URL = os.getenv("SEARXNG_URL", "https://ranger-search.kalevent.com")
SEARXNG_ENGINES = [e.strip() for e in (os.getenv("SEARXNG_ENGINES") or "").split(",") if e.strip()]
SEARXNG_TIMEOUT = float(os.getenv("SEARXNG_TIMEOUT", "10"))


class InternetSearchTool:
    """
    Tool for performing internet searches from multiple sources.
    Results are ranked by relevance to the query.
    """

    def __init__(self, max_retries: int | None = None, cache_size: int = 20):
        self.name = "internet_search"
        self.description = "Tool for performing internet searches from multiple sources"
        self.parameters_json_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query string",
                },
                "context": {
                    "type": "object",
                    "description": "Optional context to refine the search",
                    "required": False,
                },
            },
        }
        self.function = self.search
        self.max_retries = max_retries
        self.cache_size = cache_size
        self._cache: OrderedDict[str, List[Dict[str, Any]]] = OrderedDict()

    async def search(
        self,
        ctx: Any,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Perform a SearxNG-backed web search with data handling and ranking.

        Args:
            ctx: Context with a logger attribute for diagnostics.
            query: The search query string.
            context: Optional context to refine the search (e.g., site restrictions).
        """
        try:
            if not SEARXNG_URL:
                return [{"error": "SEARXNG_URL is not configured"}]

            cache_key = f"{query}|{repr(context) if context else ''}"
            cached = self._cache.get(cache_key)
            if cached is not None:
                ctx.logger.debug("[InternetSearchTool] Cache hit for query")
                return [dict(r) for r in cached]

            aggregated_results: List[Dict[str, Any]] = []
            source_used = "searxng"

            if context:
                if "url" in context:
                    query += f" site:{context['url']}"
                if "products" in context:
                    keywords = " OR ".join(context["products"])
                    query += f" ({keywords})"

            async with aiohttp.ClientSession() as session:
                try:
                    searx_results = await self._search_searxng(session, query)
                    aggregated_results.extend(searx_results)
                except Exception as e:
                    ctx.logger.error(f"SearxNG search failed: {e}")
                    return [{"error": str(e)}]

            ranked = self.rank_results(aggregated_results, query)
            if ranked:
                self._cache[cache_key] = [dict(r) for r in ranked]
                self._cache.move_to_end(cache_key)
                if len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
            return ranked or [{"error": "No results found.", "source": source_used}]

        except aiohttp.ClientError as e:  # type: ignore[attr-defined]
            ctx.logger.error(f"[InternetSearchTool] Search error: {e}")
            return [{"error": str(e)}]
        except Exception as e:
            ctx.logger.error(f"[InternetSearchTool] Unexpected error: {e}")
            return [{"error": str(e)}]

    async def _search_searxng(self, session: aiohttp.ClientSession, query: str) -> List[Dict[str, Any]]:
        url = urljoin(SEARXNG_URL, "/search")
        params = {
            "q": query,
            "format": "json",
        }
        if SEARXNG_ENGINES:
            params["engines"] = ",".join(SEARXNG_ENGINES)
        headers = {"User-Agent": "Mozilla/5.0 (compatible; inboxiq-search-bot/1.0)"}
        async with session.get(url, params=params, timeout=SEARXNG_TIMEOUT, headers=headers) as response:
            response.raise_for_status()
            data = await response.json()
            results = data.get("results", [])
            return [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("content") or r.get("snippet"),
                    "source": "searxng",
                }
                for r in results
            ]

    def rank_results(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        """
        Rank results based on relevance to the search query.
        """
        keywords = query.lower().split()
        for result in results:
            text = (result.get("title", "") + result.get("snippet", "")).lower()
            result["score"] = sum(word in text for word in keywords)
        return sorted(results, key=lambda r: r["score"], reverse=True)


class SearchResultProcessor:
    """
    Tool for processing and enhancing search results.

    This class provides methods to process search results by:
    1. Filtering and removing duplicate results
    2. Enhancing result metadata
    3. Extracting key information
    4. Sorting and ranking results based on various criteria
    5. Formatting results for better readability
    """

    def __init__(self, max_results: int = 10):
        self.max_results = max_results

    def process_results(
        self,
        ctx: Any,
        results: List[Dict[str, Any]],
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: str = "relevance",
    ) -> List[Dict[str, Any]]:
        """
        Process search results through filtering, enhancing, and sorting.
        """
        if not results:
            ctx.logger.warning("[SearchResultProcessor] No results to process")
            return []

        ctx.logger.debug(f"[SearchResultProcessor] Processing {len(results)} search results")

        processed_results = self._preprocess_results(results)

        if filters:
            processed_results = self._filter_results(processed_results, filters)

        processed_results = self._remove_duplicates(processed_results)
        processed_results = self._enhance_results(processed_results, query)
        processed_results = self._sort_results(processed_results, sort_by)
        processed_results = processed_results[: self.max_results]

        ctx.logger.debug(f"[SearchResultProcessor] Returning {len(processed_results)} processed results")
        return processed_results

    def _preprocess_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        preprocessed: List[Dict[str, Any]] = []

        for result in results:
            if not result or "error" in result:
                continue

            processed_result: Dict[str, Any] = {
                "title": result.get("title", "Untitled"),
                "url": result.get("url", ""),
                "snippet": result.get("snippet", ""),
                "source": result.get("source", "unknown"),
                "score": result.get("score", 0),
            }

            if processed_result["url"]:
                try:
                    parsed_url = urlparse(processed_result["url"])
                    processed_result["domain"] = parsed_url.netloc
                except Exception:
                    processed_result["domain"] = ""

            if processed_result["snippet"]:
                processed_result["snippet"] = re.sub(r"<[^>]+>", "", processed_result["snippet"])
                processed_result["snippet"] = re.sub(r"\s+", " ", processed_result["snippet"]).strip()

            preprocessed.append(processed_result)

        return preprocessed

    def _filter_results(self, results: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        filtered = results

        if "domains" in filters and isinstance(filters["domains"], list):
            allowed_domains = [d.lower() for d in filters["domains"]]
            filtered = [r for r in filtered if any(d in r.get("domain", "").lower() for d in allowed_domains)]

        if "content_type" in filters:
            content_type = filters["content_type"].lower()
            if content_type == "pdf":
                filtered = [r for r in filtered if r.get("url", "").lower().endswith(".pdf")]
            elif content_type == "academic":
                academic_domains = [".edu", ".ac.", "scholar.", "research.", "academic."]
                filtered = [r for r in filtered if any(d in r.get("domain", "").lower() for d in academic_domains)]

        if "date_after" in filters and "date" in results[0]:
            filtered = [r for r in filtered if r.get("date", "") >= filters["date_after"]]

        return filtered

    def _remove_duplicates(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique_urls = set()
        unique_results: List[Dict[str, Any]] = []

        for result in results:
            url = result.get("url", "")

            if url in unique_urls:
                continue

            title = result.get("title", "").lower()
            is_duplicate = False

            for unique_result in unique_results:
                existing_title = unique_result.get("title", "").lower()

                if title and existing_title and (
                    title in existing_title
                    or existing_title in title
                    or self._compute_similarity(title, existing_title) > 0.8
                ):
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_urls.add(url)
                unique_results.append(result)

        return unique_results

    def _compute_similarity(self, str1: str, str2: str) -> float:
        words1 = set(str1.split())
        words2 = set(str2.split())

        if not words1 or not words2:
            return 0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union)

    def _enhance_results(self, results: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
        query_terms = set(query.lower().split())

        for result in results:
            domain = result.get("domain", "")
            if domain:
                result["domain_authority"] = self._estimate_domain_authority(domain)

            snippet = result.get("snippet", "")
            if snippet:
                result["relevant_fragment"] = self._extract_relevant_fragment(snippet, query_terms)
                result["keyword_matches"] = sum(term in snippet.lower() for term in query_terms)

        return results

    def _estimate_domain_authority(self, domain: str) -> float:
        authority = 0.5

        known_high_authority = [
            ".gov",
            ".edu",
            "wikipedia.org",
            "nytimes.com",
            "bbc.",
            "reuters.com",
            "nature.com",
            "science.org",
            "harvard.",
            "stanford.",
            "mit.edu",
        ]

        for high_auth in known_high_authority:
            if high_auth in domain:
                authority = 0.9
                break

        tld = domain.split(".")[-1] if "." in domain else ""
        if tld in ["com", "org", "net"]:
            authority += 0.1
        elif tld in ["io", "ai", "co"]:
            authority -= 0.1

        return min(max(authority, 0.1), 1.0)

    def _extract_relevant_fragment(self, text: str, query_terms: set[str]) -> str:
        if not text or not query_terms:
            return text

        sentences = re.split(r"[.!?]+", text)

        if not sentences:
            return text

        scored_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            score = sum(term in sentence.lower() for term in query_terms)
            scored_sentences.append((score, sentence))

        if scored_sentences:
            scored_sentences.sort(reverse=True)
            return scored_sentences[0][1]

        return sentences[0] if sentences else text

    def _sort_results(self, results: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
        if not results:
            return results

        if sort_by == "relevance":
            return sorted(
                results,
                key=lambda r: (
                    r.get("score", 0) * 2
                    + r.get("keyword_matches", 0) * 3
                    + r.get("domain_authority", 0.5) * 5
                ),
                reverse=True,
            )
        elif sort_by == "date" and "date" in results[0]:
            return sorted(results, key=lambda r: r.get("date", ""), reverse=True)
        elif sort_by == "domain":
            return sorted(results, key=lambda r: r.get("domain_authority", 0), reverse=True)
        else:
            return sorted(results, key=lambda r: r.get("score", 0), reverse=True)

    def format_results(self, results: List[Dict[str, Any]], format_type: str = "default") -> Union[List[Dict[str, Any]], str]:
        if not results:
            return [] if format_type not in ("text", "markdown") else "No results found."

        if format_type == "compact":
            return [
                {
                    "title": r.get("title", "Untitled"),
                    "url": r.get("url", ""),
                    "snippet": r.get("relevant_fragment", r.get("snippet", ""))[:100],
                }
                for r in results
            ]
        elif format_type == "text":
            lines = []
            for i, r in enumerate(results, 1):
                lines.append(f"{i}. {r.get('title', 'Untitled')}")
                lines.append(f"   URL: {r.get('url', '')}")
                lines.append(f"   {r.get('relevant_fragment', r.get('snippet', ''))[:150]}")
                lines.append("")
            return "\n".join(lines)
        elif format_type == "markdown":
            lines = []
            for r in results:
                lines.append(f"### [{r.get('title', 'Untitled')}]({r.get('url', '')})")
                lines.append(f"{r.get('relevant_fragment', r.get('snippet', ''))}")
                lines.append(f"*Source: {r.get('domain', '')}*")
                lines.append("")
            return "\n".join(lines)
        else:
            return results


class _Ctx:
    """Minimal context with logger to satisfy existing tool signatures."""

    def __init__(self) -> None:
        self.logger = logger


_ctx = _Ctx()
_search_tool = InternetSearchTool(max_retries=3)
_result_processor = SearchResultProcessor(max_results=10)


@mcp.tool()
async def search(
    query: str,
    context: Optional[Dict[str, Any]] = None,
    max_results: int = 10,
    requires_human: bool = False,  # kept for parity with other MCP tools
    mcp_context: Context | None = None,
) -> Dict[str, Any]:
    """
    Run an internet search using Kalevent's local tooling.
    """
    if not query or not isinstance(query, str):
        raise ToolError("query is required")

    _result_processor.max_results = max_results or _result_processor.max_results

    try:
        raw_results = await _search_tool.search(_ctx, query, context)
        processed = _result_processor.process_results(_ctx, raw_results, query)
        sources = {r.get("source") for r in processed if isinstance(r, dict) and r.get("source")}
        source_label = "mixed" if len(sources) > 1 else (sources.pop() if sources else "searxng")
        return {
            "query": query,
            "results": processed,
            "count": len(processed),
            "source": source_label,
            "context_applied": bool(context),
        }
    except Exception as exc:
        logger.exception("search_mcp failed for query '%s': %s", query, exc)
        raise ToolError(f"search failed: {exc}") from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
