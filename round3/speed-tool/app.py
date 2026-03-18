"""
Speed Tool — Upload video, detect deliveries, scrub frames, measure speed.

Usage:
    pip install -r requirements.txt
    GOOGLE_API_KEY=xxx python app.py

Then open http://localhost:8000
"""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Optional: Gemini for auto-detection
try:
    from google import genai
    GEMINI_AVAILABLE = bool(os.environ.get("GOOGLE_API_KEY"))
except ImportError:
    GEMINI_AVAILABLE = False

app = FastAPI(title="Speed Tool")

# Storage
APP_DIR = Path(__file__).parent
SAMPLES_DIR = APP_DIR / "samples"
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="speed_tool_"))
CLIPS_DIR = UPLOAD_DIR / "clips"
FRAMES_DIR = UPLOAD_DIR / "frames"
CLIPS_DIR.mkdir(exist_ok=True)
FRAMES_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(exist_ok=True)

# State
sessions = {}


# ──────────────────────────────────────────────────────────
# Video Processing
# ──────────────────────────────────────────────────────────

def get_video_info(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0
    cap.release()
    return {
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration": duration,
    }


def extract_clip(video_path: str, center_frame: int, fps: float, clip_id: str) -> dict:
    """Extract 3s clip: 1.5s before center + 1.5s after center."""
    before_frames = int(fps * 1.5)
    after_frames = int(fps * 1.5)
    start_frame = max(0, center_frame - before_frames)
    end_frame = center_frame + after_frames

    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    end_frame = min(end_frame, total)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    clip_path = str(CLIPS_DIR / f"{clip_id}.mp4")
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(clip_path, fourcc, fps, (width, height))

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frames_written = 0
    for i in range(start_frame, end_frame):
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(frame)
        frames_written += 1

    writer.release()
    cap.release()

    # Extract all frames as JPEG for scrubbing
    clip_frames_dir = FRAMES_DIR / clip_id
    clip_frames_dir.mkdir(exist_ok=True)

    cap2 = cv2.VideoCapture(clip_path)
    idx = 0
    while True:
        ret, frame = cap2.read()
        if not ret:
            break
        # Resize for web (max 640px wide)
        scale = min(640 / width, 480 / height, 1.0)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(width * scale), int(height * scale)))
        cv2.imwrite(str(clip_frames_dir / f"{idx:04d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        idx += 1
    cap2.release()

    return {
        "clip_id": clip_id,
        "clip_path": clip_path,
        "start_frame": start_frame,
        "end_frame": end_frame,
        "frame_count": frames_written,
        "release_frame_in_clip": center_frame - start_frame,
        "fps": fps,
    }


def extract_frame_image(video_path: str, frame_num: int) -> str:
    """Extract a single frame as JPEG."""
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        return None
    path = str(UPLOAD_DIR / f"frame_{frame_num}.jpg")
    cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return path


# ──────────────────────────────────────────────────────────
# Gemini Delivery Detection
# ──────────────────────────────────────────────────────────

DETECT_PROMPT = """You are analyzing a cricket bowling video recorded at {fps} frames per second.

Find ALL bowling deliveries in this video. For each delivery, identify the frame number
where the ball is released from the bowler's hand.

Return STRICT JSON only:
{{
  "deliveries": [
    {{"release_frame": 847, "confidence": 0.95}},
    {{"release_frame": 2103, "confidence": 0.90}}
  ]
}}

Rules:
- release_frame is the 0-indexed frame number where the ball leaves the hand
- confidence is 0.0-1.0
- If no deliveries found, return {{"deliveries": []}}
- Only return deliveries you are confident about
"""


async def detect_deliveries_gemini(video_path: str, fps: float) -> list:
    """Use Gemini to find delivery release frames."""
    if not GEMINI_AVAILABLE:
        return []

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    # Upload video
    uploaded = client.files.upload(file=video_path)

    # Wait for processing
    while uploaded.state.name == "PROCESSING":
        time.sleep(2)
        uploaded = client.files.get(name=uploaded.name)

    if uploaded.state.name != "ACTIVE":
        return []

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[uploaded, DETECT_PROMPT.format(fps=int(fps))],
        config={
            "temperature": 0.0,
            "response_mime_type": "application/json",
        },
    )

    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return result.get("deliveries", [])
    except Exception as e:
        print(f"Gemini parse error: {e}")
        return []


# ──────────────────────────────────────────────────────────
# Speed Calculation
# ──────────────────────────────────────────────────────────

GATE_DISTANCES = {
    "full_pitch": 20.12,
    "crease_to_crease": 17.68,
    "crease_to_far_stumps": 18.90,
    "half_pitch": 10.06,
    "marker_10m": 10.0,
    "custom": None,
}


def calculate_speed(release_frame: int, gate_frame: int, fps: float,
                    gate: str, custom_distance: float = None) -> dict:
    """Calculate speed from two frame numbers."""
    distance = GATE_DISTANCES.get(gate, custom_distance)
    if distance is None:
        distance = custom_distance
    if distance is None or distance <= 0:
        return {"error": "Invalid distance"}

    frame_diff = gate_frame - release_frame
    if frame_diff <= 0:
        return {"error": "Gate frame must be after release frame"}

    time_s = frame_diff / fps
    speed_ms = distance / time_s
    speed_kph = speed_ms * 3.6

    # Error estimate (±1 frame per gate)
    time_min = (frame_diff - 2) / fps
    time_max = (frame_diff + 2) / fps
    speed_max = (distance / time_min) * 3.6 if time_min > 0 else 0
    speed_min = (distance / time_max) * 3.6
    error = (speed_max - speed_min) / 2

    speed_mph = speed_kph * 0.621371

    return {
        "speed_kph": round(speed_kph, 1),
        "speed_mph": round(speed_mph, 1),
        "distance_m": distance,
        "frame_diff": frame_diff,
        "time_s": round(time_s, 4),
        "error_kph": round(error, 1),
        "error_mph": round(error * 0.621371, 1),
        "gate": gate,
    }


# ──────────────────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.get("/samples")
async def list_samples():
    """List all videos in samples dir (includes uploads)."""
    videos = []
    for f in sorted(SAMPLES_DIR.iterdir()):
        if f.suffix.lower() in (".mov", ".mp4", ".m4v"):
            thumb = f.with_suffix(".jpg")
            info = get_video_info(str(f))
            videos.append({
                "filename": f.name,
                "thumbnail": f"/sample-thumb/{f.stem}.jpg" if thumb.exists() else None,
                "duration": round(info["duration"], 1),
                "fps": info["fps"],
                "resolution": f"{info['width']}x{info['height']}",
            })
    return videos


@app.get("/sample-thumb/{name}")
async def sample_thumbnail(name: str):
    """Serve a sample thumbnail."""
    path = SAMPLES_DIR / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(str(path), media_type="image/jpeg")


@app.post("/load-sample")
async def load_sample(filename: str):
    """Load a sample video as if it were uploaded."""
    video_path = str(SAMPLES_DIR / filename)
    if not Path(video_path).exists():
        raise HTTPException(404, "Sample not found")

    info = get_video_info(video_path)
    session_id = filename.replace(".", "_")

    # Skip Gemini for sample loading — user can enter frame manually
    sessions[session_id] = {
        "video_path": video_path,
        "info": info,
        "deliveries": [],
        "clips": [],
    }

    return {
        "session_id": session_id,
        "info": info,
        "deliveries": [],
        "gemini_available": GEMINI_AVAILABLE,
    }


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video, save to samples, get video info + auto-detected deliveries."""
    # Save to samples dir (persistent)
    video_path = str(SAMPLES_DIR / file.filename)
    with open(video_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Generate thumbnail
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total // 2)
    ret, frame = cap.read()
    if ret:
        h, w = frame.shape[:2]
        scale = 240 / w
        thumb = cv2.resize(frame, (240, int(h * scale)))
        thumb_path = str(SAMPLES_DIR / Path(file.filename).with_suffix(".jpg"))
        cv2.imwrite(thumb_path, thumb, [cv2.IMWRITE_JPEG_QUALITY, 80])
    cap.release()

    info = get_video_info(video_path)
    session_id = file.filename.replace(".", "_")

    sessions[session_id] = {
        "video_path": video_path,
        "info": info,
        "deliveries": [],
        "clips": [],
    }

    return {
        "session_id": session_id,
        "info": info,
        "deliveries": [],
        "gemini_available": GEMINI_AVAILABLE,
    }


@app.get("/video-frame/{session_id}/{frame_num}")
async def get_video_frame(session_id: str, frame_num: int):
    """Get a single frame from the full video."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Cache frames in a session-specific dir
    vframes_dir = FRAMES_DIR / f"full_{session_id}"
    vframes_dir.mkdir(exist_ok=True)
    frame_path = vframes_dir / f"{frame_num:06d}.jpg"

    if not frame_path.exists():
        cap = cv2.VideoCapture(session["video_path"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            raise HTTPException(404, "Frame not found")
        h, w = frame.shape[:2]
        scale = min(640 / w, 480 / h, 1.0)
        if scale < 1.0:
            frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
        cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

    return FileResponse(str(frame_path), media_type="image/jpeg")


@app.post("/extract-clip")
async def extract_clip_endpoint(session_id: str, release_frame: int):
    """Extract a 3s clip around a release frame."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    clip_id = f"{session_id}_d{len(session['clips'])}"
    clip = extract_clip(
        session["video_path"],
        release_frame,
        session["info"]["fps"],
        clip_id,
    )

    session["clips"].append(clip)
    return clip


@app.get("/frame/{clip_id}/{frame_num}")
async def get_frame(clip_id: str, frame_num: int):
    """Get a single frame image from a clip."""
    frame_path = FRAMES_DIR / clip_id / f"{frame_num:04d}.jpg"
    if not frame_path.exists():
        raise HTTPException(404, "Frame not found")
    return FileResponse(str(frame_path), media_type="image/jpeg")


@app.post("/calculate-speed")
async def calculate_speed_endpoint(
    release_frame: int,
    gate_frame: int,
    fps: float,
    gate: str = "stumps",
    custom_distance: float = None,
):
    """Calculate speed from marked frames."""
    result = calculate_speed(release_frame, gate_frame, fps, gate, custom_distance)
    return result


# ──────────────────────────────────────────────────────────
# Frontend
# ──────────────────────────────────────────────────────────

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Speed Tool — Hit the stumps, get your speed</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Mono', monospace;
    background: #0D1117; color: #e6edf3;
    max-width: 900px; margin: 0 auto; padding: 20px;
}
h1 { color: #006D77; margin-bottom: 4px; font-size: 24px; }
.subtitle { color: #8DA9C4; font-size: 14px; margin-bottom: 20px; }
h2 { color: #8DA9C4; margin: 20px 0 10px; font-size: 18px; }

.upload-zone {
    border: 2px dashed #30363d; border-radius: 12px;
    padding: 40px; text-align: center; cursor: pointer;
    transition: border-color 0.2s;
}
.upload-zone:hover { border-color: #006D77; }
.upload-zone.active { border-color: #006D77; background: #006D7710; }
input[type="file"] { display: none; }

.info { background: #161b22; border-radius: 8px; padding: 16px; margin: 12px 0; font-size: 14px; }
.info span { color: #8DA9C4; }

.btn {
    background: #006D77; color: white; border: none; border-radius: 6px;
    padding: 8px 16px; cursor: pointer; font-family: inherit; font-size: 14px;
}
.btn:hover { background: #008891; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn.active { background: #238636; border-color: #238636; }

.scrubber { margin: 16px 0; }
.frame-display {
    background: #000; border-radius: 8px; overflow: hidden;
    display: flex; justify-content: center; align-items: center;
    min-height: 300px; position: relative;
}
.frame-display img { max-width: 100%; max-height: 480px; }
.frame-counter {
    position: absolute; top: 10px; right: 10px;
    background: #000000cc; color: #fff; padding: 4px 10px;
    border-radius: 4px; font-size: 13px; font-family: 'SF Mono', monospace;
}

.controls { display: flex; align-items: center; gap: 8px; margin: 10px 0; }
.controls button {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 14px; cursor: pointer;
    font-family: inherit; font-size: 16px; min-width: 44px;
}
.controls button:hover { background: #30363d; }

input[type="range"] { flex: 1; accent-color: #006D77; height: 6px; }

.marks { display: flex; gap: 12px; margin: 12px 0; font-size: 14px; }
.mark-box {
    background: #161b22; border-radius: 8px; padding: 12px 16px; flex: 1;
}
.mark-box .label { color: #8DA9C4; font-size: 12px; }
.mark-box .value { font-size: 20px; margin-top: 4px; }
.mark-box .value.set { color: #238636; }

.distance-row {
    display: flex; align-items: center; gap: 10px; margin: 16px 0;
    background: #161b22; border-radius: 8px; padding: 12px 16px;
}
.distance-row label { color: #8DA9C4; font-size: 13px; white-space: nowrap; }
.distance-row input {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 12px; font-family: inherit;
    font-size: 18px; width: 100px; text-align: center;
}
.distance-row .unit { color: #8DA9C4; font-size: 14px; }

.speed-result {
    background: #006D7720; border: 2px solid #006D77; border-radius: 12px;
    padding: 24px; text-align: center; margin: 20px 0;
}
.speed-result .speed { font-size: 56px; font-weight: bold; color: #006D77; }
.speed-result .speed-secondary { font-size: 28px; color: #8DA9C4; margin-top: 4px; }
.speed-result .unit { font-size: 20px; color: #8DA9C4; }
.speed-result .detail { font-size: 13px; color: #8DA9C4; margin-top: 8px; }

.hidden { display: none; }
.loading { color: #8DA9C4; font-style: italic; }

.keyboard-help {
    background: #161b22; border-radius: 8px; padding: 10px 16px;
    font-size: 12px; color: #8DA9C4; margin: 12px 0;
}
.keyboard-help kbd {
    background: #21262d; border: 1px solid #30363d; border-radius: 3px;
    padding: 2px 6px; font-family: inherit;
}

.sample-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px; margin: 16px 0;
}
.sample-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    overflow: hidden; cursor: pointer; transition: border-color 0.2s;
}
.sample-card:hover { border-color: #006D77; }
.sample-card img { width: 100%; height: 120px; object-fit: cover; }
.sample-card .meta { padding: 8px; font-size: 12px; color: #8DA9C4; }
.sample-card .name { color: #e6edf3; font-size: 13px; margin-bottom: 4px; }

.mark-buttons { display: flex; gap: 8px; margin: 10px 0; }
.mark-buttons button {
    flex: 1; padding: 12px; font-size: 15px; border-radius: 8px;
    border: 2px solid; cursor: pointer; font-family: inherit; font-weight: 600;
    transition: all 0.15s;
}
.mark-buttons .release-btn {
    background: #006D7720; border-color: #006D77; color: #006D77;
}
.mark-buttons .release-btn:hover { background: #006D7740; }
.mark-buttons .release-btn.active { background: #006D77; color: white; }
.mark-buttons .stumps-btn {
    background: #da363420; border-color: #da3634; color: #da3634;
}
.mark-buttons .stumps-btn:hover { background: #da363440; }
.mark-buttons .stumps-btn.active { background: #da3634; color: white; }
</style>
</head>
<body>

<h1>Speed Tool</h1>
<p class="subtitle">Hit the stumps, get your speed.</p>

<!-- Step 1: Upload or pick sample -->
<div id="step-upload">
    <div class="upload-zone" onclick="document.getElementById('file-input').click()" id="drop-zone">
        <p style="font-size: 18px; margin-bottom: 8px;">Drop video here or click to upload</p>
        <p style="color: #8DA9C4; font-size: 14px;">iPhone slo-mo (120fps / 240fps) recommended</p>
    </div>
    <input type="file" id="file-input" accept="video/*" onchange="uploadVideo(this.files[0])">
    <div id="upload-status"></div>

    <h2>Or pick from library</h2>
    <div class="sample-grid" id="sample-grid"></div>
</div>

<!-- Step 2: Browse + measure -->
<div id="step-browse" class="hidden">
    <div class="info" id="video-info"></div>

    <div class="keyboard-help">
        <kbd>&larr;</kbd> / <kbd>&rarr;</kbd> &plusmn;1 frame &nbsp;
        <kbd>Shift</kbd>+arrows &plusmn;10 &nbsp;
        <kbd>R</kbd> mark release &nbsp;
        <kbd>S</kbd> mark stumps hit &nbsp;
        <kbd>Space</kbd> play/pause &nbsp;
        <kbd>C</kbd> clear marks
    </div>

    <div class="scrubber">
        <div class="frame-display">
            <img id="browse-img" src="" alt="frame">
            <div class="frame-counter" id="browse-counter">0 / 0</div>
        </div>
        <div class="controls">
            <button onclick="browseStep(-10)">-10</button>
            <button onclick="browseStep(-1)">&larr;</button>
            <input type="range" id="browse-slider" min="0" max="0" value="0"
                   oninput="browseSeek(parseInt(this.value))">
            <button onclick="browseStep(1)">&rarr;</button>
            <button onclick="browseStep(10)">+10</button>
        </div>
    </div>

    <div class="mark-buttons">
        <button class="release-btn" id="btn-release" onclick="markRelease()">
            Mark Release (R)
        </button>
        <button class="stumps-btn" id="btn-stumps" onclick="markStumps()">
            Stumps Hit! (S)
        </button>
    </div>

    <div class="marks">
        <div class="mark-box">
            <div class="label">Release Frame</div>
            <div class="value" id="release-value">&mdash;</div>
        </div>
        <div class="mark-box">
            <div class="label">Stumps Hit Frame</div>
            <div class="value" id="stumps-value">&mdash;</div>
        </div>
        <div class="mark-box">
            <div class="label">Transit</div>
            <div class="value" id="diff-value">&mdash;</div>
        </div>
    </div>

    <div class="distance-row">
        <label>Crease to stumps:</label>
        <input type="number" id="distance-input" value="18.90" step="0.1" min="1" max="30">
        <span class="unit">metres</span>
        <button class="btn" onclick="calcSpeed()" id="btn-calc" disabled>
            Calculate Speed
        </button>
    </div>

    <div id="speed-result" class="hidden">
        <div class="speed-result">
            <div class="speed" id="speed-kph">&mdash;</div>
            <div class="unit">km/h</div>
            <div class="speed-secondary" id="speed-mph">&mdash;</div>
            <div class="unit" style="font-size:14px;">mph</div>
            <div class="detail" id="speed-detail"></div>
        </div>
    </div>

    <div style="margin-top:20px; display:flex; gap:8px;">
        <button class="btn" onclick="clearMarks()">Clear Marks</button>
        <button class="btn" onclick="resetToUpload()" style="background:#21262d;border:1px solid #30363d;">
            &larr; Back to Library
        </button>
    </div>
</div>

<script>
let state = {
    sessionId: null,
    fps: 120,
    totalFrames: 0,
    currentFrame: 0,
    releaseFrame: null,
    stumpsFrame: null,
    playing: false,
    playTimer: null,
};

// ── Samples ──

async function loadSamples() {
    try {
        const res = await fetch('/samples');
        const samples = await res.json();
        const grid = document.getElementById('sample-grid');
        grid.innerHTML = '';
        if (samples.length === 0) {
            grid.innerHTML = '<p style="color:#8DA9C4;font-size:14px;">No videos yet. Upload one.</p>';
            return;
        }
        samples.forEach(s => {
            const card = document.createElement('div');
            card.className = 'sample-card';
            card.onclick = () => loadSample(s.filename);
            card.innerHTML = `
                ${s.thumbnail ? `<img src="${s.thumbnail}" alt="${s.filename}">` : '<div style="height:120px;background:#21262d;"></div>'}
                <div class="meta">
                    <div class="name">${s.filename}</div>
                    ${s.fps}fps | ${s.duration}s | ${s.resolution}
                </div>`;
            grid.appendChild(card);
        });
    } catch (err) { console.error('Failed to load samples:', err); }
}

async function loadSample(filename) {
    const status = document.getElementById('upload-status');
    status.innerHTML = '<p class="loading">Loading...</p>';
    try {
        const res = await fetch(`/load-sample?filename=${encodeURIComponent(filename)}`, { method: 'POST' });
        handleVideoLoaded(await res.json());
        status.innerHTML = '';
    } catch (err) {
        status.innerHTML = `<p style="color:#f85149;">Error: ${err.message}</p>`;
    }
}

loadSamples();

// ── Upload ──

async function uploadVideo(file) {
    if (!file) return;
    const status = document.getElementById('upload-status');
    status.innerHTML = '<p class="loading">Uploading ' + file.name + '...</p>';
    document.getElementById('drop-zone').classList.add('active');
    const formData = new FormData();
    formData.append('file', file);
    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        handleVideoLoaded(await res.json());
        status.innerHTML = '';
        loadSamples();
    } catch (err) {
        status.innerHTML = `<p style="color:#f85149;">Error: ${err.message}</p>`;
    }
}

function handleVideoLoaded(data) {
    state.sessionId = data.session_id;
    state.fps = data.info.fps;
    state.totalFrames = data.info.frame_count;
    state.currentFrame = 0;

    const info = data.info;
    document.getElementById('video-info').innerHTML = `
        <span>FPS:</span> ${info.fps} &nbsp;|&nbsp;
        <span>Frames:</span> ${info.frame_count} &nbsp;|&nbsp;
        <span>Resolution:</span> ${info.width}&times;${info.height} &nbsp;|&nbsp;
        <span>Duration:</span> ${info.duration.toFixed(1)}s
    `;

    document.getElementById('browse-slider').max = state.totalFrames - 1;
    document.getElementById('browse-slider').value = 0;
    clearMarks();

    document.getElementById('step-upload').classList.add('hidden');
    document.getElementById('step-browse').classList.remove('hidden');
    browseSeek(0);
}

// Drag and drop
const dropZone = document.getElementById('drop-zone');
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('active'); });
dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('active'); });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault(); dropZone.classList.remove('active');
    if (e.dataTransfer.files.length > 0) uploadVideo(e.dataTransfer.files[0]);
});

// ── Frame Navigation ──

function browseSeek(n) {
    n = Math.max(0, Math.min(n, state.totalFrames - 1));
    state.currentFrame = n;
    document.getElementById('browse-slider').value = n;
    const t = (n / state.fps).toFixed(2);
    document.getElementById('browse-counter').textContent = `${n} / ${state.totalFrames - 1}  (${t}s)`;
    document.getElementById('browse-img').src = `/video-frame/${state.sessionId}/${n}`;
}

function browseStep(delta) { browseSeek(state.currentFrame + delta); }

function togglePlay() {
    if (state.playing) {
        clearInterval(state.playTimer); state.playing = false;
    } else {
        state.playing = true;
        state.playTimer = setInterval(() => {
            if (state.currentFrame >= state.totalFrames - 1) {
                clearInterval(state.playTimer); state.playing = false; return;
            }
            browseSeek(state.currentFrame + 1);
        }, 1000 / 30);
    }
}

// ── Marking ──

function markRelease() {
    state.releaseFrame = state.currentFrame;
    const t = (state.releaseFrame / state.fps).toFixed(2);
    document.getElementById('release-value').textContent = `Frame ${state.releaseFrame} (${t}s)`;
    document.getElementById('release-value').classList.add('set');
    document.getElementById('btn-release').classList.add('active');
    updateDiff();
}

function markStumps() {
    state.stumpsFrame = state.currentFrame;
    const t = (state.stumpsFrame / state.fps).toFixed(2);
    document.getElementById('stumps-value').textContent = `Frame ${state.stumpsFrame} (${t}s)`;
    document.getElementById('stumps-value').classList.add('set');
    document.getElementById('btn-stumps').classList.add('active');
    updateDiff();
}

function updateDiff() {
    if (state.releaseFrame !== null && state.stumpsFrame !== null) {
        const diff = state.stumpsFrame - state.releaseFrame;
        const t = (diff / state.fps).toFixed(4);
        document.getElementById('diff-value').textContent = `${diff} frames (${t}s)`;
        document.getElementById('diff-value').classList.add('set');
        document.getElementById('btn-calc').disabled = false;
    }
}

function clearMarks() {
    state.releaseFrame = null;
    state.stumpsFrame = null;
    document.getElementById('release-value').textContent = '\\u2014';
    document.getElementById('release-value').classList.remove('set');
    document.getElementById('stumps-value').textContent = '\\u2014';
    document.getElementById('stumps-value').classList.remove('set');
    document.getElementById('diff-value').textContent = '\\u2014';
    document.getElementById('diff-value').classList.remove('set');
    document.getElementById('btn-release').classList.remove('active');
    document.getElementById('btn-stumps').classList.remove('active');
    document.getElementById('btn-calc').disabled = true;
    document.getElementById('speed-result').classList.add('hidden');
}

// ── Speed Calculation ──

async function calcSpeed() {
    if (state.releaseFrame === null || state.stumpsFrame === null) return;

    const distance = parseFloat(document.getElementById('distance-input').value);
    if (!distance || distance <= 0) { alert('Enter a valid distance'); return; }

    const params = new URLSearchParams({
        release_frame: state.releaseFrame,
        gate_frame: state.stumpsFrame,
        fps: state.fps,
        gate: 'custom',
        custom_distance: distance,
    });

    const res = await fetch(`/calculate-speed?${params}`, { method: 'POST' });
    const data = await res.json();

    if (data.error) { alert(data.error); return; }

    document.getElementById('speed-kph').textContent = data.speed_kph;
    document.getElementById('speed-mph').textContent = data.speed_mph;
    document.getElementById('speed-detail').textContent =
        `${data.distance_m}m in ${data.time_s}s | ${data.frame_diff} frames @ ${state.fps}fps | \\u00B1${data.error_kph} kph`;
    document.getElementById('speed-result').classList.remove('hidden');
}

// ── Navigation ──

function resetToUpload() {
    if (state.playing) { clearInterval(state.playTimer); state.playing = false; }
    state.sessionId = null;
    clearMarks();
    document.getElementById('step-browse').classList.add('hidden');
    document.getElementById('step-upload').classList.remove('hidden');
    loadSamples();
}

// ── Keyboard ──

document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (document.getElementById('step-browse').classList.contains('hidden')) return;

    switch (e.key) {
        case 'ArrowLeft':  e.preventDefault(); browseStep(e.shiftKey ? -10 : -1); break;
        case 'ArrowRight': e.preventDefault(); browseStep(e.shiftKey ? 10 : 1); break;
        case 'r': case 'R': markRelease(); break;
        case 's': case 'S': markStumps(); break;
        case 'c': case 'C': clearMarks(); break;
        case ' ': e.preventDefault(); togglePlay(); break;
    }
});
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"Temp dir: {UPLOAD_DIR}")
    print(f"Open http://localhost:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
