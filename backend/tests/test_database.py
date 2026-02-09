# Tests for database operations
import pytest
from database import (
    init_db, insert_summary, get_summaries, get_next_bowl_num,
    insert_delivery, get_deliveries, get_delivery, get_next_delivery_sequence
)


class TestSummaryOperations:
    """Tests for summary table operations."""

    def test_insert_and_retrieve_summary(self):
        """Test inserting and retrieving a summary."""
        insert_summary(1, "Good bowl", "120 km/h", "club")
        summaries = get_summaries()

        assert len(summaries) >= 1
        latest = summaries[0]
        assert latest['summary'] == "Good bowl"
        assert latest['speed_est'] == "120 km/h"
        assert latest['config'] == "club"

    def test_get_next_bowl_num_empty(self):
        """Test getting next bowl number from empty table."""
        # Note: depends on test isolation
        next_num = get_next_bowl_num()
        assert next_num >= 1

    def test_get_next_bowl_num_increment(self):
        """Test that bowl number increments correctly."""
        current = get_next_bowl_num()
        insert_summary(current, "test", "0", "club")
        assert get_next_bowl_num() == current + 1

    def test_filter_by_config(self):
        """Test filtering summaries by config."""
        # Insert with unique bowl numbers
        base = get_next_bowl_num()
        insert_summary(base, "Junior Bowl", "80 km/h", "junior")
        insert_summary(base + 1, "Club Bowl", "110 km/h", "club")

        junior_sums = get_summaries(config="junior")
        assert any(s['summary'] == "Junior Bowl" for s in junior_sums)

        club_sums = get_summaries(config="club")
        assert any(s['summary'] == "Club Bowl" for s in club_sums)

    def test_get_summaries_limit(self):
        """Test that limit parameter works."""
        # Insert several summaries
        base = get_next_bowl_num()
        for i in range(10):
            insert_summary(base + i, f"Bowl {i}", "100 km/h", "club")

        # Get with limit
        limited = get_summaries(limit=3)
        assert len(limited) == 3

    def test_summaries_ordered_by_id_desc(self):
        """Test that summaries are returned newest first."""
        base = get_next_bowl_num()
        insert_summary(base, "First", "100 km/h", "club")
        insert_summary(base + 1, "Second", "100 km/h", "club")
        insert_summary(base + 2, "Third", "100 km/h", "club")

        summaries = get_summaries(limit=3)
        # Newest should be first
        assert summaries[0]['summary'] == "Third"


class TestDeliveryOperations:
    """Tests for delivery table operations."""

    def test_insert_and_retrieve_delivery(self):
        """Test inserting and retrieving a delivery."""
        delivery_id = "test-delivery-001"
        insert_delivery(
            delivery_id=delivery_id,
            sequence=1,
            cloud_video_url="https://storage.example.com/video.mp4",
            cloud_thumbnail_url="https://storage.example.com/thumb.jpg",
            release_timestamp=3.5,
            speed="125 km/h",
            report="Good delivery",
            tips="Keep arm higher",
            status="success"
        )

        delivery = get_delivery(delivery_id)
        assert delivery is not None
        assert delivery['id'] == delivery_id
        assert delivery['sequence'] == 1
        assert delivery['cloud_video_url'] == "https://storage.example.com/video.mp4"
        assert delivery['release_timestamp'] == 3.5
        assert delivery['speed'] == "125 km/h"
        assert delivery['status'] == "success"

    def test_get_delivery_not_found(self):
        """Test getting a non-existent delivery."""
        delivery = get_delivery("non-existent-id")
        assert delivery is None

    def test_insert_delivery_minimal(self):
        """Test inserting delivery with minimal fields."""
        delivery_id = "test-delivery-002"
        insert_delivery(
            delivery_id=delivery_id,
            sequence=2,
            cloud_video_url="https://storage.example.com/video2.mp4",
            cloud_thumbnail_url=""
        )

        delivery = get_delivery(delivery_id)
        assert delivery is not None
        assert delivery['speed'] is None
        assert delivery['report'] is None

    def test_insert_delivery_replace(self):
        """Test that insert replaces existing delivery."""
        delivery_id = "test-delivery-003"

        # Insert initial
        insert_delivery(
            delivery_id=delivery_id,
            sequence=3,
            cloud_video_url="https://old-url.com",
            cloud_thumbnail_url=""
        )

        # Replace with new data
        insert_delivery(
            delivery_id=delivery_id,
            sequence=3,
            cloud_video_url="https://new-url.com",
            cloud_thumbnail_url="",
            speed="130 km/h"
        )

        delivery = get_delivery(delivery_id)
        assert delivery['cloud_video_url'] == "https://new-url.com"
        assert delivery['speed'] == "130 km/h"

    def test_get_deliveries_list(self):
        """Test getting list of deliveries."""
        # Insert several deliveries
        for i in range(5):
            insert_delivery(
                delivery_id=f"list-test-{i}",
                sequence=100 + i,
                cloud_video_url=f"https://storage.example.com/video{i}.mp4",
                cloud_thumbnail_url=""
            )

        deliveries = get_deliveries(limit=50)
        assert len(deliveries) >= 5

    def test_get_deliveries_limit(self):
        """Test delivery list respects limit."""
        # Insert many deliveries
        for i in range(10):
            insert_delivery(
                delivery_id=f"limit-test-{i}",
                sequence=200 + i,
                cloud_video_url=f"https://storage.example.com/video{i}.mp4",
                cloud_thumbnail_url=""
            )

        deliveries = get_deliveries(limit=3)
        assert len(deliveries) == 3

    def test_get_next_delivery_sequence(self):
        """Test getting next delivery sequence number."""
        current_seq = get_next_delivery_sequence()
        assert current_seq >= 1

        # Insert a delivery and check increment
        insert_delivery(
            delivery_id="seq-test-001",
            sequence=current_seq,
            cloud_video_url="https://test.com",
            cloud_thumbnail_url=""
        )

        next_seq = get_next_delivery_sequence()
        assert next_seq == current_seq + 1

    def test_delivery_with_all_fields(self):
        """Test delivery with all fields populated."""
        delivery_id = "full-delivery-001"
        insert_delivery(
            delivery_id=delivery_id,
            sequence=500,
            cloud_video_url="https://storage.example.com/full.mp4",
            cloud_thumbnail_url="https://storage.example.com/thumb.jpg",
            release_timestamp=4.2,
            speed="140 km/h",
            report="Excellent technique with high arm action",
            tips="Maintain this form",
            status="success"
        )

        delivery = get_delivery(delivery_id)
        assert delivery['sequence'] == 500
        assert delivery['cloud_thumbnail_url'] == "https://storage.example.com/thumb.jpg"
        assert delivery['release_timestamp'] == 4.2
        assert delivery['report'] == "Excellent technique with high arm action"
        assert delivery['tips'] == "Maintain this form"

    def test_delivery_status_types(self):
        """Test different delivery status values."""
        statuses = ["success", "failed", "pending", "analyzing"]

        for i, status in enumerate(statuses):
            delivery_id = f"status-test-{i}"
            insert_delivery(
                delivery_id=delivery_id,
                sequence=600 + i,
                cloud_video_url="https://test.com",
                cloud_thumbnail_url="",
                status=status
            )

            delivery = get_delivery(delivery_id)
            assert delivery['status'] == status


class TestDatabaseInit:
    """Tests for database initialization."""

    def test_init_db_creates_tables(self):
        """Test that init_db creates required tables."""
        import sqlite3
        from database import DB_NAME

        # Re-init to ensure tables exist
        init_db()

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        # Check summaries table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'")
        assert cursor.fetchone() is not None

        # Check deliveries table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='deliveries'")
        assert cursor.fetchone() is not None

        conn.close()

    def test_init_db_idempotent(self):
        """Test that init_db can be called multiple times safely."""
        # Should not raise any errors
        init_db()
        init_db()
        init_db()

        # Tables should still work
        insert_summary(999, "Idempotent test", "0", "club")
        summaries = get_summaries()
        assert any(s['summary'] == "Idempotent test" for s in summaries)
