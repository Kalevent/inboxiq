#!/usr/bin/env python3
"""
Import a blog post from JSON file to production database.

Usage:
    python scripts/import_blog_post.py blog_post_maximizing-revenue-automation-in-revenue-operations.json
"""
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.app import create_app
from src.models import BlogPost
from src.extensions import db
from uuid import uuid4


def import_blog_post(json_file: str, force: bool = False):
    """Import a blog post from JSON file to database."""
    # Read JSON file
    with open(json_file, 'r') as f:
        data = json.load(f)

    app = create_app()

    with app.app_context():
        # Check if slug already exists
        existing = db.session.query(BlogPost).filter(BlogPost.slug == data['slug']).first()

        if existing and not force:
            print(f"⚠️  Blog post with slug '{data['slug']}' already exists!")
            print(f"   Use --force to overwrite")
            print(f"   Existing ID: {existing.id}")
            sys.exit(1)

        if existing and force:
            print(f"🔄 Updating existing blog post: {existing.id}")
            blog_post = existing
        else:
            print(f"➕ Creating new blog post")
            blog_post = BlogPost()
            # Generate new UUID for production
            blog_post.id = str(uuid4())

        # Update fields
        blog_post.title = data['title']
        blog_post.slug = data['slug']
        blog_post.status = data.get('status', 'published')
        blog_post.funnel_stage = data.get('funnel_stage')
        blog_post.primary_keyword = data.get('primary_keyword')
        blog_post.secondary_keywords = data.get('secondary_keywords', [])
        blog_post.summary = data.get('summary')
        blog_post.excerpt = data.get('excerpt')
        blog_post.content_html = data.get('content_html')
        blog_post.markdown = data.get('markdown')
        blog_post.rendered_html = data.get('rendered_html')
        blog_post.brief_json = data.get('brief_json')
        blog_post.last_prompt = data.get('last_prompt')
        blog_post.meta_description = data.get('meta_description')
        blog_post.canonical_url = data.get('canonical_url')
        blog_post.hero_image_url = data.get('hero_image_url')
        blog_post.hero_image_alt = data.get('hero_image_alt')
        blog_post.word_count = data.get('word_count')
        blog_post.read_time_minutes = data.get('read_time_minutes')
        blog_post.internal_links = data.get('internal_links', [])
        blog_post.auto_generated = data.get('auto_generated', False)
        blog_post.dspy_quality_score = data.get('dspy_quality_score')

        # Handle published_at
        published_at = data.get('published_at')
        if published_at and isinstance(published_at, str):
            blog_post.published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
        elif blog_post.status == 'published' and not blog_post.published_at:
            blog_post.published_at = datetime.utcnow()

        # Note: generated_content_id is intentionally skipped - don't copy FKs across databases

        if not existing:
            db.session.add(blog_post)

        db.session.commit()

        print(f"✅ Blog post imported successfully!")
        print(f"   ID: {blog_post.id}")
        print(f"   Title: {blog_post.title}")
        print(f"   Slug: {blog_post.slug}")
        print(f"   Status: {blog_post.status}")
        print(f"   URL: https://api.kalevent.com/blog/{blog_post.slug}")
        print(f"   URL: https://kalevent.com/blog/{blog_post.slug}")

        return blog_post.id


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_blog_post.py <json_file> [--force]")
        print("Example: python scripts/import_blog_post.py blog_post_maximizing-revenue-automation.json")
        sys.exit(1)

    json_file = sys.argv[1]
    force = '--force' in sys.argv

    if not Path(json_file).exists():
        print(f"❌ File not found: {json_file}")
        sys.exit(1)

    import_blog_post(json_file, force)
