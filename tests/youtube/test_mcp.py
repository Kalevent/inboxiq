import pytest
from unittest.mock import patch, MagicMock


def test_heygen_render_video_missing_key(monkeypatch):
    monkeypatch.delenv("HEYGEN_API_KEY", raising=False)
    from src.mcp import heygen_mcp
    import importlib
    importlib.reload(heygen_mcp)
    result = heygen_mcp.render_video(
        script="Test script.",
        avatar_id="test-avatar",
        voice_id="test-voice",
        video_format="mp4",
        aspect_ratio="16:9",
    )
    assert result["status"] == "error"
    assert "HEYGEN_API_KEY" in result["error"]


def test_heygen_render_video_success(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": {"video_id": "job-123"}}
    with patch("requests.post", return_value=mock_response):
        from src.mcp import heygen_mcp
        import importlib
        importlib.reload(heygen_mcp)
        result = heygen_mcp.render_video(
            script="Test script.",
            avatar_id="977b1ab85dba4eefb159a6072677effd",
            voice_id="41332f3d53e148aab6956b92d3e5503e",
            video_format="mp4",
            aspect_ratio="16:9",
        )
    assert result["status"] == "submitted"
    assert result["job_id"] == "job-123"


def test_heygen_get_render_status_complete(monkeypatch):
    monkeypatch.setenv("HEYGEN_API_KEY", "test-key")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {"status": "completed", "video_url": "https://cdn.heygen.com/video.mp4"}
    }
    with patch("requests.get", return_value=mock_response):
        from src.mcp import heygen_mcp
        import importlib
        importlib.reload(heygen_mcp)
        result = heygen_mcp.get_render_status("job-123")
    assert result["status"] == "completed"
    assert result["render_url"] == "https://cdn.heygen.com/video.mp4"
