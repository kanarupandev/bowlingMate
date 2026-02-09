from unittest.mock import patch, MagicMock
from agent import agent_node, AgentState


def test_agent_error_handling():
    """Test agent graceful degradation when Gemini API fails."""

    with patch('agent.genai') as mock_genai, \
         patch('agent.insert_summary') as mock_insert, \
         patch('agent.get_next_bowl_num') as mock_bowl_num:

        # Simulate upload failure
        mock_genai.upload_file.side_effect = Exception("Gemini API Down")
        mock_bowl_num.return_value = 1

        state = AgentState(
            messages=[],
            video_path="dummy.mov",
            config="club",
            language="en",
            bowl_count=0,
            report="",
            speed_est=""
        )

        # It should NOT crash, but return error text
        result = agent_node(state)

        # Verify graceful degradation
        assert "failed" in result['report'].lower() or "Analysis failed" in result['report']
        assert result['speed_est'] == "0 km/h"
