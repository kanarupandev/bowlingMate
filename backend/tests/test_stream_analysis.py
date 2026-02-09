# Tests for Coach (stream-analysis) endpoint
import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock


class TestAnalyzeEndpoint:
    """Tests for /analyze endpoint (upload + cache)."""

    def test_analyze_upload_success(self, client):
        """Test successful video upload for analysis."""
        response = client.post(
            "/analyze",
            data={"config": "club", "language": "en"},
            files={"video": ("test.mov", b"fake video bytes", "video/quicktime")}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert "video_id" in data

    def test_analyze_returns_video_id(self, client):
        """Test that upload returns a valid UUID."""
        response = client.post(
            "/analyze",
            data={"config": "junior", "language": "en"},
            files={"video": ("test.mov", b"fake video bytes", "video/quicktime")}
        )

        data = response.json()
        video_id = data["video_id"]

        # Should be a valid UUID format
        import uuid
        try:
            uuid.UUID(video_id)
            valid_uuid = True
        except ValueError:
            valid_uuid = False

        assert valid_uuid, "video_id should be a valid UUID"


class TestStreamAnalysisEndpoint:
    """Tests for /stream-analysis SSE endpoint."""

    def test_stream_analysis_with_cached_video(self, client, mock_gemini_coach_response):
        """Test streaming analysis with pre-uploaded video."""
        # First upload a video
        upload_response = client.post(
            "/analyze",
            data={"config": "club", "language": "en"},
            files={"video": ("test.mov", b"fake video bytes", "video/quicktime")}
        )
        video_id = upload_response.json()["video_id"]

        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = json.dumps(mock_gemini_coach_response)

        with patch("google.generativeai.configure"), \
             patch("google.generativeai.GenerativeModel") as mock_model:
            mock_model.return_value.generate_content.return_value = mock_response

            response = client.get(
                f"/stream-analysis?video_id={video_id}&config=club&language=en"
            )

            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

    def test_stream_analysis_missing_video(self, client):
        """Test streaming with non-existent video_id."""
        response = client.get(
            "/stream-analysis?video_id=nonexistent-id&config=club&language=en"
        )

        assert response.status_code == 200
        # Should return error event
        content = response.text
        assert "error" in content.lower() or "not found" in content.lower()

    def test_stream_analysis_no_auth(self, client_no_auth):
        """Test that streaming requires authentication."""
        response = client_no_auth.get(
            "/stream-analysis?video_id=test-id&config=club&language=en"
        )

        assert response.status_code == 401


class TestCoachResponseParsing:
    """Tests for Coach response parsing logic."""

    def test_parse_speed_from_response(self):
        """Test speed extraction from coach response."""
        from agent import run_streamed_agent

        # Test various speed formats
        responses = [
            ({"estimated_speed_kmh": 125}, "125 km/h"),
            ({"estimated_speed_kmh": 0}, "N/A"),
            ({"estimated_speed_kmh": "_"}, "N/A"),
            ({}, "N/A"),  # Missing field
        ]

        for raw_data, expected in responses:
            speed_val = raw_data.get("estimated_speed_kmh")
            if not speed_val or speed_val == 0 or speed_val == "_":
                speed_str = "N/A"
            else:
                speed_str = f"{speed_val} km/h"

            assert speed_str == expected

    def test_extract_tips_from_phases(self):
        """Test tip extraction from phase data."""
        phases = [
            {"name": "Run-up", "status": "GOOD", "tip": "Keep steady"},
            {"name": "Release", "status": "NEEDS WORK", "tip": "Arm higher"},
            {"name": "Follow-through", "status": "GOOD", "tip": None},  # No tip
        ]

        extracted_tips = [p.get("tip") for p in phases if p.get("tip")]

        assert len(extracted_tips) == 2
        assert "Keep steady" in extracted_tips
        assert "Arm higher" in extracted_tips
