#!/usr/bin/env python3
"""
Export a blog post from local database to JSON file.

Usage:
    python scripts/export_blog_post.py maximizing-revenue-automation-in-revenue-operations
"""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.app import create_app
from src.models import BlogPost
from src.extensions import db


def export_blog_post(slug: str, output_file: str = None):
    """Export a blog post by slug to JSON file."""
    app = create_app()

    with app.app_context():
        # Query the blog post
        blog_post = db.session.query(BlogPost).filter(BlogPost.slug == slug).first()

        if not blog_post:
            print(f"❌ Blog post with slug '{slug}' not found!")
            sys.exit(1)

        # Convert to dict and add extra info
        data = blog_post.to_dict()

        # Add additional fields that might not be in to_dict()
        data.update({
            "markdown": blog_post.markdown,
            "rendered_html": blog_post.rendered_html,
            "brief_json": blog_post.brief_json,
            "last_prompt": blog_post.last_prompt,
            "meta_description": blog_post.meta_description,
            "canonical_url": blog_post.canonical_url,
            "hero_image_url": blog_post.hero_image_url,
            "hero_image_alt": blog_post.hero_image_alt,
            "word_count": blog_post.word_count,
            "read_time_minutes": blog_post.read_time_minutes,
            "internal_links": blog_post.internal_links or [],
            "generated_content_id": blog_post.generated_content_id,
            "auto_generated": blog_post.auto_generated,
            "dspy_quality_score": blog_post.dspy_quality_score,
        })

        # Default output file
        if not output_file:
            output_file = f"blog_post_{slug}.json"

        # Write to file
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        print(f"✅ Blog post exported to: {output_file}")
        print(f"   Title: {blog_post.title}")
        print(f"   Status: {blog_post.status}")
        print(f"   Published: {blog_post.published_at}")

        return output_file


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/export_blog_post.py <slug> [output_file]")
        print("Example: python scripts/export_blog_post.py maximizing-revenue-automation-in-revenue-operations")
        sys.exit(1)

    slug = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    export_blog_post(slug, output_file)
