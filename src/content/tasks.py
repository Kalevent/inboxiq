"""
Celery tasks for Content Generation Agent

Automated tasks for:
- Weekly blog post generation
- On-demand content creation
- SEO optimization
- Publishing automation
"""
import os
import json
from datetime import datetime
from celery import shared_task
import markdown

from src.extensions import db
from src.models import BlogPost, GeneratedContent, PitchedBlogTopic

# Import DSPy modules
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


def initialize_dspy():
    """Initialize DSPy with LLM configuration for content generation."""
    if not DSPY_AVAILABLE:
        raise RuntimeError("DSPy not available")

    # Configure DSPy with content-generation-specific settings
    # (higher max_tokens than the centralized config which is for triage)
    provider = os.getenv("DSPY_PROVIDER", "openai").strip().lower()
    model = os.getenv("DSPY_MODEL", "gpt-4o-mini")

    # Use DSPy 3.x LM API with content-appropriate settings
    if "/" not in model:
        model = f"{provider}/{model}"

    lm = dspy.LM(model=model, max_tokens=3000, temperature=0.7)
    dspy.settings.configure(lm=lm)


def _generate_hero_image(title: str, topic: dict) -> tuple[str, str]:
    """
    Generate hero image using DALL-E 3 and upload to S3.

    Args:
        title: Blog post title
        topic: Topic object with keywords and context

    Returns:
        Tuple of (image_url, alt_text)
    """
    import openai
    import requests
    from src.uploads import upload_bytes, build_public_url

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    client = openai.OpenAI(api_key=openai_api_key)

    # Craft image prompt based on blog topic
    keyword = topic.get("target_keyword", "business automation")
    angle = topic.get("angle", "professional")

    image_prompt = f"""Professional hero image for a blog post about {keyword}.
Style: Modern, clean, professional business illustration.
Theme: {title}
Mood: Innovative, trustworthy, data-driven.
No text or words in the image.
Perspective: Wide angle, suitable for blog header (16:9 aspect ratio feel).
Colors: Blue, purple, white tones - corporate but approachable."""

    # Generate image with DALL-E 3
    response = client.images.generate(
        model="dall-e-3",
        prompt=image_prompt,
        size="1024x1024",
        quality="standard",
        n=1
    )

    image_url = response.data[0].url

    # Download image
    img_response = requests.get(image_url, timeout=30)
    img_response.raise_for_status()
    image_bytes = img_response.content

    # Upload to S3
    from datetime import datetime
    slug_safe = title.lower().replace(" ", "-")[:50]
    key = f"blog/heroes/{datetime.now().strftime('%Y%m%d')}-{slug_safe}.png"

    upload_bytes(
        key=key,
        data=image_bytes,
        content_type="image/png",
        content_disposition=f'inline; filename="{slug_safe}.png"'
    )

    public_url = build_public_url(key)
    alt_text = f"Hero image for {title}"

    return public_url, alt_text


@shared_task(name="content.generate_blog_post")
def generate_blog_post(
    niche: str = "Revenue Operations",
    audience: str = "VP Revenue Operations, B2B SaaS, 100-500 employees",
    topic_index: int = 0,
    auto_publish: bool = False
):
    """
    Generate a full blog post using DSPy content pipeline.

    Args:
        niche: Blog niche
        audience: Target audience
        topic_index: Which topic to use from generated list
        auto_publish: Auto-publish (default: False, requires review)

    Returns:
        Dict with generated content ID and details
    """
    initialize_dspy()

    try:
        # 1. Generate topics
        topic_module = TopicGeneratorModule()
        topics_result = topic_module(
            blog_niche=niche,
            target_audience=audience,
            num_topics=5
        )

        topics = json.loads(topics_result.topics)
        if topic_index >= len(topics):
            topic_index = 0
        selected_topic = topics[topic_index]

        # 2. Create outline
        outline_module = OutlineCreatorModule()
        outline_result = outline_module(
            topic=json.dumps(selected_topic),
            target_word_count=1500,
            content_depth="intermediate"
        )

        # 3. Write content
        writer_module = ContentWriterModule()
        write_result = writer_module(
            outline=outline_result.outline,
            tone="professional",
            include_examples=True,
            include_stats=True
        )

        # 4. Edit content
        editor_module = EditorModule()
        edit_result = editor_module(
            draft=write_result.blog_post_draft,
            editing_focus="all"
        )

        # 5. Optimize SEO
        seo_module = SEOOptimizerModule()
        target_keywords = json.dumps([{
            "keyword": selected_topic["target_keyword"],
            "volume": selected_topic.get("estimated_monthly_searches", 1000),
            "difficulty": selected_topic.get("estimated_difficulty", 50),
            "priority": 1
        }])
        seo_result = seo_module(
            edited_post=edit_result.edited_post,
            target_keywords=target_keywords
        )

        # 6. Generate hero image with DALL-E 3
        hero_image_url = None
        hero_image_alt = None
        try:
            hero_image_url, hero_image_alt = _generate_hero_image(
                title=seo_result.meta_title,
                topic=selected_topic
            )
        except Exception as img_exc:
            # Don't fail the whole task if image generation fails
            import logging
            logging.getLogger(__name__).warning("Hero image generation failed: %s", img_exc)

        # 7. Save to database
        generated_content = GeneratedContent(
            content_type="blog_post",
            title=seo_result.meta_title,
            slug=seo_result.slug,
            content=seo_result.optimized_post,
            meta_data=json.dumps({
                "meta_title": seo_result.meta_title,
                "meta_description": seo_result.meta_description,
                "target_keywords": json.loads(target_keywords),
                "seo_score": seo_result.seo_score,
                "word_count": write_result.word_count
            }),
            generation_pipeline=json.dumps({
                "topic_output": selected_topic,
                "outline_output": json.loads(outline_result.outline),
                "writer_output": {
                    "word_count": write_result.word_count,
                    "readability_score": write_result.readability_score
                },
                "editor_output": {
                    "changes_summary": edit_result.changes_summary,
                    "improvement_score": edit_result.improvement_score
                },
                "seo_output": {
                    "seo_score": seo_result.seo_score,
                    "optimization_notes": seo_result.optimization_notes
                }
            }),
            dspy_version="1.0.0",
            status="draft",
            funnel_stage=selected_topic.get("target_stage", "discovery"),
            target_audience_json=json.dumps({"persona": audience}),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(generated_content)
        db.session.flush()

        # Convert markdown to HTML and sanitize against XSS
        from src.sanitize import sanitize_html

        md_converter = markdown.Markdown(extensions=['extra', 'codehilite', 'toc'])
        raw_html = md_converter.convert(seo_result.optimized_post)

        # Sanitize HTML to prevent XSS attacks (defense-in-depth)
        content_html = sanitize_html(raw_html)

        # Calculate read time (average reading speed: 200 words/minute)
        import math
        read_time = math.ceil(write_result.word_count / 200) if write_result.word_count else 1

        # Create blog post entry
        blog_post = BlogPost(
            title=seo_result.meta_title,
            slug=seo_result.slug,
            status="ready" if not auto_publish else "published",
            funnel_stage=selected_topic.get("target_stage", "discovery"),
            primary_keyword=selected_topic["target_keyword"],
            secondary_keywords=selected_topic.get("secondary_keywords", []),
            content_html=content_html,
            markdown=seo_result.optimized_post,
            meta_description=seo_result.meta_description,
            excerpt=seo_result.meta_description,  # Use meta description as excerpt
            hero_image_url=hero_image_url,
            hero_image_alt=hero_image_alt,
            word_count=write_result.word_count,
            read_time_minutes=read_time,
            generated_content_id=generated_content.id,
            auto_generated=True,
            dspy_quality_score=float(seo_result.seo_score) / 100.0,
            published_at=datetime.now() if auto_publish else None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(blog_post)
        db.session.commit()

        # Send email notification for review
        try:
            from src.email_utils import send_content_review_email
            import os

            notification_email = os.getenv("ADMIN_EMAILS", "support@kalevent.com").split(",")[0].strip()
            blog_url = f"{os.getenv('API_BASE_URL', 'https://api.kalevent.com')}/blog/{seo_result.slug}"

            send_content_review_email(
                to_email=notification_email,
                title=seo_result.meta_title,
                slug=seo_result.slug,
                content_preview=seo_result.optimized_post[:500],
                seo_score=seo_result.seo_score,
                word_count=write_result.word_count,
                readability_score=write_result.readability_score,
                blog_url=blog_url
            )
        except Exception as e:
            # Don't fail the whole task if email fails
            import logging
            logging.getLogger(__name__).warning("Failed to send content review email: %s", e)

        return {
            "success": True,
            "generated_content_id": generated_content.id,
            "blog_post_id": blog_post.id,
            "title": seo_result.meta_title,
            "slug": seo_result.slug,
            "word_count": write_result.word_count,
            "seo_score": seo_result.seo_score,
            "status": blog_post.status,
            "pipeline_summary": {
                "topics_generated": len(topics),
                "readability_score": write_result.readability_score,
                "improvement_score": edit_result.improvement_score,
                "seo_optimizations": seo_result.optimization_notes
            }
        }

    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}


@shared_task(name="content.generate_weekly_posts")
def generate_weekly_posts(num_posts: int = 3):
    """
    Scheduled task: Generate weekly blog posts.

    Runs every Monday at 6 AM.

    Args:
        num_posts: Number of posts to generate (default: 3)

    Returns:
        Dict with list of generated posts
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "num_posts_requested": num_posts,
        "posts_generated": [],
        "errors": []
    }

    for i in range(num_posts):
        try:
            result = generate_blog_post(
                topic_index=i,
                auto_publish=False  # Always require review
            )

            if "error" not in result:
                results["posts_generated"].append(result)
            else:
                results["errors"].append(result["error"])

        except Exception as e:
            results["errors"].append(f"Post {i+1}: {str(e)}")

    return results


@shared_task(name="content.optimize_existing_post")
def optimize_existing_post(blog_post_id: str):
    """
    Re-optimize existing blog post for SEO.

    Args:
        blog_post_id: BlogPost UUID

    Returns:
        Dict with optimization results
    """
    initialize_dspy()

    blog_post = db.session.query(BlogPost).filter(BlogPost.id == blog_post_id).first()
    if not blog_post:
        return {"error": f"Blog post {blog_post_id} not found"}

    try:
        seo_module = SEOOptimizerModule()

        target_keywords = json.dumps([{
            "keyword": blog_post.primary_keyword,
            "volume": 1000,
            "difficulty": 50,
            "priority": 1
        }])

        result = seo_module(
            edited_post=blog_post.markdown or blog_post.content_html or "",
            target_keywords=target_keywords
        )

        # Update blog post
        blog_post.markdown = result.optimized_post
        blog_post.meta_description = result.meta_description
        blog_post.slug = result.slug
        blog_post.dspy_quality_score = float(result.seo_score) / 100.0
        blog_post.updated_at = datetime.now()

        db.session.commit()

        return {
            "success": True,
            "blog_post_id": blog_post_id,
            "seo_score": result.seo_score,
            "meta_title": result.meta_title,
            "meta_description": result.meta_description,
            "optimization_notes": result.optimization_notes
        }

    except Exception as e:
        db.session.rollback()
        return {"error": str(e)}


@shared_task(name="content.content_generation_job")
def content_generation_job():
    """
    Main content generation orchestration job.

    Runs scheduled content generation tasks.
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "weekly_posts": None,
        "errors": []
    }

    try:
        # Generate weekly posts (only on Mondays)
        if datetime.now().weekday() == 0:  # Monday
            results["weekly_posts"] = generate_weekly_posts(num_posts=3)

        return results

    except Exception as e:
        results["errors"].append(str(e))
        return results


@shared_task(name="content.generate_blog_from_pitched_topic")
def generate_blog_from_pitched_topic(topic_id: str):
    """
    Generate blog post from a manually pitched topic.

    Args:
        topic_id: PitchedBlogTopic UUID

    Returns:
        Dict with generated content ID and details
    """
    initialize_dspy()

    pitched_topic = db.session.query(PitchedBlogTopic).filter(
        PitchedBlogTopic.id == topic_id
    ).first()

    if not pitched_topic:
        return {"error": f"Pitched topic {topic_id} not found"}

    try:
        # Convert pitched topic into the format expected by content generation
        selected_topic = {
            "title": pitched_topic.title,
            "description": pitched_topic.description or "",
            "target_keyword": pitched_topic.target_keyword or pitched_topic.title.lower(),
            "secondary_keywords": pitched_topic.secondary_keywords or [],
            "target_stage": pitched_topic.funnel_stage or "discovery",
            "angle": "professional",
            "estimated_monthly_searches": 1000,
            "estimated_difficulty": 50
        }

        # 1. Create outline
        outline_module = OutlineCreatorModule()
        outline_result = outline_module(
            topic=json.dumps(selected_topic),
            target_word_count=1500,
            content_depth="intermediate"
        )

        # 2. Write content
        writer_module = ContentWriterModule()
        write_result = writer_module(
            outline=outline_result.outline,
            tone="professional",
            include_examples=True,
            include_stats=True
        )

        # 3. Edit content
        editor_module = EditorModule()
        edit_result = editor_module(
            draft=write_result.blog_post_draft,
            editing_focus="all"
        )

        # 4. Optimize SEO
        seo_module = SEOOptimizerModule()
        target_keywords = json.dumps([{
            "keyword": selected_topic["target_keyword"],
            "volume": selected_topic.get("estimated_monthly_searches", 1000),
            "difficulty": selected_topic.get("estimated_difficulty", 50),
            "priority": 1
        }])
        seo_result = seo_module(
            edited_post=edit_result.edited_post,
            target_keywords=target_keywords
        )

        # 5. Generate hero image with DALL-E 3
        hero_image_url = None
        hero_image_alt = None
        try:
            hero_image_url, hero_image_alt = _generate_hero_image(
                title=seo_result.meta_title,
                topic=selected_topic
            )
        except Exception as img_exc:
            import logging
            logging.getLogger(__name__).warning("Hero image generation failed: %s", img_exc)

        # 6. Save to database
        generated_content = GeneratedContent(
            content_type="blog_post",
            title=seo_result.meta_title,
            slug=seo_result.slug,
            content=seo_result.optimized_post,
            meta_data=json.dumps({
                "meta_title": seo_result.meta_title,
                "meta_description": seo_result.meta_description,
                "target_keywords": json.loads(target_keywords),
                "seo_score": seo_result.seo_score,
                "word_count": write_result.word_count,
                "pitched_topic_id": topic_id
            }),
            generation_pipeline=json.dumps({
                "pitched_topic": selected_topic,
                "outline_output": json.loads(outline_result.outline),
                "writer_output": {
                    "word_count": write_result.word_count,
                    "readability_score": write_result.readability_score
                },
                "editor_output": {
                    "changes_summary": edit_result.changes_summary,
                    "improvement_score": edit_result.improvement_score
                },
                "seo_output": {
                    "seo_score": seo_result.seo_score,
                    "optimization_notes": seo_result.optimization_notes
                }
            }),
            dspy_version="1.0.0",
            status="draft",
            funnel_stage=pitched_topic.funnel_stage or "discovery",
            target_audience_json=json.dumps({
                "persona": pitched_topic.target_audience or "Business professionals"
            }),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(generated_content)
        db.session.flush()

        # Convert markdown to HTML and sanitize against XSS
        from src.sanitize import sanitize_html

        md_converter = markdown.Markdown(extensions=['extra', 'codehilite', 'toc'])
        raw_html = md_converter.convert(seo_result.optimized_post)
        content_html = sanitize_html(raw_html)

        # Calculate read time
        import math
        read_time = math.ceil(write_result.word_count / 200) if write_result.word_count else 1

        # Create blog post entry
        blog_post = BlogPost(
            title=seo_result.meta_title,
            slug=seo_result.slug,
            status="ready",
            funnel_stage=pitched_topic.funnel_stage or "discovery",
            primary_keyword=selected_topic["target_keyword"],
            secondary_keywords=selected_topic.get("secondary_keywords", []),
            content_html=content_html,
            markdown=seo_result.optimized_post,
            meta_description=seo_result.meta_description,
            excerpt=seo_result.meta_description,
            hero_image_url=hero_image_url,
            hero_image_alt=hero_image_alt,
            word_count=write_result.word_count,
            read_time_minutes=read_time,
            generated_content_id=generated_content.id,
            auto_generated=True,
            dspy_quality_score=float(seo_result.seo_score) / 100.0,
            published_at=None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        db.session.add(blog_post)

        # Update pitched topic status
        pitched_topic.status = "generated"
        pitched_topic.generated_content_id = generated_content.id
        pitched_topic.updated_at = datetime.now()

        db.session.commit()

        # Send email notification
        try:
            from src.email_utils import send_content_review_email

            notification_email = os.getenv("ADMIN_EMAILS", "support@kalevent.com").split(",")[0].strip()
            blog_url = f"{os.getenv('API_BASE_URL', 'https://api.kalevent.com')}/blog/{seo_result.slug}"

            send_content_review_email(
                to_email=notification_email,
                title=seo_result.meta_title,
                slug=seo_result.slug,
                content_preview=seo_result.optimized_post[:500],
                seo_score=seo_result.seo_score,
                word_count=write_result.word_count,
                readability_score=write_result.readability_score,
                blog_url=blog_url
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to send content review email: %s", e)

        return {
            "success": True,
            "pitched_topic_id": topic_id,
            "generated_content_id": generated_content.id,
            "blog_post_id": blog_post.id,
            "title": seo_result.meta_title,
            "slug": seo_result.slug,
            "word_count": write_result.word_count,
            "seo_score": seo_result.seo_score,
            "status": blog_post.status
        }

    except Exception as e:
        db.session.rollback()
        # Mark pitched topic as failed
        try:
            pitched_topic.pitch_notes = f"{pitched_topic.pitch_notes or ''}\n\nGeneration failed: {str(e)}".strip()
            db.session.commit()
        except:
            pass
        return {"error": str(e)}
