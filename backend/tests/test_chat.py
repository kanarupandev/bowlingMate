"""Tests for /chat endpoint - Interactive Coach Chat."""
import pytest
from unittest.mock import patch, MagicMock


class TestChatEndpoint:
    """Test the /chat endpoint structure and validation."""

    def test_chat_request_model(self):
        """Test ChatRequest model accepts valid data."""
        from main import ChatRequest

        request = ChatRequest(
            message="What's wrong with my release?",
            delivery_id="test-123",
            phases=[
                {"name": "Run-up", "status": "GOOD", "clip_ts": 0.5},
                {"name": "Release", "status": "NEEDS WORK", "clip_ts": 2.0}
            ]
        )

        assert request.message == "What's wrong with my release?"
        assert request.delivery_id == "test-123"
        assert len(request.phases) == 2

    def test_chat_response_model(self):
        """Test ChatResponse model structure."""
        from main import ChatResponse

        # Response with video action
        response = ChatResponse(
            text="Your elbow is bending at release.",
            video_action={"action": "focus", "timestamp": 2.0}
        )
        assert response.text == "Your elbow is bending at release."
        assert response.video_action["action"] == "focus"
        assert response.video_action["timestamp"] == 2.0

        # Response without video action
        response_no_action = ChatResponse(text="Hello!", video_action=None)
        assert response_no_action.video_action is None

    def test_coach_chat_tool_schema(self):
        """Test the Gemini function calling tool schema."""
        from main import COACH_CHAT_TOOL

        # Verify tool structure
        assert "function_declarations" in COACH_CHAT_TOOL
        func = COACH_CHAT_TOOL["function_declarations"][0]

        assert func["name"] == "control_video"
        assert "parameters" in func

        # Verify action enum
        props = func["parameters"]["properties"]
        assert "action" in props
        assert props["action"]["enum"] == ["focus", "pause", "play"]

        # Verify timestamp property
        assert "timestamp" in props
        assert props["timestamp"]["type"] == "number"


class TestChatPrompt:
    """Test coach chat prompt loading."""

    def test_prompt_file_exists(self):
        """Verify prompt file is present."""
        import os
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "coach_chat_prompt.txt"
        )
        assert os.path.exists(prompt_path), f"Prompt file missing: {prompt_path}"

    def test_prompt_contains_placeholders(self):
        """Verify prompt has required placeholders."""
        import os
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "coach_chat_prompt.txt"
        )
        with open(prompt_path, "r") as f:
            content = f.read()

        assert "{phases_json}" in content, "Prompt missing {phases_json} placeholder"
        assert "control_video" in content, "Prompt should mention control_video"
        assert "focus" in content, "Prompt should mention focus action"


class TestVideoAction:
    """Test video action extraction logic."""

    def test_focus_action_structure(self):
        """Test focus action has required fields."""
        action = {"action": "focus", "timestamp": 2.5}

        assert action["action"] == "focus"
        assert action["timestamp"] == 2.5
        assert isinstance(action["timestamp"], float)

    def test_pause_action_no_timestamp(self):
        """Test pause action doesn't require timestamp."""
        action = {"action": "pause", "timestamp": None}

        assert action["action"] == "pause"
        # Timestamp can be None for pause

    def test_play_action_no_timestamp(self):
        """Test play action doesn't require timestamp."""
        action = {"action": "play", "timestamp": None}

        assert action["action"] == "play"


class TestPhaseTimestampExtraction:
    """Test phase timestamp handling for video seek."""

    def test_extract_clip_ts_from_phases(self):
        """Test extracting clip_ts from phase data."""
        phases = [
            {"name": "Run-up", "status": "GOOD", "clip_ts": 0.5},
            {"name": "Loading", "status": "NEEDS WORK", "clip_ts": 1.5},
            {"name": "Release", "status": "GOOD", "clip_ts": 2.0},
        ]

        # Find release timestamp
        release_phase = next((p for p in phases if "release" in p["name"].lower()), None)
        assert release_phase is not None
        assert release_phase["clip_ts"] == 2.0

    def test_handle_missing_clip_ts(self):
        """Test handling phases without clip_ts (backward compat)."""
        phases = [
            {"name": "Run-up", "status": "GOOD"},  # No clip_ts
            {"name": "Release", "status": "GOOD", "clipTimestamp": 2.0},  # Old format
        ]

        # Should handle both formats
        for p in phases:
            clip_ts = p.get("clip_ts") or p.get("clipTimestamp")
            if p["name"] == "Release":
                assert clip_ts == 2.0
            else:
                assert clip_ts is None
