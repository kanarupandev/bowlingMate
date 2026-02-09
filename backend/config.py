# wellBowled Backend Configuration
import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    # App Config
    APP_NAME: str = "wellBowled"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"
    
    # Credentials
    GOOGLE_API_KEY: str
    API_SECRET: str = "wellbowled-hackathon-secret" # Default for dev, override in prod
    
    # AI Config - Gemini 3 ONLY
    GEMINI_MODEL_NAME: str = "gemini-3-pro-preview"
    SCOUT_MODEL: str = "gemini-3-flash-preview"  # Fast for detection
    COACH_MODEL: str = "gemini-3-pro-preview"    # Pro for detailed analysis
    EMBEDDING_MODEL_NAME: str = "models/text-embedding-004"
    ENABLE_RAG: bool = True
    ANALYSIS_TIMEOUT: int = 500 # 8.3 minutes default
    SCOUT_CONFIDENCE_THRESHOLD: float = 0.70

    # Mock Mode - Returns fixed responses for 3sec_vid.mp4 (saves API costs)
    # Set to False in production to use real Gemini API
    MOCK_SCOUT: bool = False   # Real Gemini Scout detection
    MOCK_COACH: bool = False   # Real Gemini Coach analysis

    # Overlay Generation - Enable MediaPipe skeleton overlay
    # Warning: First build takes ~30 min (subsequent builds ~8 min with cache)
    ENABLE_OVERLAY: bool = True
    
    # GCS Config
    GCS_BUCKET_NAME: str = "wellbowled-clips"
    GCS_CREDENTIALS_PATH: str = ""  # Optional: path to service account JSON
    
    # Paths
    TEMP_VIDEO_DIR: str = "temp_videos"
    DB_NAME: str = "bowling.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

@lru_cache
def get_settings():
    return Settings()
