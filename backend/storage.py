"""
Google Cloud Storage Service for video clip persistence.
Handles upload, download, thumbnail generation, and signed URL creation.
"""
import os
import subprocess
import logging
from typing import Optional, Tuple
from datetime import timedelta
from google.cloud import storage
from google.auth import compute_engine
from google.auth.transport import requests as auth_requests
import google.auth

from config import get_settings

logger = logging.getLogger("BowlingMate.storage")
settings = get_settings()


class GCSStorageService:
    """Handles all GCS operations for BowlingMate clips."""

    def __init__(self):
        self.bucket_name = settings.GCS_BUCKET_NAME
        self._client: Optional[storage.Client] = None
        self._bucket: Optional[storage.Bucket] = None
        self._signing_credentials = None

    @property
    def client(self) -> storage.Client:
        """Lazy-initialize GCS client."""
        if self._client is None:
            self._client = storage.Client()
        return self._client

    @property
    def signing_credentials(self):
        """Get credentials that can sign URLs (for Cloud Run)."""
        if self._signing_credentials is None:
            credentials, project = google.auth.default()
            # For Cloud Run, we need to use IAM signing
            if isinstance(credentials, compute_engine.Credentials):
                auth_request = auth_requests.Request()
                credentials.refresh(auth_request)
                self._signing_credentials = compute_engine.IDTokenCredentials(
                    auth_request,
                    target_audience="",
                    service_account_email=credentials.service_account_email
                )
                # Store the service account email for signing
                self._service_account_email = credentials.service_account_email
            else:
                self._signing_credentials = credentials
                self._service_account_email = None
        return self._signing_credentials
    
    @property
    def bucket(self) -> storage.Bucket:
        """Get or create the bucket."""
        if self._bucket is None:
            try:
                self._bucket = self.client.get_bucket(self.bucket_name)
            except Exception:
                logger.warning(f"Bucket {self.bucket_name} not found, creating...")
                self._bucket = self.client.create_bucket(self.bucket_name, location="us-central1")
        return self._bucket
    
    def generate_thumbnail(self, video_path: str, output_path: str) -> bool:
        """Generate a thumbnail from video using ffmpeg."""
        try:
            # Extract frame at 1 second, resize to 320x180
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-ss", "00:00:01",
                "-vframes", "1",
                "-vf", "scale=320:180",
                output_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            return True
        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
            return False
    
    def upload_clip(self, local_path: str, delivery_id: str, base_url: str = "") -> Tuple[str, str]:
        """
        Upload video clip and thumbnail to GCS.
        Returns: (video_proxy_url, thumbnail_proxy_url)
        """
        # Upload video
        video_blob_name = f"clips/{delivery_id}.mp4"
        video_blob = self.bucket.blob(video_blob_name)
        video_blob.upload_from_filename(local_path, content_type="video/mp4")
        logger.info(f"Uploaded video to gs://{self.bucket_name}/{video_blob_name}")

        # Generate and upload thumbnail
        thumb_path = local_path.replace(".mp4", "_thumb.jpg")
        thumb_url = ""
        if self.generate_thumbnail(local_path, thumb_path):
            thumb_blob_name = f"thumbs/{delivery_id}.jpg"
            thumb_blob = self.bucket.blob(thumb_blob_name)
            thumb_blob.upload_from_filename(thumb_path, content_type="image/jpeg")
            thumb_url = f"{base_url}/media/thumb/{delivery_id}" if base_url else ""
            logger.info(f"Uploaded thumbnail to gs://{self.bucket_name}/{thumb_blob_name}")
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

        video_url = f"{base_url}/media/video/{delivery_id}" if base_url else ""
        logger.info(f"Returning proxy URLs: video={video_url}, thumb={thumb_url}")
        return video_url, thumb_url

    def get_proxy_url(self, blob_name: str, base_url: str) -> str:
        """Generate a proxy URL that streams through the backend (secure, no public access needed)."""
        # Extract delivery_id from blob_name (e.g., "clips/uuid.mp4" -> "uuid")
        delivery_id = blob_name.split("/")[-1].replace(".mp4", "").replace(".jpg", "")
        media_type = "video" if ".mp4" in blob_name or "clips/" in blob_name else "thumb"
        return f"{base_url}/media/{media_type}/{delivery_id}"

    def download_blob(self, blob_name: str) -> Optional[bytes]:
        """Download blob content from GCS."""
        try:
            blob = self.bucket.blob(blob_name)
            return blob.download_as_bytes()
        except Exception as e:
            logger.error(f"Failed to download {blob_name}: {e}")
            return None

    def refresh_signed_url(self, delivery_id: str) -> str:
        """Deprecated: Use proxy URLs instead. Returns proxy URL for backwards compatibility."""
        return f"/media/video/{delivery_id}"


# Singleton instance
_storage_service: Optional[GCSStorageService] = None

def get_storage_service() -> GCSStorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = GCSStorageService()
    return _storage_service
