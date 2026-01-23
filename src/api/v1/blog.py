from http import HTTPStatus
from flask import jsonify, request

from src.api.v1 import v1


@v1.route("/blog/posts", methods=["POST"])
def create_blog_post():
  """
  Placeholder endpoint for agent-authored blog submissions.
  Accepts JSON payloads; currently responds with a not-implemented marker.
  """
  payload = request.get_json(silent=True) or {}
  return (
    jsonify(
      {
        "status": "not_implemented",
        "message": "Blog post ingestion will be enabled soon.",
        "received_keys": list(payload.keys()),
      }
    ),
    HTTPStatus.NOT_IMPLEMENTED,
  )
