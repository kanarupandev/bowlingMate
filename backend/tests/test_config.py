# Tests for backend configuration
import pytest
import os
from unittest.mock import patch


class TestSettings:
    """Tests for application settings."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Set up required environment variables for tests."""
        # Store original env
        original_key = os.environ.get("GOOGLE_API_KEY")

        # Set test value
        os.environ["GOOGLE_API_KEY"] = "test-api-key-for-testing"

        # Clear cached settings
        from config import get_settings
        get_settings.cache_clear()

        yield

        # Restore original env
        if original_key:
            os.environ["GOOGLE_API_KEY"] = original_key
        elif "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

        # Clear cache again
        get_settings.cache_clear()

    def test_settings_loads(self):
        """Test that settings can be instantiated."""
        from config import Settings
        settings = Settings()
        assert settings is not None

    def test_default_values(self):
        """Test default configuration values."""
        from config import Settings
        settings = Settings()

        assert settings.APP_NAME == "BowlingMate"
        assert settings.SCOUT_MODEL == "gemini-3-flash-preview"  # Flash for speed
        assert settings.COACH_MODEL == "gemini-3-pro-preview"    # Pro for analysis
        assert settings.SCOUT_CONFIDENCE_THRESHOLD == 0.70
        assert settings.ANALYSIS_TIMEOUT >= 300

    def test_api_secret_exists(self):
        """Test that API secret is configured."""
        from config import Settings
        settings = Settings()
        assert settings.API_SECRET is not None
        assert len(settings.API_SECRET) > 0

    def test_get_settings_cached(self):
        """Test that get_settings returns cached instance."""
        from config import get_settings
        settings1 = get_settings()
        settings2 = get_settings()

        # Should return same cached instance
        assert settings1 is settings2

    def test_gcs_config(self):
        """Test GCS configuration defaults."""
        from config import Settings
        settings = Settings()

        assert settings.GCS_BUCKET_NAME == "bowlingmate-clips"
        assert settings.TEMP_VIDEO_DIR == "temp_videos"

    def test_model_names_valid(self):
        """Test that model names follow expected format."""
        from config import Settings
        settings = Settings()

        assert "gemini" in settings.SCOUT_MODEL.lower()
        assert "gemini" in settings.COACH_MODEL.lower()
        # Scout uses Flash for speed, Coach uses Pro for analysis
        assert "gemini-3" in settings.SCOUT_MODEL.lower()
        assert "gemini-3" in settings.COACH_MODEL.lower()

    def test_google_api_key_required(self):
        """Test that GOOGLE_API_KEY is required."""
        from config import Settings

        # Note: This test may pass if .env file exists with key
        # The key should be set either via env or .env file
        settings = Settings()
        assert settings.GOOGLE_API_KEY is not None
        assert len(settings.GOOGLE_API_KEY) > 0

    def test_api_secret_default(self):
        """Test that API_SECRET has a default value."""
        from config import Settings
        settings = Settings()

        # Default value should be set
        assert settings.API_SECRET == "bowlingmate-hackathon-secret"

    def test_debug_mode_default(self):
        """Test debug mode default."""
        from config import Settings
        settings = Settings()

        assert settings.DEBUG is True

    def test_log_level_default(self):
        """Test log level default."""
        from config import Settings
        settings = Settings()

        assert settings.LOG_LEVEL == "DEBUG"

    def test_enable_rag_default(self):
        """Test RAG enabled by default."""
        from config import Settings
        settings = Settings()

        assert settings.ENABLE_RAG is True


class TestConfidenceThreshold:
    """Tests for confidence threshold configuration."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Set up required environment variables for tests."""
        original_key = os.environ.get("GOOGLE_API_KEY")
        os.environ["GOOGLE_API_KEY"] = "test-api-key-for-testing"

        from config import get_settings
        get_settings.cache_clear()

        yield

        if original_key:
            os.environ["GOOGLE_API_KEY"] = original_key
        elif "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

        get_settings.cache_clear()

    def test_threshold_in_valid_range(self):
        """Test threshold is between 0 and 1."""
        from config import Settings
        settings = Settings()

        assert 0.0 <= settings.SCOUT_CONFIDENCE_THRESHOLD <= 1.0

    def test_threshold_aligns_with_prompt(self):
        """Test threshold aligns with prompt guidance (<0.70 should not detect)."""
        from config import Settings
        settings = Settings()

        # Prompt says <0.70 should not return found=true
        # So threshold should be >= 0.70
        assert settings.SCOUT_CONFIDENCE_THRESHOLD >= 0.70


class TestSettingsOverride:
    """Tests for settings override via environment variables."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Set up environment with overrides."""
        original_env = {
            "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY"),
            "SCOUT_CONFIDENCE_THRESHOLD": os.environ.get("SCOUT_CONFIDENCE_THRESHOLD"),
            "APP_NAME": os.environ.get("APP_NAME"),
        }

        os.environ["GOOGLE_API_KEY"] = "test-api-key-for-testing"

        from config import get_settings
        get_settings.cache_clear()

        yield

        # Restore
        for key, value in original_env.items():
            if value is not None:
                os.environ[key] = value
            elif key in os.environ:
                del os.environ[key]

        get_settings.cache_clear()

    def test_threshold_can_be_overridden(self):
        """Test that threshold can be overridden via env."""
        from config import get_settings
        get_settings.cache_clear()

        os.environ["SCOUT_CONFIDENCE_THRESHOLD"] = "0.85"

        from config import Settings
        settings = Settings()

        assert settings.SCOUT_CONFIDENCE_THRESHOLD == 0.85

    def test_app_name_can_be_overridden(self):
        """Test that app name can be overridden."""
        from config import get_settings
        get_settings.cache_clear()

        os.environ["APP_NAME"] = "CustomApp"

        from config import Settings
        settings = Settings()

        assert settings.APP_NAME == "CustomApp"
