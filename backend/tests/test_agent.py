from unittest.mock import MagicMock, patch
from agent import agent_node, AgentState
import json


def test_agent_node_logic():
    """Test agent_node with mocked Gemini API."""

    # Mock JSON response from Gemini
    mock_response_data = {
        "phases": [
            {"name": "Run-up", "status": "GOOD", "observation": "Good rhythm", "tip": "Keep it up"}
        ],
        "estimated_speed_kmh": 130,
        "effort": "High",
        "summary": "Good delivery",
        "release_timestamp": 3.0
    }

    with patch('agent.genai') as mock_genai, \
         patch('agent.insert_summary') as mock_insert, \
         patch('agent.get_next_bowl_num') as mock_bowl_num:

        # Mock video file upload
        mock_video_file = MagicMock()
        mock_video_file.name = "test_video"
        mock_video_file.state.name = "ACTIVE"
        mock_genai.upload_file.return_value = mock_video_file
        mock_genai.get_file.return_value = mock_video_file

        # Mock model and response
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps(mock_response_data)
        mock_model.generate_content.return_value = mock_response
        mock_genai.GenerativeModel.return_value = mock_model

        mock_bowl_num.return_value = 1

        # Setup State
        state = AgentState(
            messages=[],
            video_path="dummy.mov",
            config="technical",
            language="en",
            bowl_count=0,
            report="",
            speed_est=""
        )

        # Execute
        result = agent_node(state)

        # Assertions - agent parses JSON response
        assert 'report' in result
        assert mock_genai.upload_file.called
        mock_insert.assert_called_once()
