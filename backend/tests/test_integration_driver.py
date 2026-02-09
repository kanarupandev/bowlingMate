"""
Integration Test Driver - Simulates iOS Frontend Calls

This test uses REAL Gemini API calls (no mocking) to verify the full pipeline:
1. Scout: /detect-action - Detect bowling in video chunk
2. Upload: /analyze - Upload video for analysis
3. Coach: /stream-analysis - Stream analysis results (SSE)

Requires:
- GOOGLE_API_KEY environment variable
- Backend running (set BACKEND_URL env var)
- Test video files available

NOTE: These tests are SKIPPED by default unless RUN_INTEGRATION_TESTS=1 is set.
This prevents CI failures when backend isn't running.
"""

import os
import sys
import json
import time
import httpx
import pytest
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import get_settings

# Test configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
TEST_VIDEO_PATH = Path(__file__).parent.parent / "temp_videos" / "chunk_10s.mp4"
FULL_VIDEO_PATH = Path(__file__).parent.parent / "test_video.mp4"

# Skip integration tests unless explicitly enabled
SKIP_INTEGRATION = os.getenv("RUN_INTEGRATION_TESTS", "0") != "1"
pytestmark = pytest.mark.skipif(SKIP_INTEGRATION, reason="Integration tests disabled. Set RUN_INTEGRATION_TESTS=1 to run.")


def get_auth_headers():
    """Get authentication headers matching iOS app."""
    settings = get_settings()
    return {"X-WellBowled-Secret": settings.API_SECRET}


class TestScoutDetection:
    """Test Scout (detect-action) endpoint with real video."""

    @pytest.mark.skipif(not TEST_VIDEO_PATH.exists(), reason="Test video not found")
    def test_detect_action_with_real_video(self):
        """
        Simulates iOS VideoActionDetector calling /detect-action.

        iOS Code Reference (VideoActionDetector.swift:45):
            CompositeNetworkService.shared.detectAction(videoChunkURL: tempUrl)
        """
        print(f"\n🎬 Testing Scout with: {TEST_VIDEO_PATH}")
        print(f"   Video size: {TEST_VIDEO_PATH.stat().st_size / 1024:.1f} KB")

        with open(TEST_VIDEO_PATH, "rb") as f:
            video_bytes = f.read()

        start_time = time.time()

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{BACKEND_URL}/detect-action",
                headers=get_auth_headers(),
                files={"file": ("chunk.mp4", video_bytes, "video/mp4")}
            )

        elapsed = time.time() - start_time
        print(f"   Response time: {elapsed:.2f}s")
        print(f"   Status: {response.status_code}")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        data = response.json()
        print(f"   Result: {json.dumps(data, indent=2)}")

        # Validate response structure (matches iOS ActionDetectionResult)
        assert "found" in data, "Response missing 'found' field"
        assert isinstance(data["found"], bool), "'found' should be boolean"

        if data["found"]:
            assert "timestamp" in data, "Detection found but missing timestamp"
            assert "confidence" in data, "Detection found but missing confidence"
            print(f"   ✅ BOWLING DETECTED at {data['timestamp']}s (confidence: {data['confidence']})")
        else:
            print(f"   ⚠️ No bowling detected in this chunk")

        return data

    @pytest.mark.skipif(not TEST_VIDEO_PATH.exists(), reason="Test video not found")
    def test_detect_action_response_format(self):
        """Verify response format matches iOS expectations."""
        with open(TEST_VIDEO_PATH, "rb") as f:
            video_bytes = f.read()

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{BACKEND_URL}/detect-action",
                headers=get_auth_headers(),
                files={"file": ("chunk.mp4", video_bytes, "video/mp4")}
            )

        data = response.json()

        # iOS expects: struct ActionDetectionResult { found: Bool, timestamp: Double? }
        assert "found" in data
        if data["found"]:
            # timestamp should be a number when found=true
            assert data["timestamp"] is None or isinstance(data["timestamp"], (int, float))


class TestCoachAnalysis:
    """Test Coach (analyze + stream-analysis) endpoints."""

    @pytest.mark.skipif(not TEST_VIDEO_PATH.exists(), reason="Test video not found")
    def test_analyze_upload(self):
        """
        Simulates iOS uploading video via /analyze endpoint.

        iOS Code Reference (BowlViewModel.swift):
            networkService.prefetchUpload(videoURL: url, config: config, language: "en")
        """
        print(f"\n📤 Testing Upload with: {TEST_VIDEO_PATH}")

        with open(TEST_VIDEO_PATH, "rb") as f:
            video_bytes = f.read()

        start_time = time.time()

        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                f"{BACKEND_URL}/analyze",
                headers=get_auth_headers(),
                data={"config": "club", "language": "en"},
                files={"video": ("test.mov", video_bytes, "video/quicktime")}
            )

        elapsed = time.time() - start_time
        print(f"   Response time: {elapsed:.2f}s")
        print(f"   Status: {response.status_code}")

        assert response.status_code == 200

        data = response.json()
        print(f"   Result: {json.dumps(data, indent=2)}")

        # Should return video_id for streaming
        assert "video_id" in data or "status" in data

        return data

    @pytest.mark.skipif(not TEST_VIDEO_PATH.exists(), reason="Test video not found")
    def test_stream_analysis_sse(self):
        """
        Simulates iOS consuming SSE stream from /stream-analysis.

        iOS Code Reference (BowlViewModel.swift):
            networkService.streamAnalysis(videoID: videoID, videoURL: nil, config: config, language: "en")
        """
        # First upload video
        with open(TEST_VIDEO_PATH, "rb") as f:
            video_bytes = f.read()

        with httpx.Client(timeout=120.0) as client:
            upload_response = client.post(
                f"{BACKEND_URL}/analyze",
                headers=get_auth_headers(),
                data={"config": "club", "language": "en"},
                files={"video": ("test.mov", video_bytes, "video/quicktime")}
            )

        if upload_response.status_code != 200:
            pytest.skip("Upload failed, cannot test streaming")

        upload_data = upload_response.json()
        video_id = upload_data.get("video_id")

        if not video_id:
            pytest.skip("No video_id returned from upload")

        print(f"\n📡 Testing SSE Stream for video_id: {video_id}")

        # Stream analysis (SSE)
        events = []
        start_time = time.time()

        with httpx.Client(timeout=300.0) as client:
            with client.stream(
                "GET",
                f"{BACKEND_URL}/stream-analysis",
                params={"video_id": video_id, "config": "club", "language": "en"},
                headers=get_auth_headers()
            ) as response:
                assert response.status_code == 200
                assert "text/event-stream" in response.headers.get("content-type", "")

                for line in response.iter_lines():
                    if line.startswith("data:"):
                        event_data = line[5:].strip()
                        events.append(event_data)
                        print(f"   SSE Event: {event_data[:100]}...")

                        # Check for completion
                        if '"type":"complete"' in event_data or '"type":"error"' in event_data:
                            break

        elapsed = time.time() - start_time
        print(f"   Total stream time: {elapsed:.2f}s")
        print(f"   Events received: {len(events)}")

        assert len(events) > 0, "Should receive at least one SSE event"


class TestFullPipeline:
    """Test complete frontend flow: Scout -> Upload -> Coach."""

    @pytest.mark.skipif(not TEST_VIDEO_PATH.exists(), reason="Test video not found")
    def test_complete_flow(self):
        """
        Simulates complete iOS flow:
        1. User imports video
        2. VideoActionDetector scans chunks for bowling
        3. When found, extract clip and upload
        4. Stream analysis results
        """
        print("\n" + "="*60)
        print("🏏 FULL PIPELINE TEST - Simulating iOS Frontend")
        print("="*60)

        # Step 1: Scout Detection
        print("\n[1/3] SCOUT: Detecting bowling action...")
        with open(TEST_VIDEO_PATH, "rb") as f:
            video_bytes = f.read()

        with httpx.Client(timeout=120.0) as client:
            scout_response = client.post(
                f"{BACKEND_URL}/detect-action",
                headers=get_auth_headers(),
                files={"file": ("chunk.mp4", video_bytes, "video/mp4")}
            )

        assert scout_response.status_code == 200
        scout_data = scout_response.json()
        print(f"      Result: found={scout_data.get('found')}, "
              f"timestamp={scout_data.get('timestamp')}, "
              f"confidence={scout_data.get('confidence')}")

        # Step 2: Upload (regardless of detection for test purposes)
        print("\n[2/3] UPLOAD: Sending video for analysis...")
        with httpx.Client(timeout=120.0) as client:
            upload_response = client.post(
                f"{BACKEND_URL}/analyze",
                headers=get_auth_headers(),
                data={"config": "club", "language": "en"},
                files={"video": ("clip.mov", video_bytes, "video/quicktime")}
            )

        assert upload_response.status_code == 200
        upload_data = upload_response.json()
        video_id = upload_data.get("video_id")
        print(f"      video_id: {video_id}")

        if not video_id:
            print("      ⚠️ No video_id - skipping stream test")
            return

        # Step 3: Stream Analysis
        print("\n[3/3] COACH: Streaming analysis...")
        events_received = 0
        final_result = None

        with httpx.Client(timeout=300.0) as client:
            with client.stream(
                "GET",
                f"{BACKEND_URL}/stream-analysis",
                params={"video_id": video_id, "config": "club", "language": "en"},
                headers=get_auth_headers()
            ) as response:
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        events_received += 1
                        event_data = line[5:].strip()

                        try:
                            parsed = json.loads(event_data)
                            if parsed.get("type") == "complete":
                                final_result = parsed
                                break
                            elif parsed.get("type") == "error":
                                print(f"      ❌ Error: {parsed.get('message')}")
                                break
                        except json.JSONDecodeError:
                            pass

        print(f"      Events received: {events_received}")

        if final_result:
            print("\n" + "-"*40)
            print("📊 ANALYSIS RESULT:")
            print("-"*40)
            if "speed" in final_result:
                print(f"   Speed: {final_result.get('speed')}")
            if "summary" in final_result:
                print(f"   Summary: {final_result.get('summary')}")
            if "phases" in final_result:
                for phase in final_result.get("phases", []):
                    status = "✅" if phase.get("status") == "GOOD" else "⚠️"
                    print(f"   {status} {phase.get('name')}: {phase.get('observation', 'N/A')}")

        print("\n" + "="*60)
        print("✅ PIPELINE TEST COMPLETE")
        print("="*60)


# CLI Runner
if __name__ == "__main__":
    """
    Run directly: python test_integration_driver.py

    Usage:
        # Test against local backend
        python test_integration_driver.py

        # Test against deployed backend
        BACKEND_URL=https://your-backend.run.app python test_integration_driver.py
    """
    import argparse

    parser = argparse.ArgumentParser(description="Backend Integration Test Driver")
    parser.add_argument("--url", default=BACKEND_URL, help="Backend URL")
    parser.add_argument("--video", default=str(TEST_VIDEO_PATH), help="Video file path")
    parser.add_argument("--scout-only", action="store_true", help="Only test Scout detection")
    args = parser.parse_args()

    # Override globals
    BACKEND_URL = args.url
    if args.video:
        TEST_VIDEO_PATH = Path(args.video)

    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Video: {TEST_VIDEO_PATH}")
    print(f"Video exists: {TEST_VIDEO_PATH.exists()}")

    if not TEST_VIDEO_PATH.exists():
        print("❌ Test video not found!")
        sys.exit(1)

    # Run tests
    test_scout = TestScoutDetection()
    result = test_scout.test_detect_action_with_real_video()

    if not args.scout_only:
        test_pipeline = TestFullPipeline()
        test_pipeline.test_complete_flow()
