import pytest
from unittest.mock import MagicMock, patch
from config import Settings
import os

# 1. Tests for existing settings logic
def test_settings_load():
    settings = Settings()
    # Verify defaults or env-loaded values
    assert settings.GEMINI_MODEL_NAME is not None
    assert settings.ANALYSIS_TIMEOUT >= 300

# 2. RED: Test for a new utility we haven't built yet (Video Metadata Extractor)
# Following Strict TDD
def test_extract_speed_from_text():
    from utils import extract_speed
    assert extract_speed("Total speed was 120 km/h today") == "120 km/h"
    assert extract_speed("No speed here") == "0 km/h"
    assert extract_speed("SPEED_EST: 145 km/h") == "145 km/h"

# 3. Test for Agent Node via Graph
@patch("agent.genai")
def test_agent_graph_execution(mock_genai):
    import json
    from agent import app_graph

    # Mock upload
    mock_file = MagicMock()
    mock_file.state.name = "ACTIVE"
    mock_file.name = "files/test_video"
    mock_genai.upload_file.return_value = mock_file
    mock_genai.get_file.return_value = mock_file

    # Mock model response (JSON format as expected by agent)
    mock_response_data = {
        "phases": [{"name": "Run-up", "status": "GOOD", "observation": "Good rhythm", "tip": "Keep it up"}],
        "estimated_speed_kmh": 110,
        "effort": "High",
        "summary": "Good delivery",
        "release_timestamp": 3.0
    }
    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_response_data)
    mock_genai.GenerativeModel.return_value.generate_content.return_value = mock_response

    state = {
        "messages": [],
        "video_path": "fake.mp4",
        "config": "club",
        "language": "en"
    }

    # Patch database functions
    with patch("agent.insert_summary"), patch("agent.get_next_bowl_num", return_value=1):
        result = app_graph.invoke(state)

    assert "report" in result
    assert result["bowl_count"] == 1
