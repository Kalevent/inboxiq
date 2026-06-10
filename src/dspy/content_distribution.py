"""
DSPy modules for intelligent content distribution.

Provides AI-powered decision-making for:
- Optimal posting times based on audience engagement
- Platform selection (LinkedIn vs Twitter vs email)
- Content optimization per platform
- Audience segmentation and personalization
"""
from __future__ import annotations

import dspy
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class PostingTimeOptimizer(dspy.Signature):
    """
    Determine the optimal time to post content based on audience behavior.

    Analyzes historical engagement data to recommend best posting times.
    """
    content_type = dspy.InputField(desc="Type of content (blog_post, case_study, announcement)")
    funnel_stage = dspy.InputField(desc="Funnel stage (VISITS, DISCOVERY, CONSIDERATION, CONVERSION, RETENTION)")
    target_audience = dspy.InputField(desc="Target audience description (e.g., 'VP Revenue Operations, B2B SaaS')")
    historical_engagement = dspy.InputField(desc="JSON of past engagement by hour/day: {hour: avg_engagement_rate}")
    current_datetime = dspy.InputField(desc="Current datetime ISO string")

    optimal_hour = dspy.OutputField(desc="Hour of day to post (0-23, UTC)")
    optimal_day_of_week = dspy.OutputField(desc="Day of week (0=Monday, 6=Sunday)")
    reasoning = dspy.OutputField(desc="Brief explanation of why this time is optimal")
    confidence = dspy.OutputField(desc="Confidence score 1-10")


class PlatformSelector(dspy.Signature):
    """
    Select optimal social media platforms for content distribution.

    Analyzes content type, audience, and goals to recommend platforms.
    """
    content_title = dspy.InputField(desc="Content title")
    content_summary = dspy.InputField(desc="Brief content summary (1-2 sentences)")
    funnel_stage = dspy.InputField(desc="Funnel stage (VISITS, DISCOVERY, CONSIDERATION, CONVERSION)")
    target_audience = dspy.InputField(desc="Target audience ICP characteristics")
    content_goal = dspy.InputField(desc="Primary goal (awareness, education, conversion, retention)")

    linkedin = dspy.OutputField(desc="'yes' or 'no' - Should post to LinkedIn")
    twitter = dspy.OutputField(desc="'yes' or 'no' - Should post to Twitter")
    email_newsletter = dspy.OutputField(desc="'yes' or 'no' - Should send email newsletter")
    reasoning = dspy.OutputField(desc="Explanation of platform selection strategy")


class ContentOptimizer(dspy.Signature):
    """
    Optimize blog content for specific social media platform.

    Adapts tone, length, and CTAs for platform best practices.
    """
    blog_title = dspy.InputField(desc="Original blog post title")
    blog_summary = dspy.InputField(desc="Blog post summary or excerpt")
    primary_keyword = dspy.InputField(desc="Primary SEO keyword")
    target_platform = dspy.InputField(desc="Platform to optimize for (linkedin, twitter, email)")
    target_audience = dspy.InputField(desc="Audience ICP")

    optimized_text = dspy.OutputField(desc="Platform-optimized post text with emojis and formatting")
    call_to_action = dspy.OutputField(desc="Platform-appropriate CTA")
    hashtags = dspy.OutputField(desc="Relevant hashtags (comma-separated, 3-5 max)")


class AudienceSegmenter(dspy.Signature):
    """
    Segment audience for personalized content delivery.

    Analyzes user attributes to create targeted content variations.
    """
    content_topic = dspy.InputField(desc="Main topic of the content")
    available_segments = dspy.InputField(desc="Available audience segments (JSON list of {industry, company_size, role})")
    content_summary = dspy.InputField(desc="Content summary")

    priority_segments = dspy.OutputField(desc="Top 3 segments to target (comma-separated)")
    personalization_angles = dspy.OutputField(desc="How to personalize for each segment (JSON)")
    reasoning = dspy.OutputField(desc="Why these segments are prioritized")


class DistributionIntelligenceModule(dspy.Module):
    """
    Complete content distribution intelligence module.

    Combines timing optimization, platform selection, content optimization,
    and audience segmentation into a cohesive distribution strategy.
    """

    def __init__(self):
        super().__init__()
        self.posting_time = dspy.ChainOfThought(PostingTimeOptimizer)
        self.platform_select = dspy.ChainOfThought(PlatformSelector)
        self.content_optimize = dspy.ChainOfThought(ContentOptimizer)
        self.audience_segment = dspy.ChainOfThought(AudienceSegmenter)

    def forward(
        self,
        blog_title: str,
        blog_summary: str,
        funnel_stage: str,
        target_audience: str,
        primary_keyword: Optional[str] = None,
        content_type: str = "blog_post",
        content_goal: str = "awareness"
    ) -> Dict[str, Any]:
        """
        Generate comprehensive distribution strategy.

        Args:
            blog_title: Blog post title
            blog_summary: Summary/excerpt
            funnel_stage: VISITS, DISCOVERY, CONSIDERATION, etc.
            target_audience: ICP description
            primary_keyword: SEO keyword
            content_type: Type of content
            content_goal: Primary objective

        Returns:
            Distribution strategy with timing, platforms, optimized content
        """
        # 1. Determine optimal posting time
        # TODO: Pull real historical engagement data from database
        historical_engagement = {
            "9": 0.45, "10": 0.62, "11": 0.58,  # Morning engagement
            "13": 0.51, "14": 0.67, "15": 0.72,  # Afternoon peak
            "16": 0.59, "17": 0.48  # Late afternoon
        }

        timing = self.posting_time(
            content_type=content_type,
            funnel_stage=funnel_stage,
            target_audience=target_audience,
            historical_engagement=str(historical_engagement),
            current_datetime=datetime.now(timezone.utc).isoformat()
        )

        # 2. Select optimal platforms
        platforms = self.platform_select(
            content_title=blog_title,
            content_summary=blog_summary,
            funnel_stage=funnel_stage,
            target_audience=target_audience,
            content_goal=content_goal
        )

        # 3. Optimize content for each selected platform
        optimized_content = {}

        if platforms.linkedin.lower() == "yes":
            linkedin_content = self.content_optimize(
                blog_title=blog_title,
                blog_summary=blog_summary,
                primary_keyword=primary_keyword or "",
                target_platform="linkedin",
                target_audience=target_audience
            )
            optimized_content["linkedin"] = {
                "text": linkedin_content.optimized_text,
                "cta": linkedin_content.call_to_action,
                "hashtags": linkedin_content.hashtags
            }

        if platforms.twitter.lower() == "yes":
            twitter_content = self.content_optimize(
                blog_title=blog_title,
                blog_summary=blog_summary,
                primary_keyword=primary_keyword or "",
                target_platform="twitter",
                target_audience=target_audience
            )
            optimized_content["twitter"] = {
                "text": twitter_content.optimized_text,
                "cta": twitter_content.call_to_action,
                "hashtags": twitter_content.hashtags
            }

        if platforms.email_newsletter.lower() == "yes":
            email_content = self.content_optimize(
                blog_title=blog_title,
                blog_summary=blog_summary,
                primary_keyword=primary_keyword or "",
                target_platform="email",
                target_audience=target_audience
            )
            optimized_content["email"] = {
                "text": email_content.optimized_text,
                "cta": email_content.call_to_action,
                "subject_line": f"📬 {blog_title}"
            }

        # 4. Segment audience for personalization
        # TODO: Pull real segments from database
        available_segments = [
            {"industry": "Healthcare", "company_size": "100-500", "role": "Operations Director"},
            {"industry": "Insurance", "company_size": "500-2000", "role": "Claims Manager"},
            {"industry": "B2B SaaS", "company_size": "50-200", "role": "Customer Success VP"}
        ]

        segmentation = self.audience_segment(
            content_topic=blog_title,
            available_segments=str(available_segments),
            content_summary=blog_summary
        )

        return {
            "timing": {
                "optimal_hour": int(timing.optimal_hour),
                "optimal_day_of_week": int(timing.optimal_day_of_week),
                "reasoning": timing.reasoning,
                "confidence": int(timing.confidence)
            },
            "platforms": {
                "linkedin": platforms.linkedin.lower() == "yes",
                "twitter": platforms.twitter.lower() == "yes",
                "email": platforms.email_newsletter.lower() == "yes",
                "reasoning": platforms.reasoning
            },
            "optimized_content": optimized_content,
            "segmentation": {
                "priority_segments": segmentation.priority_segments,
                "personalization": segmentation.personalization_angles,
                "reasoning": segmentation.reasoning
            }
        }


# Convenience functions for direct usage

def get_optimal_posting_time(
    content_type: str,
    funnel_stage: str,
    target_audience: str
) -> Dict[str, Any]:
    """
    Get optimal posting time for content.

    Returns:
        {
            "optimal_hour": 14,
            "optimal_day_of_week": 2,
            "reasoning": "...",
            "confidence": 8
        }
    """
    module = DistributionIntelligenceModule()

    # Placeholder - in production, load compiled module
    result = module.forward(
        blog_title="Sample Title",
        blog_summary="Sample summary",
        funnel_stage=funnel_stage,
        target_audience=target_audience,
        content_type=content_type
    )

    return result["timing"]


def get_platform_strategy(
    blog_title: str,
    blog_summary: str,
    funnel_stage: str,
    target_audience: str,
    content_goal: str = "awareness"
) -> Dict[str, Any]:
    """
    Get platform distribution strategy.

    Returns:
        {
            "linkedin": True,
            "twitter": False,
            "email": True,
            "reasoning": "..."
        }
    """
    module = DistributionIntelligenceModule()

    result = module.forward(
        blog_title=blog_title,
        blog_summary=blog_summary,
        funnel_stage=funnel_stage,
        target_audience=target_audience,
        content_goal=content_goal
    )

    return result["platforms"]


def optimize_for_platform(
    blog_title: str,
    blog_summary: str,
    platform: str,
    target_audience: str,
    primary_keyword: Optional[str] = None
) -> Dict[str, str]:
    """
    Optimize content for specific platform.

    Args:
        platform: 'linkedin', 'twitter', or 'email'

    Returns:
        {
            "text": "Optimized post text...",
            "cta": "Read more →",
            "hashtags": "#AI #Automation"
        }
    """
    optimizer = dspy.ChainOfThought(ContentOptimizer)

    result = optimizer(
        blog_title=blog_title,
        blog_summary=blog_summary,
        primary_keyword=primary_keyword or "",
        target_platform=platform,
        target_audience=target_audience
    )

    return {
        "text": result.optimized_text,
        "cta": result.call_to_action,
        "hashtags": result.hashtags
    }
