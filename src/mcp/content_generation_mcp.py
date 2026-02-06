"""
Content Generation MCP server for Leads Funnel v2.0

Exposes DSPy content generation modules as MCP tools for autonomous content creation.
Provides full pipeline: topic generation → outline → writing → editing → SEO.

Tools:
- generate_topics: Generate blog topic ideas
- create_outline: Create structured blog outline
- write_content: Write full blog post draft
- edit_content: Edit and polish draft
- optimize_seo: Optimize for search engines
- generate_full_blog_post: End-to-end generation (all steps combined)

Env:
- DSPY_ARTIFACTS_DIR: Directory containing compiled DSPy models (default: ./dspy_artifacts)
- DSPY_MODEL: LLM model for DSPy (default: gpt-4)
- OPENAI_API_KEY: OpenAI API key for DSPy
"""
from __future__ import annotations

import os
import sys
import json
from typing import Any, Dict, Optional

try:
    from mcp.server.fastmcp import FastMCP, Context, ToolError
except ImportError:
    from mcp.server.fastmcp import FastMCP, Context
    try:
        from mcp.types import ToolError
    except ImportError:
        class ToolError(Exception):
            pass

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

try:
    import dspy
    from src.dspy.content import (
        TopicGeneratorModule,
        OutlineCreatorModule,
        ContentWriterModule,
        EditorModule,
        SEOOptimizerModule
    )
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False


mcp = FastMCP("content-generation-mcp")

DSPY_ARTIFACTS_DIR = os.getenv("DSPY_ARTIFACTS_DIR", "./dspy_artifacts")
DSPY_MODEL = os.getenv("DSPY_MODEL", "gpt-4")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def initialize_dspy():
    """Initialize DSPy configuration."""
    if not DSPY_AVAILABLE:
        raise ToolError("DSPy not available. Install: pip install dspy-ai")

    if not OPENAI_API_KEY:
        raise ToolError("OPENAI_API_KEY environment variable required")

    lm = dspy.OpenAI(model=DSPY_MODEL, api_key=OPENAI_API_KEY, max_tokens=3000)
    dspy.settings.configure(lm=lm)


def load_compiled_module(module_name: str):
    """
    Load compiled DSPy module from artifacts directory.
    If not found, returns uncompiled module.

    Args:
        module_name: Module name (e.g., 'topic_generator')

    Returns:
        Compiled or uncompiled DSPy module
    """
    artifact_path = os.path.join(DSPY_ARTIFACTS_DIR, f"{module_name}_compiled.pkl")

    # If compiled artifact exists, load it
    if os.path.exists(artifact_path):
        try:
            import pickle
            with open(artifact_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Warning: Failed to load compiled module {module_name}: {e}")

    # Fall back to uncompiled module
    module_map = {
        'topic_generator': TopicGeneratorModule,
        'outline_creator': OutlineCreatorModule,
        'content_writer': ContentWriterModule,
        'editor': EditorModule,
        'seo_optimizer': SEOOptimizerModule
    }

    module_class = module_map.get(module_name)
    if not module_class:
        raise ToolError(f"Unknown module: {module_name}")

    initialize_dspy()
    return module_class()


@mcp.tool()
def generate_topics(
    blog_niche: str,
    target_audience: str,
    num_topics: int = 10,
    existing_topics: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate blog topics using DSPy TopicGeneratorModule.

    Args:
        blog_niche: Blog niche/vertical
        target_audience: Target audience persona
        num_topics: Number of topics to generate (default: 10)
        existing_topics: JSON array of existing topics to avoid duplicates (optional)

    Returns:
        Dict with topics array and reasoning
    """
    try:
        module = load_compiled_module("topic_generator")
        result = module(
            blog_niche=blog_niche,
            target_audience=target_audience,
            num_topics=num_topics,
            existing_topics=existing_topics
        )

        return {
            "topics": json.loads(result.topics),
            "reasoning": result.reasoning
        }
    except Exception as e:
        raise ToolError(f"Failed to generate topics: {e}")


@mcp.tool()
def create_outline(
    topic: str,  # JSON string
    target_word_count: int = 1500,
    content_depth: str = "intermediate"
) -> Dict[str, Any]:
    """
    Create blog post outline using DSPy OutlineCreatorModule.

    Args:
        topic: JSON topic object from generate_topics
        target_word_count: Target word count (default: 1500)
        content_depth: Content depth (beginner | intermediate | expert)

    Returns:
        Dict with outline, estimated_word_count, research_sources
    """
    try:
        module = load_compiled_module("outline_creator")
        result = module(
            topic=topic,
            target_word_count=target_word_count,
            content_depth=content_depth
        )

        return {
            "outline": json.loads(result.outline),
            "estimated_word_count": result.estimated_word_count,
            "research_sources": result.research_sources
        }
    except Exception as e:
        raise ToolError(f"Failed to create outline: {e}")


@mcp.tool()
def write_content(
    outline: str,  # JSON string
    tone: str = "professional",
    include_examples: bool = True
) -> Dict[str, Any]:
    """
    Write full blog post using DSPy ContentWriterModule.

    Args:
        outline: JSON outline from create_outline
        tone: Writing tone (professional | conversational | technical | storytelling)
        include_examples: Include real-world examples (default: True)

    Returns:
        Dict with draft, word_count, readability_score
    """
    try:
        module = load_compiled_module("content_writer")
        result = module(
            outline=outline,
            tone=tone,
            include_examples=include_examples
        )

        return {
            "draft": result.blog_post_draft,
            "word_count": result.word_count,
            "readability_score": result.readability_score,
            "sections_written": result.sections_written
        }
    except Exception as e:
        raise ToolError(f"Failed to write content: {e}")


@mcp.tool()
def edit_content(
    draft: str,
    style_guide: Optional[str] = None,
    editing_focus: str = "all"
) -> Dict[str, Any]:
    """
    Edit blog post using DSPy EditorModule.

    Args:
        draft: Markdown draft from write_content
        style_guide: Style guide rules (optional)
        editing_focus: Focus areas (grammar | clarity | engagement | all)

    Returns:
        Dict with edited_post, changes_summary, improvement_score
    """
    try:
        module = load_compiled_module("editor")
        result = module(
            draft=draft,
            style_guide=style_guide or "",
            editing_focus=editing_focus
        )

        return {
            "edited_post": result.edited_post,
            "changes_summary": result.changes_summary,
            "improvement_score": result.improvement_score,
            "remaining_issues": result.remaining_issues
        }
    except Exception as e:
        raise ToolError(f"Failed to edit content: {e}")


@mcp.tool()
def optimize_seo(
    edited_post: str,
    target_keywords: str  # JSON array
) -> Dict[str, Any]:
    """
    Optimize blog post for SEO using DSPy SEOOptimizerModule.

    Args:
        edited_post: Edited markdown post
        target_keywords: JSON array of keywords with volume/difficulty

    Returns:
        Dict with optimized_post, meta_title, meta_description, slug, seo_score
    """
    try:
        module = load_compiled_module("seo_optimizer")
        result = module(
            edited_post=edited_post,
            target_keywords=target_keywords
        )

        return {
            "optimized_post": result.optimized_post,
            "meta_title": result.meta_title,
            "meta_description": result.meta_description,
            "slug": result.slug,
            "seo_score": result.seo_score,
            "keyword_density": json.loads(result.keyword_density),
            "optimization_notes": result.optimization_notes
        }
    except Exception as e:
        raise ToolError(f"Failed to optimize SEO: {e}")


@mcp.tool()
def generate_full_blog_post(
    niche: str,
    audience: str,
    topic_index: int = 0,
    tone: str = "professional"
) -> Dict[str, Any]:
    """
    End-to-end: Generate topic → outline → draft → edit → optimize.

    Args:
        niche: Blog niche
        audience: Target audience
        topic_index: Which topic to use from generated list (default: 0)
        tone: Writing tone (default: professional)

    Returns:
        Dict with complete blog post and all pipeline outputs
    """
    try:
        # 1. Generate topics
        topics_result = generate_topics(niche, audience, num_topics=3)
        if topic_index >= len(topics_result["topics"]):
            topic_index = 0
        selected_topic = topics_result["topics"][topic_index]

        # 2. Create outline
        outline_result = create_outline(json.dumps(selected_topic))

        # 3. Write content
        write_result = write_content(
            json.dumps(outline_result["outline"]),
            tone=tone
        )

        # 4. Edit content
        edit_result = edit_content(write_result["draft"])

        # 5. Optimize SEO
        target_keywords = json.dumps([
            {
                "keyword": selected_topic["target_keyword"],
                "volume": selected_topic.get("estimated_monthly_searches", 1000),
                "difficulty": selected_topic.get("estimated_difficulty", 50),
                "priority": 1
            }
        ])
        seo_result = optimize_seo(edit_result["edited_post"], target_keywords)

        return {
            "success": True,
            "topic": selected_topic,
            "outline": outline_result["outline"],
            "final_post": seo_result["optimized_post"],
            "meta_title": seo_result["meta_title"],
            "meta_description": seo_result["meta_description"],
            "slug": seo_result["slug"],
            "seo_score": seo_result["seo_score"],
            "word_count": write_result["word_count"],
            "readability_score": write_result["readability_score"],
            "improvement_score": edit_result["improvement_score"],
            "pipeline_summary": {
                "topics_generated": len(topics_result["topics"]),
                "sections_written": write_result["sections_written"],
                "edits_made": edit_result["changes_summary"],
                "seo_optimizations": seo_result["optimization_notes"]
            }
        }
    except Exception as e:
        raise ToolError(f"Failed to generate full blog post: {e}")


if __name__ == "__main__":
    mcp.run()
