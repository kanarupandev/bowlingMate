# BowlingMate API Documentation

**Base URL**: `https://bowlingmate-m4xzkste5q-uc.a.run.app`

## Authentication

All endpoints (except `/` and `/docs`) require authentication via Bearer token:

```
Authorization: Bearer <API_SECRET>
```

Unauthenticated requests return `401 Unauthorized`.

---

## Core Pipeline

### 1. Detect Deliveries (Scout)

**`POST /detect-action`**

Scans a video chunk for bowling deliveries using Gemini 3 Flash. The Scout detects the peak arm arc — works even with shadow bowling (no ball needed).

**Request**
```
Content-Type: multipart/form-data

file: <video.mp4>   (required)
```

**Response** `200 OK`
```json
{
  "found": true,
  "deliveries_detected_at_time": [1.3, 8.7, 15.2],
  "total_count": 3
}
```

| Field | Type | Description |
|-------|------|-------------|
| `found` | bool | Whether any deliveries were detected |
| `deliveries_detected_at_time` | float[] | Timestamps (seconds) of each delivery |
| `total_count` | int | Number of deliveries found |

**Latency**: ~15s per 2-minute video chunk

---

### 2. Submit for Analysis (Expert)

**`POST /analyze`**

Accepts a video clip and returns a `video_id` for streaming analysis results.

**Request**
```
Content-Type: multipart/form-data

video: <clip.mp4>     (required)
config: "club"         (optional, default: "club")
language: "en"         (optional, default: "en")
```

| Config Level | Description |
|-------------|-------------|
| `junior` | Simple language, encouraging tone |
| `club` | Direct, motivational feedback |
| `technical` | Analytical, biomechanical detail |

**Response** `200 OK`
```json
{
  "status": "accepted",
  "video_id": "4060713e-eb2e-43f9-83db-eec1184378ad"
}
```

Use the `video_id` to connect to the SSE stream.

---

### 3. Stream Analysis Results (Expert)

**`GET /stream-analysis`**

Server-Sent Events (SSE) stream of Expert analysis. Connect immediately after `/analyze`.

**Query Parameters**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `video_id` | string | — | Required. From `/analyze` response |
| `config` | string | `"club"` | Analysis depth level |
| `language` | string | `"en"` | Response language |
| `generate_overlay` | bool | `false` | Also generate MediaPipe skeleton overlay |

**SSE Events**

Event 1 — Status update:
```
data: {"status": "event", "message": "Expert AI (Gemini 3 Pro) Thinking...", "type": "info"}
```

Event 2 — Analysis result:
```
data: {
  "status": "success",
  "report": "Great high-arm release creates bounce, but stabilizing the head will improve consistency.",
  "speed_est": "75 km/h",
  "phases": [
    {
      "name": "Run-up",
      "status": "GOOD",
      "observation": "Rhythmical approach with decent momentum leading into the crease.",
      "tip": "Ensure the approach angle is consistent to aid alignment.",
      "clip_ts": 0.6
    },
    {
      "name": "Loading/Coil",
      "status": "NEEDS WORK",
      "observation": "Shoulders remain somewhat open; front arm pull is passive.",
      "tip": "Close your shoulders more and pull the non-bowling arm down harder for torque.",
      "clip_ts": 1.1
    },
    {
      "name": "Release Action",
      "status": "GOOD",
      "observation": "Nice high arm action with a vertical release point.",
      "tip": "Maintain this high release to maximize bounce and dip.",
      "clip_ts": 1.3
    },
    {
      "name": "Wrist/Snap",
      "status": "GOOD",
      "observation": "Clear wrist engagement at the top to impart spin.",
      "tip": "Focus on ripping 'over' the ball to generate top-spin.",
      "clip_ts": 1.35
    },
    {
      "name": "Head/Eyes",
      "status": "NEEDS WORK",
      "observation": "Head falls away slightly to the off-side at the moment of delivery.",
      "tip": "Keep your chin up and eyes level on the target throughout the release.",
      "clip_ts": 1.3
    },
    {
      "name": "Follow-through",
      "status": "GOOD",
      "observation": "Shoulder rotates fully and back leg comes through effectively.",
      "tip": "Try to finish balanced and ready to field.",
      "clip_ts": 1.8
    }
  ],
  "tips": ["Tip 1", "Tip 2", "..."],
  "release_timestamp": 1.3,
  "bowl_id": 1770632437,
  "effort": "Medium",
  "latency": 37.25
}
```

Event 3 — Overlay (if `generate_overlay=true`):
```
data: {"status": "overlay", "overlay_url": "https://storage.googleapis.com/..."}
```

**Phase Object**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Phase name: Run-up, Loading/Coil, Release Action, Wrist/Snap, Head/Eyes, Follow-through |
| `status` | string | `"GOOD"` or `"NEEDS WORK"` |
| `observation` | string | What the Expert observed |
| `tip` | string | Actionable coaching tip |
| `clip_ts` | float | Timestamp in clip (seconds) where this phase occurs |

**Latency**: ~25-35s

---

### 4. Interactive Chat

**`POST /chat`**

Follow-up coaching conversation with Gemini 3 Pro. The Expert can reference specific phases and control video playback via function calling.

**Request** `application/json`
```json
{
  "message": "Can you explain more about my release action?",
  "delivery_id": "4060713e-eb2e-43f9-83db-eec1184378ad",
  "phases": [
    {"name": "Release Action", "status": "GOOD", "clip_ts": 1.3, "observation": "...", "tip": "..."}
  ]
}
```

**Response** `200 OK`
```json
{
  "text": "Your release point is actually quite high, which is excellent for generating bounce...",
  "video_action": {
    "action": "focus",
    "timestamp": 1.3
  }
}
```

| Video Action | Description |
|-------------|-------------|
| `focus` | Loop video at `timestamp` in slow-motion (0.5x) |
| `pause` | Stop playback |
| `play` | Resume normal playback |

**Latency**: ~5s

---

### 5. Generate Overlay

**`POST /generate-overlay`**

Generates a MediaPipe skeleton overlay video with phase-based color coding.

**Request**
```
Content-Type: multipart/form-data

video: <clip.mp4>    (required)
phases: "[{...}]"     (required, JSON string of phases array)
```

**Color Coding**

| Joint Color | Meaning |
|------------|---------|
| Green | Good form |
| Red | Injury risk |
| Yellow | Needs work |

**Response** `200 OK`
```json
{
  "status": "success",
  "overlay_url": "https://storage.googleapis.com/bowlingmate-clips/overlays/uuid.mp4"
}
```

---

## Storage

### Upload Clip

**`POST /upload-clip`**

Persist a video clip and auto-generated thumbnail to Google Cloud Storage.

**Request**
```
Content-Type: multipart/form-data

file: <clip.mp4>              (required)
release_timestamp: 3.0         (optional, float)
speed: "75 km/h"              (optional, string)
report: "Summary text..."      (optional, string)
tips: "Tip1\nTip2"            (optional, string)
```

**Response** `200 OK`
```json
{
  "delivery_id": "uuid",
  "video_url": "https://bowlingmate-m4xzkste5q-uc.a.run.app/media/video/uuid",
  "thumbnail_url": "https://bowlingmate-m4xzkste5q-uc.a.run.app/media/thumb/uuid"
}
```

---

### Stream Media

**`GET /media/{media_type}/{delivery_id}`**

Stream video or thumbnail from GCS through the backend. No public GCS access needed.

| Parameter | Values |
|-----------|--------|
| `media_type` | `video` (returns video/mp4) or `thumb` (returns image/jpeg) |
| `delivery_id` | UUID from upload-clip response |

**Response**: Binary stream with appropriate content type.

---

### Get Signed URL

**`GET /clip/{delivery_id}/signed-url`**

Generate a fresh signed URL for direct video playback (15-minute expiry).

**Response** `200 OK`
```json
{
  "video_url": "https://storage.googleapis.com/bowlingmate-clips/clips/uuid.mp4?X-Goog-Signature=..."
}
```

---

### List Deliveries

**`GET /deliveries`**

Get all deliveries for session history, newest first.

**Query Parameters**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | 50 | Maximum number of deliveries to return |

**Response** `200 OK`
```json
{
  "deliveries": [
    {
      "delivery_id": "uuid",
      "sequence": 1,
      "cloud_video_url": "...",
      "cloud_thumbnail_url": "...",
      "release_timestamp": 3.0,
      "speed": "75 km/h",
      "report": "...",
      "tips": "...",
      "created_at": "2026-02-09T10:00:00"
    }
  ]
}
```

---

## Diagnostics

### Health Check

**`GET /`** (no auth required)

```json
{"status": "ok", "service": "BowlingMate-backend", "model": "gemini-3-pro-preview"}
```

### Debug Gemini

**`GET /debug-gemini`**

Smoke test the Gemini API key and model connection.

```json
{
  "status": "success",
  "key_used": "AIza...xxxx",
  "model_used": "gemini-3-pro-preview",
  "gemini_response": "Gemini REST OK"
}
```

### Debug Overlay

**`GET /debug-overlay`**

Check MediaPipe, OpenCV, and FFmpeg installation status.

```json
{
  "enable_overlay": true,
  "mock_scout": false,
  "mock_coach": false,
  "mediapipe_available": true,
  "opencv_version": "4.11.0",
  "ffmpeg_available": true
}
```

---

## Error Responses

All errors follow this format:

```json
{"status": "error", "message": "Description of what went wrong"}
```

| HTTP Code | Meaning |
|-----------|---------|
| 401 | Missing or invalid `Authorization` header |
| 404 | Media not found in GCS |
| 500 | Internal server error (check logs) |

## Rate Limits

No application-level rate limits. Gemini API has its own per-project quotas. The backend uses `ANALYSIS_TIMEOUT=500s` as a safety timeout for long-running analyses.
