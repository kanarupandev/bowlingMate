def test_analyze_endpoint(client):
    """Test that /analyze accepts video and returns video_id for streaming."""
    # Create dummy file content
    file_content = b"fake video bytes"

    response = client.post(
        "/analyze",
        data={"config": "junior", "language": "en"},
        files={"video": ("test.mov", file_content, "video/quicktime")}
    )

    # Verify Response - new API returns status and video_id
    assert response.status_code == 200
    data = response.json()
    assert data['status'] == "accepted"
    assert 'video_id' in data
    # video_id should be a valid UUID
    import uuid
    uuid.UUID(data['video_id'])  # Raises if not valid UUID
