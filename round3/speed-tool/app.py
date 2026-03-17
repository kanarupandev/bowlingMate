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
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="speed_tool_"))
CLIPS_DIR = UPLOAD_DIR / "clips"
FRAMES_DIR = UPLOAD_DIR / "frames"
CLIPS_DIR.mkdir(exist_ok=True)
FRAMES_DIR.mkdir(exist_ok=True)

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


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Upload a video, get video info + auto-detected deliveries."""
    # Save uploaded file
    video_path = str(UPLOAD_DIR / file.filename)
    with open(video_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    info = get_video_info(video_path)
    session_id = file.filename.replace(".", "_")

    # Auto-detect deliveries with Gemini
    deliveries = await detect_deliveries_gemini(video_path, info["fps"])

    sessions[session_id] = {
        "video_path": video_path,
        "info": info,
        "deliveries": deliveries,
        "clips": [],
    }

    return {
        "session_id": session_id,
        "info": info,
        "deliveries": deliveries,
        "gemini_available": GEMINI_AVAILABLE,
    }


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
<title>Speed Tool</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Mono', monospace;
    background: #0D1117; color: #e6edf3;
    max-width: 900px; margin: 0 auto; padding: 20px;
}
h1 { color: #006D77; margin-bottom: 20px; font-size: 24px; }
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

.delivery-list { display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }
.delivery-btn {
    background: #006D77; color: white; border: none; border-radius: 6px;
    padding: 8px 16px; cursor: pointer; font-family: inherit; font-size: 14px;
}
.delivery-btn:hover { background: #008891; }

/* Frame scrubber */
.scrubber { margin: 20px 0; }
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

.controls { display: flex; align-items: center; gap: 8px; margin: 12px 0; }
.controls button {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 14px; cursor: pointer;
    font-family: inherit; font-size: 16px; min-width: 44px;
}
.controls button:hover { background: #30363d; }
.controls button.mark {
    background: #006D77; border-color: #006D77; color: white; font-size: 14px;
}
.controls button.mark:hover { background: #008891; }
.controls button.mark.active { background: #238636; border-color: #238636; }

input[type="range"] {
    flex: 1; accent-color: #006D77; height: 6px;
}

.marks {
    display: flex; gap: 20px; margin: 12px 0; font-size: 14px;
}
.mark-display {
    background: #161b22; border-radius: 8px; padding: 12px 16px; flex: 1;
}
.mark-display .label { color: #8DA9C4; font-size: 12px; }
.mark-display .value { font-size: 20px; margin-top: 4px; }
.mark-display .value.set { color: #238636; }

/* Gate selection */
.gate-select {
    margin: 12px 0; display: flex; gap: 8px; align-items: center;
}
.gate-select select {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 12px; font-family: inherit;
}
.gate-select input {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 12px; font-family: inherit; width: 100px;
}

/* Speed result */
.speed-result {
    background: #006D7720; border: 2px solid #006D77; border-radius: 12px;
    padding: 24px; text-align: center; margin: 20px 0;
}
.speed-result .speed { font-size: 48px; font-weight: bold; color: #006D77; }
.speed-result .unit { font-size: 20px; color: #8DA9C4; }
.speed-result .detail { font-size: 14px; color: #8DA9C4; margin-top: 8px; }

.hidden { display: none; }
.loading { color: #8DA9C4; font-style: italic; }

.keyboard-help {
    background: #161b22; border-radius: 8px; padding: 12px 16px;
    font-size: 12px; color: #8DA9C4; margin: 12px 0;
}
.keyboard-help kbd {
    background: #21262d; border: 1px solid #30363d; border-radius: 3px;
    padding: 2px 6px; font-family: inherit;
}
</style>
</head>
<body>

<h1>Speed Tool</h1>

<!-- Step 1: Upload -->
<div id="step-upload">
    <div class="upload-zone" onclick="document.getElementById('file-input').click()" id="drop-zone">
        <p style="font-size: 18px; margin-bottom: 8px;">Drop video here or click to upload</p>
        <p style="color: #8DA9C4; font-size: 14px;">iPhone slo-mo (120fps / 240fps) recommended</p>
    </div>
    <input type="file" id="file-input" accept="video/*" onchange="uploadVideo(this.files[0])">
    <div id="upload-status"></div>
</div>

<!-- Step 2: Deliveries -->
<div id="step-deliveries" class="hidden">
    <div class="info" id="video-info"></div>
    <h2>Deliveries Detected</h2>
    <div id="delivery-list" class="delivery-list"></div>
    <div id="delivery-status"></div>
</div>

<!-- Step 3: Frame Scrubber -->
<div id="step-scrubber" class="hidden">
    <h2>Scrub to Mark Frames</h2>

    <div class="keyboard-help">
        <kbd>←</kbd> / <kbd>→</kbd> ±1 frame &nbsp;
        <kbd>Shift+←</kbd> / <kbd>Shift+→</kbd> ±10 frames &nbsp;
        <kbd>R</kbd> mark release &nbsp;
        <kbd>G</kbd> mark gate &nbsp;
        <kbd>Space</kbd> play/pause
    </div>

    <div class="scrubber">
        <div class="frame-display" id="frame-display">
            <img id="frame-img" src="" alt="frame">
            <div class="frame-counter" id="frame-counter">0 / 0</div>
        </div>
        <div class="controls">
            <button onclick="stepFrames(-10)" title="-10 frames">⏪</button>
            <button onclick="stepFrames(-1)" title="-1 frame">◀</button>
            <input type="range" id="frame-slider" min="0" max="0" value="0"
                   oninput="seekFrame(parseInt(this.value))">
            <button onclick="stepFrames(1)" title="+1 frame">▶</button>
            <button onclick="stepFrames(10)" title="+10 frames">⏩</button>
        </div>
        <div class="controls">
            <button class="mark" id="btn-release" onclick="markRelease()">
                Mark Release (R)
            </button>
            <button class="mark" id="btn-gate" onclick="markGate()">
                Mark Gate (G)
            </button>
        </div>
    </div>

    <div class="marks">
        <div class="mark-display">
            <div class="label">Release Frame</div>
            <div class="value" id="release-value">—</div>
        </div>
        <div class="mark-display">
            <div class="label">Gate Frame</div>
            <div class="value" id="gate-value">—</div>
        </div>
        <div class="mark-display">
            <div class="label">Frame Diff</div>
            <div class="value" id="diff-value">—</div>
        </div>
    </div>

    <div class="gate-select">
        <span style="color: #8DA9C4;">Gate:</span>
        <select id="gate-type" onchange="toggleCustomDistance()">
            <option value="crease_to_far_stumps">Bowling Crease to Striker Stumps (18.90m)</option>
            <option value="full_pitch">Full Pitch — Stumps to Stumps (20.12m)</option>
            <option value="crease_to_crease">Crease to Crease (17.68m)</option>
            <option value="half_pitch">Half Pitch (10.06m)</option>
            <option value="marker_10m">10m Marker (10.0m)</option>
            <option value="custom">Custom Distance</option>
        </select>
        <input type="number" id="custom-distance" class="hidden"
               placeholder="metres" step="0.01" min="0.1">
        <button class="mark" onclick="calcSpeed()" id="btn-calc" disabled>
            Calculate Speed
        </button>
    </div>

    <div id="speed-result" class="hidden">
        <div class="speed-result">
            <div class="speed" id="speed-value">—</div>
            <div class="unit" id="speed-unit">km/h</div>
            <div class="speed" id="speed-value-mph" style="font-size:28px;color:#8DA9C4;margin-top:4px;">—</div>
            <div class="unit" style="font-size:14px;color:#8DA9C4;">mph</div>
            <div class="detail" id="speed-detail"></div>
        </div>
    </div>
</div>

<script>
let state = {
    sessionId: null,
    fps: 120,
    clipId: null,
    totalFrames: 0,
    currentFrame: 0,
    releaseFrame: null,
    gateFrame: null,
    releaseFrameInClip: null,
    playing: false,
    playTimer: null,
};

// ── Upload ──

async function uploadVideo(file) {
    if (!file) return;

    const status = document.getElementById('upload-status');
    status.innerHTML = '<p class="loading">Uploading and analyzing...</p>';
    document.getElementById('drop-zone').classList.add('active');

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const data = await res.json();

        state.sessionId = data.session_id;
        state.fps = data.info.fps;

        // Show video info
        const info = data.info;
        document.getElementById('video-info').innerHTML = `
            <span>FPS:</span> ${info.fps} &nbsp;|&nbsp;
            <span>Frames:</span> ${info.frame_count} &nbsp;|&nbsp;
            <span>Resolution:</span> ${info.width}×${info.height} &nbsp;|&nbsp;
            <span>Duration:</span> ${info.duration.toFixed(1)}s &nbsp;|&nbsp;
            <span>Gemini:</span> ${data.gemini_available ? '✓' : '✗'}
        `;

        // Show deliveries
        const list = document.getElementById('delivery-list');
        list.innerHTML = '';

        if (data.deliveries.length > 0) {
            data.deliveries.forEach((d, i) => {
                const btn = document.createElement('button');
                btn.className = 'delivery-btn';
                const timeSec = (d.release_frame / state.fps).toFixed(2);
                btn.textContent = `Delivery ${i + 1} — frame ${d.release_frame} (${timeSec}s)`;
                btn.onclick = () => loadClip(d.release_frame);
                list.appendChild(btn);
            });
        } else {
            document.getElementById('delivery-status').innerHTML =
                '<p class="info">No deliveries auto-detected. Enter release frame manually:</p>' +
                '<div class="controls" style="margin-top:8px;">' +
                '<input type="number" id="manual-frame" placeholder="Release frame #" ' +
                'style="background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:8px 12px;font-family:inherit;width:160px;">' +
                '<button class="delivery-btn" onclick="loadClip(parseInt(document.getElementById(\'manual-frame\').value))">Extract Clip</button>' +
                '</div>';
        }

        document.getElementById('step-upload').classList.add('hidden');
        document.getElementById('step-deliveries').classList.remove('hidden');
        status.innerHTML = '';

    } catch (err) {
        status.innerHTML = `<p style="color:#f85149;">Error: ${err.message}</p>`;
    }
}

// Drag and drop
const dropZone = document.getElementById('drop-zone');
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('active'); });
dropZone.addEventListener('dragleave', () => { dropZone.classList.remove('active'); });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('active');
    if (e.dataTransfer.files.length > 0) uploadVideo(e.dataTransfer.files[0]);
});

// ── Clip Loading ──

async function loadClip(releaseFrame) {
    if (!releaseFrame || isNaN(releaseFrame)) return;

    document.getElementById('delivery-status').innerHTML = '<p class="loading">Extracting 3s clip...</p>';

    const res = await fetch(`/extract-clip?session_id=${state.sessionId}&release_frame=${releaseFrame}`, {
        method: 'POST'
    });
    const clip = await res.json();

    state.clipId = clip.clip_id;
    state.totalFrames = clip.frame_count;
    state.releaseFrameInClip = clip.release_frame_in_clip;
    state.currentFrame = 0;
    state.releaseFrame = null;
    state.gateFrame = null;

    // Update UI
    document.getElementById('frame-slider').max = state.totalFrames - 1;
    document.getElementById('frame-slider').value = 0;
    document.getElementById('release-value').textContent = '—';
    document.getElementById('release-value').classList.remove('set');
    document.getElementById('gate-value').textContent = '—';
    document.getElementById('gate-value').classList.remove('set');
    document.getElementById('diff-value').textContent = '—';
    document.getElementById('speed-result').classList.add('hidden');
    document.getElementById('btn-calc').disabled = true;

    document.getElementById('step-scrubber').classList.remove('hidden');
    document.getElementById('delivery-status').innerHTML = '';

    seekFrame(state.releaseFrameInClip || 0);
}

// ── Frame Navigation ──

function seekFrame(n) {
    n = Math.max(0, Math.min(n, state.totalFrames - 1));
    state.currentFrame = n;
    document.getElementById('frame-slider').value = n;
    document.getElementById('frame-counter').textContent = `${n} / ${state.totalFrames - 1}`;
    document.getElementById('frame-img').src = `/frame/${state.clipId}/${n}`;
}

function stepFrames(delta) {
    seekFrame(state.currentFrame + delta);
}

function togglePlay() {
    if (state.playing) {
        clearInterval(state.playTimer);
        state.playing = false;
    } else {
        state.playing = true;
        state.playTimer = setInterval(() => {
            if (state.currentFrame >= state.totalFrames - 1) {
                clearInterval(state.playTimer);
                state.playing = false;
                return;
            }
            seekFrame(state.currentFrame + 1);
        }, 1000 / 30); // playback at 30fps for review
    }
}

// ── Marking ──

function markRelease() {
    state.releaseFrame = state.currentFrame;
    document.getElementById('release-value').textContent = `Frame ${state.releaseFrame}`;
    document.getElementById('release-value').classList.add('set');
    document.getElementById('btn-release').classList.add('active');
    updateDiff();
}

function markGate() {
    state.gateFrame = state.currentFrame;
    document.getElementById('gate-value').textContent = `Frame ${state.gateFrame}`;
    document.getElementById('gate-value').classList.add('set');
    document.getElementById('btn-gate').classList.add('active');
    updateDiff();
}

function updateDiff() {
    if (state.releaseFrame !== null && state.gateFrame !== null) {
        const diff = state.gateFrame - state.releaseFrame;
        document.getElementById('diff-value').textContent = `${diff} frames (${(diff / state.fps).toFixed(4)}s)`;
        document.getElementById('btn-calc').disabled = false;
    }
}

function toggleCustomDistance() {
    const sel = document.getElementById('gate-type').value;
    document.getElementById('custom-distance').classList.toggle('hidden', sel !== 'custom');
}

// ── Speed Calculation ──

async function calcSpeed() {
    if (state.releaseFrame === null || state.gateFrame === null) return;

    const gate = document.getElementById('gate-type').value;
    const customDist = parseFloat(document.getElementById('custom-distance').value) || null;

    const params = new URLSearchParams({
        release_frame: state.releaseFrame,
        gate_frame: state.gateFrame,
        fps: state.fps,
        gate: gate,
    });
    if (customDist) params.append('custom_distance', customDist);

    const res = await fetch(`/calculate-speed?${params}`, { method: 'POST' });
    const data = await res.json();

    if (data.error) {
        alert(data.error);
        return;
    }

    document.getElementById('speed-value').textContent = data.speed_kph;
    document.getElementById('speed-value-mph').textContent = data.speed_mph;
    document.getElementById('speed-detail').textContent =
        `${data.distance_m}m in ${data.time_s}s | ${data.frame_diff} frames @ ${state.fps}fps | ±${data.error_kph} kph / ±${data.error_mph} mph`;
    document.getElementById('speed-result').classList.remove('hidden');
}

// ── Keyboard Controls ──

document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

    switch (e.key) {
        case 'ArrowLeft':
            e.preventDefault();
            stepFrames(e.shiftKey ? -10 : -1);
            break;
        case 'ArrowRight':
            e.preventDefault();
            stepFrames(e.shiftKey ? 10 : 1);
            break;
        case 'r':
        case 'R':
            markRelease();
            break;
        case 'g':
        case 'G':
            markGate();
            break;
        case ' ':
            e.preventDefault();
            togglePlay();
            break;
    }
});
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"Gemini: {'enabled' if GEMINI_AVAILABLE else 'disabled (set GOOGLE_API_KEY)'}")
    print(f"Temp dir: {UPLOAD_DIR}")
    print(f"Open http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
