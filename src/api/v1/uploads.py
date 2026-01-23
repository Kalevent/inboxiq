from uuid import uuid4

from flask import current_app, jsonify, request
from flask_jwt_extended import jwt_required
from werkzeug.utils import secure_filename

from src.api.v1 import v1
from src.uploads import upload_bytes


@v1.route("/uploads", methods=["POST"])
@jwt_required()
def upload_file():
    """
    Upload a file to S3 (via CloudFront) for authenticated users.
    Returns the S3 key and public URL.
    """
    uploads_bucket = current_app.config.get("UPLOADS_BUCKET")
    uploads_host = current_app.config.get("UPLOADS_HOST")
    if not uploads_bucket or not uploads_host:
        return jsonify({"error": "uploads_not_configured"}), 503

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "file_required"}), 400

    filename = secure_filename(file.filename or "")
    if not filename:
        return jsonify({"error": "invalid_filename"}), 400

    data = file.read()
    if not data:
        return jsonify({"error": "empty_file"}), 400

    # Basic size guard (10 MB)
    if len(data) > 10 * 1024 * 1024:
        return jsonify({"error": "file_too_large", "max_bytes": 10 * 1024 * 1024}), 413

    key = f"public/{uuid4().hex}_{filename}"
    url = upload_bytes(
        key=key,
        data=data,
        content_type=file.mimetype or "application/octet-stream",
        content_disposition=f'attachment; filename="{filename}"',
    )
    return jsonify({"key": key, "url": url}), 201
