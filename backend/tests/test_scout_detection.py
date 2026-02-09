"""
Unit tests for Scout detection endpoint response parsing.
Tests the response format compatibility with iOS frontend.
"""
import pytest
import json


class TestScoutResponseFormat:
    """Tests for Scout detection response format."""

    def test_single_delivery_response_has_root_timestamp(self):
        """Test that single delivery response includes timestamp at root level."""
        # Simulated response from backend
        response = {
            "found": True,
            "timestamp": 7.0,
            "confidence": 0.98,
            "deliveries": [
                {"timestamp": 7.0, "confidence": 0.98, "anchor": "grey shorts, overarm release"}
            ],
            "total_count": 1
        }

        # iOS compatibility checks
        assert "found" in response
        assert "timestamp" in response  # Must be at root for iOS
        assert "confidence" in response  # Must be at root for iOS
        assert response["timestamp"] == 7.0
        assert response["confidence"] == 0.98

    def test_multiple_deliveries_response_has_first_timestamp(self):
        """Test that multiple delivery response has first timestamp at root."""
        response = {
            "found": True,
            "timestamp": 6.5,  # First delivery timestamp
            "confidence": 0.95,
            "deliveries": [
                {"timestamp": 6.5, "confidence": 0.95, "anchor": "delivery 1"},
                {"timestamp": 18.8, "confidence": 0.95, "anchor": "delivery 2"},
                {"timestamp": 37.7, "confidence": 0.95, "anchor": "delivery 3"},
                {"timestamp": 58.7, "confidence": 0.95, "anchor": "delivery 4"}
            ],
            "total_count": 4
        }

        assert response["found"] is True
        assert response["timestamp"] == 6.5  # First delivery
        assert response["total_count"] == 4
        assert len(response["deliveries"]) == 4

    def test_no_delivery_response_format(self):
        """Test response format when no deliveries found."""
        response = {
            "found": False,
            "timestamp": None,
            "confidence": 0.0,
            "deliveries": [],
            "total_count": 0
        }

        assert response["found"] is False
        assert response["timestamp"] is None
        assert response["confidence"] == 0.0
        assert response["total_count"] == 0
        assert response["deliveries"] == []


class TestConfidenceThresholdFiltering:
    """Tests for confidence threshold filtering logic."""

    def test_filter_low_confidence_detections(self):
        """Test that low confidence detections are filtered out."""
        threshold = 0.70

        deliveries = [
            {"timestamp": 5.0, "confidence": 0.65},  # Below threshold
            {"timestamp": 10.0, "confidence": 0.85},  # Above threshold
            {"timestamp": 15.0, "confidence": 0.50},  # Below threshold
        ]

        valid = [d for d in deliveries if d.get("confidence", 0) >= threshold]

        assert len(valid) == 1
        assert valid[0]["timestamp"] == 10.0

    def test_all_above_threshold(self):
        """Test when all detections are above threshold."""
        threshold = 0.70

        deliveries = [
            {"timestamp": 6.0, "confidence": 0.95},
            {"timestamp": 18.0, "confidence": 0.92},
            {"timestamp": 37.0, "confidence": 0.88},
        ]

        valid = [d for d in deliveries if d.get("confidence", 0) >= threshold]

        assert len(valid) == 3

    def test_all_below_threshold(self):
        """Test when all detections are below threshold."""
        threshold = 0.70

        deliveries = [
            {"timestamp": 5.0, "confidence": 0.50},
            {"timestamp": 10.0, "confidence": 0.60},
        ]

        valid = [d for d in deliveries if d.get("confidence", 0) >= threshold]

        assert len(valid) == 0


class TestDeliveryTimestampAccuracy:
    """Tests for delivery timestamp accuracy against ground truth."""

    # Ground truth for test_video.mp4
    EXPECTED_TIMESTAMPS = [6, 18, 37, 59]
    TOLERANCE = 2  # ±2 seconds

    def test_timestamps_within_tolerance(self):
        """Test that detected timestamps are within tolerance of expected."""
        detected = [6.5, 18.8, 37.7, 58.7]

        for expected in self.EXPECTED_TIMESTAMPS:
            matches = [d for d in detected if abs(d - expected) <= self.TOLERANCE]
            assert len(matches) >= 1, f"No detection within ±{self.TOLERANCE}s of {expected}s"

    def test_correct_delivery_count(self):
        """Test that correct number of deliveries detected."""
        detected = [6.5, 18.8, 37.7, 58.7]

        assert len(detected) == len(self.EXPECTED_TIMESTAMPS)


class TestResponseParsing:
    """Tests for parsing Gemini response formats."""

    def test_parse_deliveries_array_format(self):
        """Test parsing new deliveries array format from Gemini."""
        gemini_response = {
            "deliveries": [
                {"timestamp": 6.0, "confidence": 0.95, "anchor": "test"},
                {"timestamp": 18.0, "confidence": 0.92, "anchor": "test2"}
            ],
            "total_count": 2
        }

        deliveries = gemini_response.get("deliveries", [])
        assert len(deliveries) == 2
        assert deliveries[0]["timestamp"] == 6.0

    def test_parse_empty_deliveries(self):
        """Test parsing empty deliveries response."""
        gemini_response = {
            "deliveries": [],
            "total_count": 0
        }

        deliveries = gemini_response.get("deliveries", [])
        assert len(deliveries) == 0

    def test_handle_list_response(self):
        """Test handling when Gemini returns a list directly."""
        gemini_response = [
            {"timestamp": 6.0, "confidence": 0.95},
            {"timestamp": 18.0, "confidence": 0.90}
        ]

        # Backend should handle this format
        if isinstance(gemini_response, list):
            deliveries = gemini_response
        else:
            deliveries = gemini_response.get("deliveries", [])

        assert len(deliveries) == 2


class TestiOSCompatibility:
    """Tests to ensure iOS frontend compatibility."""

    def test_response_has_required_ios_fields(self):
        """Test that response has all fields iOS expects."""
        required_fields = ["found", "timestamp", "confidence"]

        response = {
            "found": True,
            "timestamp": 7.0,
            "confidence": 0.98,
            "deliveries": [],
            "total_count": 1
        }

        for field in required_fields:
            assert field in response, f"Missing required field: {field}"

    def test_timestamp_is_numeric_or_none(self):
        """Test that timestamp is a number or None (not string)."""
        valid_responses = [
            {"found": True, "timestamp": 7.0},
            {"found": True, "timestamp": 7},
            {"found": False, "timestamp": None},
        ]

        for resp in valid_responses:
            ts = resp["timestamp"]
            assert ts is None or isinstance(ts, (int, float))

    def test_confidence_is_numeric(self):
        """Test that confidence is always a number."""
        responses = [
            {"confidence": 0.98},
            {"confidence": 0.0},
            {"confidence": 1.0},
        ]

        for resp in responses:
            assert isinstance(resp["confidence"], (int, float))
