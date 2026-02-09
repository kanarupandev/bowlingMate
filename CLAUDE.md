# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

wellBowled is a cricket bowling analysis platform: iOS app captures video → cloud AI detects deliveries and provides biomechanical coaching feedback. Built for the Gemini 3 Hackathon 2026.

## Critical Rules

- **Gemini 3 models ONLY**: Scout uses `gemini-3-flash-preview`, Coach uses `gemini-3-pro-preview`. Never substitute other models.
- **Never mock responses**: Let API calls fail naturally. No fake/stub responses.
- **Never force push**: Other agents work on this repo. No `--force` or `-f` on push.
- **Always rebase**: Run `git pull --rebase` before every push.
- **Push immediately**: Every incremental commit must be pushed right away.
- **Merge conflicts**: Always notify user and ask for input before resolving.
- **Docker Compose**: Use `docker compose` (not `docker-compose`).
- **MediaPipe version**: Must use `mediapipe==0.10.21` — solutions API removed in 0.10.30+.

## Build & Run Commands

### Backend (FastAPI)
```bash
# Local dev
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# Run all tests
cd backend && pytest tests/ -v

# Run single test file
cd backend && pytest tests/test_api.py -v

# Run with coverage
cd backend && pytest tests/ --cov --cov-report=html

# Deploy to Cloud Run (auto-triggered on push to main touching backend/**)
# Manual: uses .github/workflows/deploy-backend.yml or ./deploy_cloud_run.sh
```

### iOS (SwiftUI)
```bash
# Sync source of truth to Xcode project
rm -rf /Users/kanarupan/workspace/xcodeProj/wellBowled/wellBowled/*.swift && \
cp -R /Users/kanarupan/workspace/wellBowled/ios/wellBowled/ \
     /Users/kanarupan/workspace/xcodeProj/wellBowled/wellBowled/

# Build
xcodebuild -project /Users/kanarupan/workspace/xcodeProj/wellBowled/wellBowled.xcodeproj \
  -scheme wellBowled -destination "platform=iOS Simulator,name=iPhone 16 Pro" build
```

## Architecture: Scout → Clipper → Coach → Overlay

### Pipeline Flow
1. **Scout** (Gemini 3 Flash): Video split into chunks → `POST /detect-action` → returns delivery timestamps (~7-15s per chunk)
2. **Clipper** (local AVFoundation): Extracts 5s clip [T-3s, T+2s] via bitstream passthrough (no re-encoding)
3. **Coach** (Gemini 3 Pro): `POST /analyze` → `GET /stream-analysis` (SSE) → 6-phase biomechanical analysis, speed estimate, tips (~25-30s)
4. **Overlay** (MediaPipe): Skeleton visualization with phase-based color coding → uploaded to GCS

### Backend (`/backend/`)
- **main.py**: FastAPI app — all endpoints, auth middleware (Bearer token), CORS, in-memory video cache
- **agent.py**: LangGraph workflow — Gemini File API upload, streaming Coach analysis, JSON parsing
- **config.py**: Pydantic Settings — all env vars with defaults. Key toggles: `MOCK_SCOUT`, `MOCK_COACH`, `ENABLE_OVERLAY`
- **prompts.py**: Gemini prompt templates for 6-phase biomechanical analysis
- **storage.py**: GCS wrapper — clip upload/download, thumbnail generation via FFmpeg
- **database.py**: SQLite — `summaries` and `deliveries` tables
- **mediapipe_overlay.py**: Pose detection + skeleton rendering (green=good, red=injury risk, yellow=weak)

### iOS (`/ios/wellBowled/`)
- **BowlViewModel.swift**: Central @MainActor state management — session/history/favorites, recording, analysis orchestration
- **NetworkService.swift**: Protocol-based HTTP client with Real/Mock/Composite routing based on AppConfig flags
- **VideoActionDetector.swift**: VisionEngine implementation — exports chunks, calls Scout, deduplicates (2.0s threshold)
- **PassthroughClipper.swift**: Bitstream video extraction (no re-encoding)
- **Models.swift**: `Delivery` struct with status enum (detecting → clipping → queued → analyzing → success/failed)
- **AppConfig.swift**: Feature flags, URLs, auth token. Source of truth for `ios/wellBowled/`, synced to Xcode project for builds

### Key API Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/detect-action` | POST | Scout: detect deliveries in video chunk |
| `/analyze` | POST | Accept video, return video_id |
| `/stream-analysis` | GET | SSE stream of Coach analysis results |
| `/upload-clip` | POST | Persist clip + thumbnail to GCS |
| `/media/video/{id}` | GET | Stream video from GCS |
| `/debug-gemini` | GET | Smoke test Gemini API key |

## Environment Variables (backend/.env)
```
GOOGLE_API_KEY=...                    # Required: Gemini API key
API_SECRET=wellbowled-hackathon-secret
GEMINI_MODEL_NAME=gemini-3-pro-preview
SCOUT_MODEL=gemini-3-flash-preview
MOCK_SCOUT=true                       # Set false for real detection
MOCK_COACH=true                       # Set false for real analysis
ENABLE_OVERLAY=false                  # MediaPipe skeleton (adds ~25min to Docker build)
GCS_BUCKET_NAME=wellbowled-clips
ANALYSIS_TIMEOUT=500
```

## Deployment
- **Cloud Run**: `wellbowled` service in `us-central1`, 2GB RAM / 2 CPU, port 8080
- **CI/CD**: GitHub Actions on push to `main` touching `backend/**` — OIDC auth, 1-hour Cloud Build timeout (MediaPipe is heavy)
- **URL**: `https://wellbowled-506790672773.us-central1.run.app`

## Commit Convention
```
git commit -m "feat|fix|test|chore(scope): description"
```
Commit after each feature/fix, push immediately with rebase.
