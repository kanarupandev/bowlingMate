# Tests for GCS storage service
import pytest
from unittest.mock import patch, MagicMock, mock_open
import sys

# Check if google.cloud.storage is available
try:
    from google.cloud import storage as gcs
    GCS_AVAILABLE = True
except ImportError:
    GCS_AVAILABLE = False


pytestmark = pytest.mark.skipif(
    not GCS_AVAILABLE,
    reason="google-cloud-storage not installed"
)


class TestGCSStorageService:
    """Tests for GCS storage service."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Set up environment for storage tests."""
        import os
        original_key = os.environ.get("GOOGLE_API_KEY")
        os.environ["GOOGLE_API_KEY"] = "test-api-key"

        yield

        if original_key:
            os.environ["GOOGLE_API_KEY"] = original_key
        elif "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

    @patch('storage.storage.Client')
    def test_client_lazy_initialization(self, mock_client_cls):
        """Test that client is lazily initialized."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            from storage import GCSStorageService
            service = GCSStorageService()
            # Client should not be initialized yet
            assert service._client is None

            # Access client property
            _ = service.client

            # Now it should be initialized
            mock_client_cls.assert_called_once()

    @patch('storage.storage.Client')
    @patch('storage.service_account.Credentials.from_service_account_file')
    def test_client_with_credentials_path(self, mock_creds, mock_client_cls):
        """Test client initialization with credentials file."""
        mock_creds.return_value = MagicMock()

        # Patch settings at module level
        with patch.object(__import__('storage'), 'settings') as mock_settings:
            mock_settings.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.GCS_CREDENTIALS_PATH = "/path/to/creds.json"

            from storage import GCSStorageService
            service = GCSStorageService()
            _ = service.client

            mock_creds.assert_called_once_with("/path/to/creds.json")
            mock_client_cls.assert_called_once()

    @patch('storage.storage.Client')
    def test_bucket_get_existing(self, mock_client_cls):
        """Test getting an existing bucket."""
        mock_client = MagicMock()
        mock_bucket = MagicMock()
        mock_client.get_bucket.return_value = mock_bucket
        mock_client_cls.return_value = mock_client

        with patch.object(__import__('storage'), 'settings') as mock_settings:
            mock_settings.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.GCS_CREDENTIALS_PATH = None

            from storage import GCSStorageService
            service = GCSStorageService()
            bucket = service.bucket

            mock_client.get_bucket.assert_called_once_with("test-bucket")
            assert bucket == mock_bucket

    @patch('storage.storage.Client')
    def test_bucket_create_if_not_exists(self, mock_client_cls):
        """Test bucket creation when it doesn't exist."""
        mock_client = MagicMock()
        mock_client.get_bucket.side_effect = Exception("Bucket not found")
        mock_new_bucket = MagicMock()
        mock_client.create_bucket.return_value = mock_new_bucket
        mock_client_cls.return_value = mock_client

        with patch.object(__import__('storage'), 'settings') as mock_settings:
            mock_settings.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.GCS_CREDENTIALS_PATH = None

            from storage import GCSStorageService
            service = GCSStorageService()
            bucket = service.bucket

            mock_client.create_bucket.assert_called_once_with("test-bucket", location="us-central1")
            assert bucket == mock_new_bucket

    @patch('storage.subprocess.run')
    def test_generate_thumbnail_success(self, mock_run):
        """Test successful thumbnail generation."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            mock_run.return_value = MagicMock(returncode=0)

            from storage import GCSStorageService
            service = GCSStorageService()
            result = service.generate_thumbnail("/path/video.mp4", "/path/thumb.jpg")

            assert result is True
            mock_run.assert_called_once()
            # Verify ffmpeg command structure
            call_args = mock_run.call_args[0][0]
            assert "ffmpeg" in call_args
            assert "/path/video.mp4" in call_args
            assert "/path/thumb.jpg" in call_args

    @patch('storage.subprocess.run')
    def test_generate_thumbnail_failure(self, mock_run):
        """Test thumbnail generation failure handling."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            mock_run.side_effect = Exception("ffmpeg not found")

            from storage import GCSStorageService
            service = GCSStorageService()
            result = service.generate_thumbnail("/path/video.mp4", "/path/thumb.jpg")

            assert result is False

    @patch('storage.storage.Client')
    @patch('storage.os.path.exists')
    @patch('storage.os.remove')
    def test_upload_clip(self, mock_remove, mock_exists, mock_client_cls):
        """Test clip upload with video and thumbnail."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            mock_client = MagicMock()
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            mock_blob.generate_signed_url.return_value = "https://signed-url.com"

            mock_client.get_bucket.return_value = mock_bucket
            mock_bucket.blob.return_value = mock_blob
            mock_client_cls.return_value = mock_client
            mock_exists.return_value = True

            from storage import GCSStorageService
            service = GCSStorageService()

            # Mock thumbnail generation
            with patch.object(service, 'generate_thumbnail', return_value=True):
                video_url, thumb_url = service.upload_clip("/path/video.mp4", "delivery-123")

            # Should have uploaded video
            mock_bucket.blob.assert_any_call("clips/delivery-123.mp4")
            mock_blob.upload_from_filename.assert_called()

            # Should return signed URLs
            assert "signed-url" in video_url
            assert "signed-url" in thumb_url

    @patch('storage.storage.Client')
    def test_get_signed_url(self, mock_client_cls):
        """Test signed URL generation."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            mock_client = MagicMock()
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            mock_blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed"

            mock_client.get_bucket.return_value = mock_bucket
            mock_bucket.blob.return_value = mock_blob
            mock_client_cls.return_value = mock_client

            from storage import GCSStorageService
            service = GCSStorageService()
            url = service.get_signed_url("clips/test.mp4", expiration_hours=2)

            mock_blob.generate_signed_url.assert_called_once()
            assert url == "https://storage.googleapis.com/signed"

    @patch('storage.storage.Client')
    def test_refresh_signed_url(self, mock_client_cls):
        """Test refreshing signed URL for playback."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            mock_client = MagicMock()
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            mock_blob.generate_signed_url.return_value = "https://fresh-url.com"

            mock_client.get_bucket.return_value = mock_bucket
            mock_bucket.blob.return_value = mock_blob
            mock_client_cls.return_value = mock_client

            from storage import GCSStorageService
            service = GCSStorageService()
            url = service.refresh_signed_url("delivery-456")

            # Should use the correct blob path
            mock_bucket.blob.assert_called_with("clips/delivery-456.mp4")
            assert url == "https://fresh-url.com"


class TestStorageServiceSingleton:
    """Tests for storage service singleton."""

    @pytest.fixture(autouse=True)
    def setup_env(self):
        """Set up environment for singleton tests."""
        import os
        original_key = os.environ.get("GOOGLE_API_KEY")
        os.environ["GOOGLE_API_KEY"] = "test-api-key"

        yield

        if original_key:
            os.environ["GOOGLE_API_KEY"] = original_key
        elif "GOOGLE_API_KEY" in os.environ:
            del os.environ["GOOGLE_API_KEY"]

    def test_get_storage_service_returns_instance(self):
        """Test that get_storage_service returns an instance."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            # Reset singleton for test
            import storage
            storage._storage_service = None

            from storage import get_storage_service, GCSStorageService
            service = get_storage_service()
            assert service is not None
            assert isinstance(service, GCSStorageService)

    def test_get_storage_service_returns_same_instance(self):
        """Test that get_storage_service returns cached instance."""
        with patch('storage.get_settings') as mock_settings:
            mock_settings.return_value.GCS_BUCKET_NAME = "test-bucket"
            mock_settings.return_value.GCS_CREDENTIALS_PATH = None

            # Reset singleton for test
            import storage
            storage._storage_service = None

            from storage import get_storage_service
            service1 = get_storage_service()
            service2 = get_storage_service()

            assert service1 is service2
