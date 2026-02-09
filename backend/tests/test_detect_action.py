"""
Tests for /detect-action endpoint batch delivery detection.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)

HEADERS = {"Authorization": "Bearer bowlingmate-hackathon-secret"}


class TestDetectActionResponseFormat:
    """Test the new response format: {found, deliveries_detected_at_time, total_count}"""

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_multiple_deliveries_detected(self, mock_configure, mock_model_class):
        """Should return array of timestamps when multiple deliveries found."""
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "found": True,
            "deliveries_detected_at_time": [6.2, 18.5, 37.1, 59.8],
            "total_count": 4
        })
        mock_model.generate_content.return_value = mock_response

        with open("/tmp/test_video.mp4", "wb") as f:
            f.write(b"fake video data")

        with open("/tmp/test_video.mp4", "rb") as f:
            response = client.post(
                "/detect-action",
                files={"file": ("test.mp4", f, "video/mp4")},
                headers=HEADERS
            )

        assert response.status_code == 200
        data = response.json()
        assert data["found"] == True
        assert data["deliveries_detected_at_time"] == [6.2, 18.5, 37.1, 59.8]
        assert data["total_count"] == 4
        assert "timestamp" not in data

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_no_deliveries_detected(self, mock_configure, mock_model_class):
        """Should return empty array when no deliveries found."""
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "found": False,
            "deliveries_detected_at_time": [],
            "total_count": 0
        })
        mock_model.generate_content.return_value = mock_response

        with open("/tmp/test_video.mp4", "wb") as f:
            f.write(b"fake video data")

        with open("/tmp/test_video.mp4", "rb") as f:
            response = client.post(
                "/detect-action",
                files={"file": ("test.mp4", f, "video/mp4")},
                headers=HEADERS
            )

        assert response.status_code == 200
        data = response.json()
        assert data["found"] == False
        assert data["deliveries_detected_at_time"] == []
        assert data["total_count"] == 0

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_single_delivery_detected(self, mock_configure, mock_model_class):
        """Should return array with single timestamp."""
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "found": True,
            "deliveries_detected_at_time": [45.3],
            "total_count": 1
        })
        mock_model.generate_content.return_value = mock_response

        with open("/tmp/test_video.mp4", "wb") as f:
            f.write(b"fake video data")

        with open("/tmp/test_video.mp4", "rb") as f:
            response = client.post(
                "/detect-action",
                files={"file": ("test.mp4", f, "video/mp4")},
                headers=HEADERS
            )

        assert response.status_code == 200
        data = response.json()
        assert data["found"] == True
        assert data["deliveries_detected_at_time"] == [45.3]
        assert data["total_count"] == 1


class TestDetectActionTimestampSorting:
    """Test that timestamps are always returned sorted."""

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_timestamps_sorted_ascending(self, mock_configure, mock_model_class):
        """Timestamps should be sorted in ascending order."""
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "found": True,
            "deliveries_detected_at_time": [59.8, 6.2, 37.1, 18.5],
            "total_count": 4
        })
        mock_model.generate_content.return_value = mock_response

        with open("/tmp/test_video.mp4", "wb") as f:
            f.write(b"fake video data")

        with open("/tmp/test_video.mp4", "rb") as f:
            response = client.post(
                "/detect-action",
                files={"file": ("test.mp4", f, "video/mp4")},
                headers=HEADERS
            )

        assert response.status_code == 200
        data = response.json()
        assert data["deliveries_detected_at_time"] == [6.2, 18.5, 37.1, 59.8]


class TestDetectActionErrorHandling:
    """Test error handling."""

    @patch("google.generativeai.GenerativeModel")
    @patch("google.generativeai.configure")
    def test_gemini_error_returns_empty(self, mock_configure, mock_model_class):
        """Should return empty results on Gemini error."""
        mock_model = MagicMock()
        mock_model_class.return_value = mock_model
        mock_model.generate_content.side_effect = Exception("API Error")

        with open("/tmp/test_video.mp4", "wb") as f:
            f.write(b"fake video data")

        with open("/tmp/test_video.mp4", "rb") as f:
            response = client.post(
                "/detect-action",
                files={"file": ("test.mp4", f, "video/mp4")},
                headers=HEADERS
            )

        assert response.status_code == 200
        data = response.json()
        assert data["found"] == False
        assert data["deliveries_detected_at_time"] == []
        assert "error" in data

    def test_missing_api_secret(self):
        """Should reject requests without API secret."""
        with open("/tmp/test_video.mp4", "wb") as f:
            f.write(b"fake video data")

        with open("/tmp/test_video.mp4", "rb") as f:
            response = client.post(
                "/detect-action",
                files={"file": ("test.mp4", f, "video/mp4")}
            )

        assert response.status_code == 401
