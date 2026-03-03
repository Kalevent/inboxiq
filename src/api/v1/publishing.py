from __future__ import annotations

from flask import jsonify, request
from flask_jwt_extended import jwt_required
from datetime import datetime

from src.extensions import db
from src.models.content import BlogPost

from src.api.v1 import v1
from src.publishing.service import create_blog_draft, list_blogs, publish_blog


def _safe_json() -> dict:
    try:
        return request.get_json() or {}
    except Exception:
        return {}


@v1.route("/publishing/blog/draft", methods=["POST"])
@jwt_required(optional=True)
def api_blog_draft():
    """
    Create a blog draft.

    DEPRECATED for manual use: Use Content Generation Agent for autonomous content creation.

    This endpoint is still used internally by the Content Agent to store generated posts.
    For manual content creation, use: POST /api/v1/content/generate

    Deprecation date: 2026-02-03
    """
    payload = _safe_json()

    # Check if called by Content Agent (has agent_id or auto_generated flag in payload)
    if not payload.get("agent_id") and not payload.get("auto_generated"):
        return jsonify({
            "deprecated": True,
            "message": "Manual blog draft creation is deprecated. Use /api/v1/content/generate for autonomous content creation.",
            "migration_guide": "docs/inboxiq/leads_funnel_v2_plan.md#content-generation-agent-architecture",
            "deprecation_date": "2026-02-03",
            "alternative_endpoint": "/api/v1/content/generate"
        }), 410  # HTTP 410 Gone

    # Allow Content Agent to proceed
    sync = bool(payload.get("sync", True))
    try:
        post, meta = create_blog_draft(payload, run_async=not sync)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to create draft: {exc}"}), 500

    if not sync:
        try:
            from src.publishing.tasks import draft_blog_task

            draft_blog_task.delay(post.id)
            meta["task"] = "queued"
        except Exception as exc:
            meta["task_error"] = str(exc)

    return (
        jsonify(
            {
                "id": post.id,
                "slug": post.slug,
                "status": post.status,
                "queued": bool(meta.get("queued")),
            }
        ),
        201,
    )


@v1.route("/publishing/blog/publish/<post_id>", methods=["POST"])
@jwt_required(optional=True)
def api_blog_publish(post_id: str):
    try:
        post = publish_blog(post_id)
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to publish: {exc}"}), 500
    published_at = post.published_at.isoformat() if post.published_at else None
    return jsonify({"id": post.id, "slug": post.slug, "status": post.status, "published_at": published_at})


@v1.route("/publishing/blog/<post_id>/status", methods=["POST"])
@jwt_required(optional=True)
def api_blog_status(post_id: str):
    data = _safe_json()
    new_status = (data.get("status") or "").strip().lower()
    allowed = {"draft", "in_review", "needs_revision", "approved", "published"}
    if new_status not in allowed:
        return jsonify({"error": f"Invalid status. Allowed: {sorted(allowed)}"}), 400

    post = BlogPost.query.filter_by(id=post_id).first() or BlogPost.query.filter_by(slug=post_id).first()
    if not post:
        return jsonify({"error": "Draft not found"}), 404

    try:
        if new_status == "published":
            # Reuse publish helper (ensures slug/content checks).
            post = publish_blog(post.id)
        else:
            post.status = new_status
            post.updated_at = datetime.utcnow()
            db.session.add(post)
            db.session.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to update status: {exc}"}), 500

    published_at = post.published_at.isoformat() if post.published_at else None
    return jsonify({"id": post.id, "slug": post.slug, "status": post.status, "published_at": published_at})


@v1.route("/publishing/blog/<post_id>/delete", methods=["POST"])
@jwt_required(optional=True)
def api_blog_delete(post_id: str):
    post = BlogPost.query.filter_by(id=post_id).first() or BlogPost.query.filter_by(slug=post_id).first()
    if not post:
        return jsonify({"error": "Draft not found"}), 404
    if post.status == "published":
        return jsonify({"error": "Cannot delete a published post"}), 400
    try:
        db.session.delete(post)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Failed to delete draft: {exc}"}), 500
    return jsonify({"deleted": True, "id": post_id})


@v1.route("/publishing/blogs", methods=["GET"])
@jwt_required(optional=True)
def api_blog_list():
    include_unpublished = request.args.get("include_unpublished", "false").lower() == "true"
    posts = list_blogs(include_unpublished=include_unpublished)
    return jsonify(
        {
            "posts": [
                {
                    "id": p.id,
                    "title": p.title,
                    "slug": p.slug,
                    "status": p.status,
                    "published_at": p.published_at.isoformat() if p.published_at else None,
                }
                for p in posts
            ]
        }
    )
