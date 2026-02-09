import os
import pytest

# Set required env vars for testing
os.environ.setdefault("GOOGLE_API_KEY", "test-api-key")
os.environ.setdefault("API_SECRET", "bowlingmate-hackathon-secret")
os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket")
