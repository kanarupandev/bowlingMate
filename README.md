# BowlingMate

**AI-native cricket bowling analysis.** Identify. Analyze. Improve.

Built for the **Google Gemini 3 Hackathon 2026**.

## The Problem

Cricket is the second most popular sport on Earth — 2.5 billion fans, 300+ million active players. Bowling is a biomechanically complex full-body action where technique determines speed, accuracy, and longevity.

Professional biomechanical analysis costs $100+/session, requires specialized facilities, and is booked weeks in advance. Most bowlers practice alone with zero feedback — repeating the same technical flaws session after session.

## The Solution

Record yourself bowling anywhere — backyard, park, nets. BowlingMate does the rest:

1. **Scout** (Gemini 3 Flash) scans your video and finds every delivery in seconds — detecting the peak arm arc from raw video bytes
2. **Clipper** (AVFoundation) extracts a precision 5-second clip around each ball release — no re-encoding
3. **Expert** (Gemini 3 Pro) performs deep biomechanical analysis across 6 phases with actionable tips
4. **Overlay** (MediaPipe) generates a skeleton visualization with color-coded joint feedback

Works with shadow bowling (no ball needed). From a Chennai backyard to a Melbourne academy — same analysis.

## Zero Classical CV Architecture

**BowlingMate has no YOLO, no OpenCV for detection, no frame extraction, no pose estimation in the detection pipeline.** Gemini 3's native multimodal video understanding is the sole vision engine.

```
Traditional pipeline:
  Video → Frame extraction → YOLO → Pose estimation → LLM → Output
  (4 models, 3 preprocessing steps)

BowlingMate pipeline:
  Video → Gemini 3 → Output
  (1 model, 0 preprocessing steps)
```

## Architecture

```
Video Input
    |
    v
[Scout] Gemini 3 Flash ──> Delivery timestamps (~15s per 2-min chunk)
    |
    v
[Clipper] AVFoundation ──> 5s clip [T-3s, T+2s] (bitstream passthrough)
    |
    v
[Expert] Gemini 3 Pro ──> 6-phase biomechanical analysis + speed estimate (~25s)
    |
    v
[Overlay] MediaPipe ──> Skeleton visualization (green/red/yellow joints)
```

### Gemini 3 Features Used

| Feature | How BowlingMate Uses It |
|---------|------------------------|
| **Native video understanding** | Raw MP4 bytes sent directly — no frame extraction, no preprocessing |
| **Split-stack (Flash + Pro)** | Flash for speed (scan minutes cheaply), Pro for depth (deep reasoning on 5s clips). ~80% cost reduction |
| **Structured JSON output** | `response_mime_type: "application/json"` for reliable parsing by iOS client |
| **Inline video bytes** | Small clips (<5MB) sent directly, skipping File API — saves ~5s latency |
| **SSE streaming** | Real-time feedback during Expert analysis (~25s) via Server-Sent Events |

### The Scout vs Expert Split

| Agent | Model | Purpose | Latency |
|-------|-------|---------|---------|
| **Scout** | `gemini-3-flash-preview` | Detect bowling deliveries in video chunks via multimodal analysis | ~15s/chunk |
| **Expert** | `gemini-3-pro-preview` | 6-phase biomechanical analysis with structured JSON output | ~25-30s |
| **Chat** | `gemini-3-pro-preview` | Interactive follow-up conversation with video context | ~5s/turn |

*Speed where it matters. Depth where it counts.*

## 6-Phase Biomechanical Analysis

The Expert analyzes each delivery across:

| Phase | What's Analyzed |
|-------|----------------|
| **Run-up** | Rhythm, balance, momentum build-up |
| **Loading/Coil** | Hip-shoulder separation, torque generation |
| **Release Action** | Arm path, release point consistency, elbow extension |
| **Wrist/Snap** | Seam position, spin generation |
| **Head/Eyes** | Stability at release, target focus |
| **Follow-through** | Energy dissipation, balance, injury risk |

Each phase receives a status (GOOD / NEEDS WORK), a specific observation, and an actionable tip.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| iOS App | SwiftUI, AVFoundation, Combine |
| Backend | Python 3.11, FastAPI, LangGraph |
| AI Models | Google Gemini 3 Flash + Pro (multimodal) |
| Pose Detection | MediaPipe 0.10.21 |
| Storage | Google Cloud Storage |
| Deployment | Cloud Run (2 vCPU, 2GB RAM) |
| CI/CD | GitHub Actions |

## Project Structure

```
bowlingMate/
├── backend/                    # FastAPI backend
│   ├── main.py                 # All API endpoints + auth middleware
│   ├── agent.py                # LangGraph Expert workflow + streaming
│   ├── config.py               # Pydantic Settings (env-based config)
│   ├── prompts.py              # Gemini prompt templates (6-phase analysis)
│   ├── prompts/                # External prompt files
│   │   ├── detect_action_prompt.txt   # Scout prompt
│   │   └── coach_chat_prompt.txt      # Chat prompt
│   ├── mediapipe_overlay.py    # Pose detection + skeleton rendering
│   ├── storage.py              # GCS upload/download + thumbnails
│   ├── database.py             # SQLite persistence
│   ├── rag.py                  # Knowledge retrieval (cricket domain)
│   ├── utils.py                # Shared utilities
│   ├── Dockerfile              # Production container
│   ├── requirements.txt        # Python dependencies
│   ├── .env.example            # Environment variable template
│   └── tests/                  # Test suite (18 test files)
├── ios/
│   └── wellBowled/             # SwiftUI application (30 source files)
│       ├── BowlViewModel.swift        # Central state management
│       ├── NetworkService.swift       # HTTP client + SSE streaming
│       ├── VideoActionDetector.swift  # Scout integration
│       ├── PassthroughClipper.swift   # Bitstream clip extraction
│       ├── ContentView.swift          # Main app layout
│       ├── AnalysisResultView.swift   # 3-page swipe analysis view
│       ├── CoachChatPage.swift        # Interactive follow-up chat
│       └── ...
├── .github/workflows/
│   └── deploy-backend.yml      # Auto-deploy to Cloud Run on push
└── README.md
```

## Backend API

All endpoints require `Authorization: Bearer <API_SECRET>` header.

### Core Endpoints

#### `POST /detect-action`
**Scout** — detect bowling deliveries in a video chunk.

```
Request:  multipart/form-data { file: video.mp4 }
Response: {
  "found": true,
  "deliveries_detected_at_time": [1.3, 8.7, 15.2],
  "total_count": 3
}
```

#### `POST /analyze`
Accept a video clip for Expert analysis. Returns a video_id for streaming.

```
Request:  multipart/form-data { file: clip.mp4, config: "club", language: "en" }
Response: { "status": "accepted", "video_id": "uuid" }
```

#### `GET /stream-analysis`
SSE stream of Expert analysis results. Connect after `/analyze`.

```
Params:   ?video_id=uuid&config=club&language=en&generate_overlay=true
Response: Server-Sent Events (SSE)
  data: {"status": "event", "message": "Expert AI (Gemini 3 Pro) Thinking...", "type": "info"}
  data: {
    "status": "success",
    "report": "Summary of technique...",
    "speed_est": "85 km/h",
    "phases": [
      {"name": "Run-up", "status": "GOOD", "observation": "...", "tip": "..."},
      {"name": "Release Action", "status": "NEEDS WORK", "observation": "...", "tip": "..."}
    ],
    "tips": ["Tip 1", "Tip 2"],
    "release_timestamp": 3.0,
    "effort": "Medium",
    "latency": 27.5
  }
```

#### `POST /generate-overlay`
Generate MediaPipe skeleton overlay video with phase-based color coding.

```
Request:  multipart/form-data { video: clip.mp4, phases: "[{...}]" }
Response: { "status": "success", "overlay_url": "https://..." }
```

### Storage Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `POST /upload-clip` | POST | Persist clip + thumbnail to GCS |
| `GET /media/{type}/{id}` | GET | Stream video/thumbnail from GCS |
| `GET /clip/{id}/signed-url` | GET | Fresh signed URL (15 min expiry) |
| `GET /deliveries` | GET | List all deliveries (session history) |

### Utility Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/debug-gemini` | GET | Smoke test Gemini API key |
| `/debug-overlay` | GET | Test MediaPipe installation |

## Getting Started

### Backend

```bash
cd backend
cp .env.example .env
# Edit .env — add your GOOGLE_API_KEY

pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080
```

### Docker (Production)

```bash
cd backend
docker build -t bowlingmate .
docker run -p 8080:8080 --env-file .env bowlingmate
```

First build takes ~30 minutes (MediaPipe compilation). Subsequent builds ~8 min with cache.

### iOS

1. Copy `ios/wellBowled/` into your Xcode project
2. Update `AppConfig.swift` with your backend URL
3. Build for iOS 17+ device (camera required)

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_API_KEY` | Yes | — | Gemini API key |
| `API_SECRET` | Yes | — | Bearer token for API auth |
| `SCOUT_MODEL` | No | `gemini-3-flash-preview` | Scout detection model |
| `COACH_MODEL` | No | `gemini-3-pro-preview` | Expert analysis model |
| `ENABLE_OVERLAY` | No | `true` | MediaPipe skeleton overlay |
| `GCS_BUCKET_NAME` | No | `wellbowled-clips` | GCS bucket for clip storage |
| `ANALYSIS_TIMEOUT` | No | `500` | Max analysis time (seconds) |

## Tests

```bash
cd backend
pytest tests/ -v
```

## Deployment

Pushes to `main` touching `backend/**` auto-deploy to Cloud Run via GitHub Actions.

## The Numbers

- **2.5 billion** cricket followers worldwide
- **$100+** per professional biomechanical session
- **6 phases** analyzed per delivery
- **~15 seconds** to scan a 60-second video
- **~25 seconds** for deep biomechanical analysis
- **0** classical CV models required
- **0** balls required (shadow bowling works)

---

*Elite analysis without elite pricing.*
