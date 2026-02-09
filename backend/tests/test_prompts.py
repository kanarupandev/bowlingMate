# Tests for prompt generation functions
import pytest
from prompts import get_multi_bowl_detection_prompt, get_analysis_prompt


class TestMultiBowlDetectionPrompt:
    """Tests for multi-bowl detection prompt."""

    def test_prompt_contains_config(self):
        """Test that prompt includes config level."""
        prompt = get_multi_bowl_detection_prompt("club", "en")

        assert "club" in prompt
        assert "en" in prompt

    def test_prompt_contains_output_format(self):
        """Test that prompt specifies JSON output format."""
        prompt = get_multi_bowl_detection_prompt("junior", "en")

        assert "JSON" in prompt
        assert "release_ts" in prompt
        assert "label" in prompt

    def test_prompt_mentions_multiple_deliveries(self):
        """Test that prompt mentions multiple deliveries."""
        prompt = get_multi_bowl_detection_prompt("technical", "en")

        assert "multiple" in prompt.lower()
        assert "deliveries" in prompt.lower() or "delivery" in prompt.lower()

    def test_different_configs(self):
        """Test prompt generation with different configs."""
        configs = ["junior", "club", "technical"]

        for config in configs:
            prompt = get_multi_bowl_detection_prompt(config, "en")
            assert config in prompt
            assert len(prompt) > 100  # Reasonable length

    def test_different_languages(self):
        """Test prompt generation with different language codes."""
        languages = ["en", "es", "fr", "de"]

        for lang in languages:
            prompt = get_multi_bowl_detection_prompt("club", lang)
            assert lang in prompt


class TestAnalysisPrompt:
    """Tests for analysis prompt generation."""

    def test_prompt_contains_config_guidance(self):
        """Test that prompt includes config-specific guidance."""
        prompt = get_analysis_prompt("junior", "en", 3.0)

        assert "Junior" in prompt
        assert "encouraging" in prompt.lower() or "fun" in prompt.lower()

    def test_prompt_contains_release_timestamp(self):
        """Test that prompt includes the release timestamp."""
        prompt = get_analysis_prompt("club", "en", 4.5)

        assert "4.5" in prompt

    def test_prompt_contains_all_phases(self):
        """Test that prompt includes all 6 phases."""
        prompt = get_analysis_prompt("technical", "en", 3.0)

        phases = ["RUN-UP", "LOADING", "COIL", "RELEASE", "WRIST", "HEAD", "EYES", "FOLLOW-THROUGH"]
        for phase in phases:
            assert phase in prompt.upper() or phase.lower() in prompt.lower()

    def test_prompt_contains_output_format(self):
        """Test that prompt specifies JSON output format."""
        prompt = get_analysis_prompt("club", "en", 2.0)

        assert "JSON" in prompt
        assert "phases" in prompt
        assert "estimated_speed_kmh" in prompt
        assert "effort" in prompt
        assert "summary" in prompt

    def test_prompt_contains_speed_instructions(self):
        """Test that prompt includes speed estimation instructions."""
        prompt = get_analysis_prompt("club", "en", 3.0)

        assert "speed" in prompt.lower()
        assert "km/h" in prompt

    def test_prompt_contains_status_options(self):
        """Test that prompt includes status options."""
        prompt = get_analysis_prompt("club", "en", 3.0)

        assert "GOOD" in prompt
        assert "NEEDS WORK" in prompt

    def test_different_config_levels(self):
        """Test that different configs produce different guidance."""
        junior_prompt = get_analysis_prompt("junior", "en", 3.0)
        technical_prompt = get_analysis_prompt("technical", "en", 3.0)

        # Both should mention their config
        assert "Junior" in junior_prompt
        assert "Technical" in technical_prompt

        # Technical should mention biomechanical or analytical
        assert "technical" in technical_prompt.lower() or "analytical" in technical_prompt.lower()

    def test_release_timestamp_context(self):
        """Test that release timestamp is used for analysis centering."""
        prompt = get_analysis_prompt("club", "en", 5.5)

        # Should reference centering around the timestamp
        assert "5.5" in prompt
        assert "Centered" in prompt or "around" in prompt.lower()

    def test_prompt_mentions_icc_rules(self):
        """Test that prompt mentions ICC elbow rules."""
        prompt = get_analysis_prompt("technical", "en", 3.0)

        assert "ICC" in prompt or "15" in prompt  # 15 degree rule

    def test_effort_levels_mentioned(self):
        """Test that all effort levels are mentioned."""
        prompt = get_analysis_prompt("club", "en", 3.0)

        effort_levels = ["Low", "Medium", "High", "Max"]
        for level in effort_levels:
            assert level in prompt
