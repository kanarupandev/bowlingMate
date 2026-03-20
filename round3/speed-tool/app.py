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
ANNOTATIONS_DIR = APP_DIR / "annotations"
CLIPS_DIR.mkdir(exist_ok=True)
FRAMES_DIR.mkdir(exist_ok=True)
SAMPLES_DIR.mkdir(exist_ok=True)
ANNOTATIONS_DIR.mkdir(exist_ok=True)

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
    """List all videos in samples dir (includes uploads). Shows annotation status."""
    videos = []
    for f in sorted(SAMPLES_DIR.iterdir()):
        if f.suffix.lower() in (".mov", ".mp4", ".m4v"):
            thumb = f.with_suffix(".jpg")
            info = get_video_info(str(f))
            ann_path = _annotation_path(f.name)
            ann = None
            if ann_path.exists():
                try:
                    ann = json.loads(ann_path.read_text())
                except Exception:
                    pass
            videos.append({
                "filename": f.name,
                "thumbnail": f"/sample-thumb/{f.stem}.jpg" if thumb.exists() else None,
                "duration": round(info["duration"], 1),
                "fps": info["fps"],
                "resolution": f"{info['width']}x{info['height']}",
                "annotated": ann is not None,
                "speed_kph": ann.get("speed_kph") if ann else None,
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
    release_adj: float = 1.08,
):
    """Calculate speed from marked frames. Includes estimated release speed."""
    result = calculate_speed(release_frame, gate_frame, fps, gate, custom_distance)
    if "error" not in result:
        result["release_est_kph"] = round(result["speed_kph"] * release_adj, 1)
        result["release_est_mph"] = round(result["speed_mph"] * release_adj, 1)
        result["release_adj"] = release_adj
    return result


# ──────────────────────────────────────────────────────────
# Annotations
# ──────────────────────────────────────────────────────────

def _annotation_path(filename: str) -> Path:
    """Get annotation JSON path for a video filename."""
    stem = Path(filename).stem
    return ANNOTATIONS_DIR / f"{stem}.json"


@app.get("/annotations")
async def list_annotations():
    """List all annotations."""
    result = {}
    for f in ANNOTATIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            result[data.get("filename", f.stem)] = data
        except Exception:
            pass
    return result


@app.get("/annotation/{filename}")
async def get_annotation(filename: str):
    """Get annotation for a specific video."""
    path = _annotation_path(filename)
    if not path.exists():
        return {"annotated": False}
    return json.loads(path.read_text())


@app.post("/annotation/{filename}")
async def save_annotation(filename: str, data: dict):
    """Save annotation for a video."""
    data["filename"] = filename
    path = _annotation_path(filename)
    path.write_text(json.dumps(data, indent=2))
    return {"saved": True, "path": str(path)}


@app.delete("/annotation/{filename}")
async def delete_annotation(filename: str):
    """Delete annotation for a video."""
    path = _annotation_path(filename)
    if path.exists():
        path.unlink()
    return {"deleted": True}


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
    max-width: 960px; margin: 0 auto; padding: 20px;
}
h1 { color: #006D77; margin-bottom: 4px; font-size: 24px; }
.subtitle { color: #8DA9C4; font-size: 14px; margin-bottom: 20px; }
h2 { color: #8DA9C4; margin: 16px 0 8px; font-size: 16px; }

.upload-zone {
    border: 2px dashed #30363d; border-radius: 12px;
    padding: 40px; text-align: center; cursor: pointer;
    transition: border-color 0.2s;
}
.upload-zone:hover { border-color: #006D77; }
.upload-zone.active { border-color: #006D77; background: #006D7710; }
input[type="file"] { display: none; }

.info { background: #161b22; border-radius: 8px; padding: 12px 16px; margin: 8px 0; font-size: 13px; }
.info span { color: #8DA9C4; }

.btn {
    background: #006D77; color: white; border: none; border-radius: 6px;
    padding: 8px 16px; cursor: pointer; font-family: inherit; font-size: 14px;
}
.btn:hover { background: #008891; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Main frame display with overlay */
.frame-container {
    position: relative; background: #000; border-radius: 8px;
    overflow: hidden; min-height: 300px;
    display: flex; justify-content: center; align-items: center;
}
.frame-container img { max-width: 100%; max-height: 500px; display: block; }
.frame-counter {
    position: absolute; top: 8px; left: 8px;
    background: #000000cc; color: #fff; padding: 4px 10px;
    border-radius: 4px; font-size: 12px;
}
.release-badge {
    position: absolute; top: 8px; right: 8px;
    background: #006D77cc; color: #fff; padding: 4px 10px;
    border-radius: 4px; font-size: 12px;
}
/* Speed overlay on frame */
.speed-overlay {
    position: absolute; bottom: 12px; right: 12px;
    background: #000000dd; border: 1px solid #006D77;
    border-radius: 8px; padding: 12px 16px; text-align: right;
    min-width: 160px; display: none;
}
.speed-overlay .delivery-speed { font-size: 36px; font-weight: bold; color: #006D77; line-height: 1; }
.speed-overlay .delivery-unit { font-size: 14px; color: #8DA9C4; }
.speed-overlay .release-speed { font-size: 20px; color: #e6edf3; margin-top: 4px; }
.speed-overlay .release-label { font-size: 11px; color: #8DA9C4; }
.speed-overlay .mph-line { font-size: 14px; color: #8DA9C4; margin-top: 2px; }
.speed-overlay .detail-line { font-size: 10px; color: #8DA9C480; margin-top: 4px; }
/* Detail strip at bottom of frame */
.detail-strip {
    position: absolute; bottom: 0; left: 0; right: 0;
    background: #000000aa; padding: 4px 12px;
    font-size: 11px; color: #8DA9C4; display: none;
}

.controls { display: flex; align-items: center; gap: 6px; margin: 8px 0; }
.controls button {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 6px 12px; cursor: pointer;
    font-family: inherit; font-size: 15px; min-width: 40px;
}
.controls button:hover { background: #30363d; }
input[type="range"] { flex: 1; accent-color: #006D77; height: 6px; }

.mark-release-btn {
    width: 100%; padding: 14px; font-size: 16px; border-radius: 8px;
    border: 2px solid #006D77; background: #006D7720; color: #006D77;
    cursor: pointer; font-family: inherit; font-weight: 600;
    transition: all 0.15s; margin: 8px 0;
}
.mark-release-btn:hover { background: #006D7740; }
.mark-release-btn.active { background: #006D77; color: white; }

/* Thumbnail strip */
.thumb-section { margin: 16px 0; }
.thumb-label { color: #8DA9C4; font-size: 13px; margin-bottom: 8px; }
.thumb-nav { display: flex; align-items: center; gap: 6px; }
.thumb-nav button {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 10px; cursor: pointer;
    font-family: inherit; font-size: 14px; min-width: 36px;
}
.thumb-nav button:hover { background: #30363d; }
.thumb-strip {
    display: flex; gap: 4px; flex: 1; overflow: hidden;
}
.thumb-strip .thumb {
    flex: 1; min-width: 0; cursor: pointer; border-radius: 4px;
    border: 2px solid transparent; overflow: hidden; position: relative;
    transition: border-color 0.15s;
}
.thumb-strip .thumb:hover { border-color: #da3634; }
.thumb-strip .thumb.selected { border-color: #da3634; }
.thumb-strip .thumb img {
    width: 100%; height: 80px; object-fit: cover; display: block;
}
.thumb-strip .thumb .thumb-label {
    position: absolute; bottom: 0; left: 0; right: 0;
    background: #000000cc; color: #fff; font-size: 10px;
    padding: 2px 4px; text-align: center;
}

.settings-row {
    display: flex; align-items: center; gap: 12px; margin: 10px 0;
    background: #161b22; border-radius: 8px; padding: 10px 16px;
    flex-wrap: wrap; font-size: 13px;
}
.settings-row label { color: #8DA9C4; white-space: nowrap; }
.settings-row input {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 4px; padding: 4px 8px; font-family: inherit;
    font-size: 14px; width: 70px; text-align: center;
}
.settings-row .unit { color: #8DA9C480; font-size: 12px; }

.hidden { display: none; }
.loading { color: #8DA9C4; font-style: italic; }

.keyboard-help {
    background: #161b22; border-radius: 8px; padding: 8px 16px;
    font-size: 11px; color: #8DA9C4; margin: 8px 0;
}
.keyboard-help kbd {
    background: #21262d; border: 1px solid #30363d; border-radius: 3px;
    padding: 1px 5px; font-family: inherit;
}

.sample-grid {
    display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 10px; margin: 12px 0;
}
.sample-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 8px;
    overflow: hidden; cursor: pointer; transition: border-color 0.2s;
    position: relative;
}
.sample-card:hover { border-color: #006D77; }
.sample-card.annotated { border-color: #238636; }
.sample-card img { width: 100%; height: 100px; object-fit: cover; }
.sample-card .meta { padding: 6px 8px; font-size: 11px; color: #8DA9C4; }
.sample-card .name { color: #e6edf3; font-size: 12px; margin-bottom: 2px; }
.sample-card .ann-badge {
    position: absolute; top: 4px; right: 4px;
    background: #238636; color: white; font-size: 10px; font-weight: bold;
    padding: 2px 6px; border-radius: 3px;
}
.sample-card .ann-badge.none {
    background: #30363d; color: #8DA9C4;
}

.annotation-count {
    color: #8DA9C4; font-size: 13px; margin: 8px 0;
}
.annotation-count strong { color: #238636; }

.save-status {
    color: #238636; font-size: 12px; margin-top: 4px;
    opacity: 0; transition: opacity 0.3s;
}
.save-status.show { opacity: 1; }

.bottom-bar { margin-top: 16px; display: flex; gap: 8px; }
</style>
</head>
<body>

<h1>Speed Tool</h1>
<p class="subtitle">Hit the stumps, get your speed.</p>

<!-- Step 1: Upload / Library -->
<div id="step-upload">
    <div class="upload-zone" onclick="document.getElementById('file-input').click()" id="drop-zone">
        <p style="font-size: 18px; margin-bottom: 8px;">Drop video here or click to upload</p>
        <p style="color: #8DA9C4; font-size: 13px;">iPhone slo-mo 240fps recommended</p>
    </div>
    <input type="file" id="file-input" accept="video/*" onchange="uploadVideo(this.files[0])">
    <div id="upload-status"></div>
    <h2>Or pick from library</h2>
    <div class="annotation-count" id="ann-count"></div>
    <div class="sample-grid" id="sample-grid"></div>
</div>

<!-- Step 2: Measure -->
<div id="step-measure" class="hidden">
    <div class="info" id="video-info"></div>

    <div class="keyboard-help">
        <kbd>&larr;</kbd>/<kbd>&rarr;</kbd> &plusmn;1 &nbsp;
        <kbd>Shift</kbd> &plusmn;10 &nbsp;
        <kbd>R</kbd> release &nbsp;
        <kbd>Space</kbd> play &nbsp;
        <kbd>C</kbd> clear
    </div>

    <!-- Main frame with overlay -->
    <div class="frame-container" id="frame-container">
        <img id="main-frame" src="" alt="frame">
        <div class="frame-counter" id="frame-counter">0 / 0</div>
        <div class="release-badge hidden" id="release-badge">Release: —</div>
        <div class="speed-overlay" id="speed-overlay">
            <div class="delivery-speed" id="ov-delivery">—</div>
            <div class="delivery-unit">km/h delivery</div>
            <div class="release-speed" id="ov-release">—</div>
            <div class="release-label">est. release</div>
            <div class="mph-line" id="ov-mph">—</div>
            <div class="detail-line" id="ov-detail"></div>
        </div>
        <div class="detail-strip" id="detail-strip"></div>
    </div>

    <!-- Scrubber -->
    <div class="controls">
        <button onclick="browseStep(-10)">-10</button>
        <button onclick="browseStep(-1)">&larr;</button>
        <input type="range" id="browse-slider" min="0" max="0" value="0"
               oninput="browseSeek(parseInt(this.value))">
        <button onclick="browseStep(1)">&rarr;</button>
        <button onclick="browseStep(10)">+10</button>
    </div>

    <!-- Phase 1: Mark Release -->
    <button class="mark-release-btn" id="btn-release" onclick="markRelease()">
        Mark Release (R)
    </button>

    <!-- Phase 2: Thumbnail strip (appears after release) -->
    <div id="phase2" class="hidden">
        <div class="thumb-section">
            <div class="thumb-label">Pick the frame where stumps are hit:</div>
            <div class="thumb-nav">
                <button onclick="shiftStrip(-state.batchSize)" title="Shift batch">&laquo;</button>
                <button onclick="shiftStrip(-1)" title="Shift 1">&lsaquo;</button>
                <div class="thumb-strip" id="thumb-strip"></div>
                <button onclick="shiftStrip(1)" title="Shift 1">&rsaquo;</button>
                <button onclick="shiftStrip(state.batchSize)" title="Shift batch">&raquo;</button>
            </div>
        </div>
    </div>

    <!-- Settings -->
    <div class="settings-row">
        <label>Distance:</label>
        <input type="number" id="distance-input" value="18.90" step="0.1" min="1" max="30">
        <span class="unit">m</span>
        <label>Batch:</label>
        <input type="number" id="batch-input" value="5" step="1" min="2" max="8"
               onchange="updateBatchSize()">
        <label>Jump:</label>
        <input type="number" id="jump-input" value="0.6" step="0.1" min="0.1" max="2.0">
        <span class="unit">s</span>
        <label>Adj:</label>
        <input type="number" id="adj-input" value="1.08" step="0.01" min="1.0" max="1.3">
        <span class="unit">&times;</span>
    </div>

    <div class="save-status" id="save-status">Annotation saved</div>

    <div class="bottom-bar">
        <button class="btn" onclick="clearAll()">Clear (C)</button>
        <button class="btn" onclick="resetToUpload()" style="background:#21262d;border:1px solid #30363d;">
            &larr; Library
        </button>
    </div>
</div>

<script>
const RELEASE_ADJ_DEFAULT = 1.08;

let state = {
    sessionId: null,
    filename: null,
    fps: 240,
    totalFrames: 0,
    currentFrame: 0,
    releaseFrame: null,
    stumpsFrame: null,
    playing: false,
    playTimer: null,
    batchSize: 5,
    stripStart: 0,
};

// ── Samples ──

async function loadSamples() {
    try {
        const res = await fetch('/samples');
        const samples = await res.json();
        const grid = document.getElementById('sample-grid');
        grid.innerHTML = '';

        const total = samples.length;
        const annotated = samples.filter(s => s.annotated).length;
        document.getElementById('ann-count').innerHTML =
            `<strong>${annotated}</strong> / ${total} annotated`;

        if (total === 0) {
            grid.innerHTML = '<p style="color:#8DA9C4;font-size:13px;">No videos yet. Upload one.</p>';
            return;
        }
        samples.forEach(s => {
            const card = document.createElement('div');
            card.className = 'sample-card' + (s.annotated ? ' annotated' : '');
            card.onclick = () => loadSample(s.filename);
            const badge = s.annotated
                ? `<div class="ann-badge">${s.speed_kph} kph</div>`
                : `<div class="ann-badge none">--</div>`;
            card.innerHTML = `
                ${s.thumbnail ? `<img src="${s.thumbnail}" alt="${s.filename}">` : '<div style="height:100px;background:#21262d;"></div>'}
                ${badge}
                <div class="meta">
                    <div class="name">${s.filename}</div>
                    ${Math.round(s.fps)}fps | ${s.duration}s | ${s.resolution}
                </div>`;
            grid.appendChild(card);
        });
    } catch (err) { console.error(err); }
}

async function loadSample(filename) {
    document.getElementById('upload-status').innerHTML = '<p class="loading">Loading...</p>';
    try {
        const res = await fetch(`/load-sample?filename=${encodeURIComponent(filename)}`, { method: 'POST' });
        const data = await res.json();
        data._filename = filename;
        handleVideoLoaded(data);
        document.getElementById('upload-status').innerHTML = '';
    } catch (err) {
        document.getElementById('upload-status').innerHTML = `<p style="color:#f85149;">${err.message}</p>`;
    }
}
loadSamples();

// ── Upload ──

async function uploadVideo(file) {
    if (!file) return;
    document.getElementById('upload-status').innerHTML = '<p class="loading">Uploading...</p>';
    document.getElementById('drop-zone').classList.add('active');
    const fd = new FormData(); fd.append('file', file);
    try {
        const res = await fetch('/upload', { method: 'POST', body: fd });
        handleVideoLoaded(await res.json());
        document.getElementById('upload-status').innerHTML = '';
        loadSamples();
    } catch (err) {
        document.getElementById('upload-status').innerHTML = `<p style="color:#f85149;">${err.message}</p>`;
    }
}

async function handleVideoLoaded(data) {
    state.sessionId = data.session_id;
    state.filename = data._filename || data.session_id;
    state.fps = data.info.fps;
    state.totalFrames = data.info.frame_count;
    state.currentFrame = 0;
    state.batchSize = parseInt(document.getElementById('batch-input').value) || 5;

    document.getElementById('video-info').innerHTML = `
        <span>FPS:</span> ${Math.round(state.fps)} &nbsp;|&nbsp;
        <span>Frames:</span> ${state.totalFrames} &nbsp;|&nbsp;
        <span>Resolution:</span> ${data.info.width}&times;${data.info.height} &nbsp;|&nbsp;
        <span>Duration:</span> ${data.info.duration.toFixed(1)}s &nbsp;|&nbsp;
        <span>${state.filename}</span>
    `;

    document.getElementById('browse-slider').max = state.totalFrames - 1;
    document.getElementById('browse-slider').value = 0;
    clearAll();

    document.getElementById('step-upload').classList.add('hidden');
    document.getElementById('step-measure').classList.remove('hidden');

    // Load existing annotation if any
    try {
        const annRes = await fetch(`/annotation/${encodeURIComponent(state.filename)}`);
        const ann = await annRes.json();
        if (ann.annotated !== false && ann.release_frame != null) {
            // Restore annotation
            state.releaseFrame = ann.release_frame;
            state.stumpsFrame = ann.stumps_frame;
            const t = (state.releaseFrame / state.fps).toFixed(2);
            document.getElementById('release-badge').textContent = `Release: F${state.releaseFrame} (${t}s)`;
            document.getElementById('release-badge').classList.remove('hidden');
            document.getElementById('btn-release').classList.add('active');
            document.getElementById('btn-release').textContent = `Release: Frame ${state.releaseFrame} (${t}s) — press R to re-mark`;

            if (ann.distance_m) document.getElementById('distance-input').value = ann.distance_m;

            // Show phase 2 and jump to stumps frame
            const jumpSec = parseFloat(document.getElementById('jump-input').value) || 0.6;
            state.stripStart = Math.max(0, state.stumpsFrame - 2);
            document.getElementById('phase2').classList.remove('hidden');
            renderStrip();
            browseSeek(state.stumpsFrame);
            calcSpeed();
            return;
        }
    } catch (e) { /* no annotation, fine */ }

    browseSeek(0);
}

// Drag and drop
const dropZone = document.getElementById('drop-zone');
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('active'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('active'));
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
    document.getElementById('frame-counter').textContent = `F${n} / ${state.totalFrames - 1}  (${t}s)`;
    document.getElementById('main-frame').src = `/video-frame/${state.sessionId}/${n}`;
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

// ── Phase 1: Mark Release ──

function markRelease() {
    state.releaseFrame = state.currentFrame;
    const t = (state.releaseFrame / state.fps).toFixed(2);

    // Update badge
    const badge = document.getElementById('release-badge');
    badge.textContent = `Release: F${state.releaseFrame} (${t}s)`;
    badge.classList.remove('hidden');

    // Update button
    document.getElementById('btn-release').classList.add('active');
    document.getElementById('btn-release').textContent = `Release: Frame ${state.releaseFrame} (${t}s) — press R to re-mark`;

    // Jump ahead and show Phase 2
    const jumpSec = parseFloat(document.getElementById('jump-input').value) || 0.6;
    const jumpFrames = Math.round(jumpSec * state.fps);
    const targetFrame = Math.min(state.releaseFrame + jumpFrames, state.totalFrames - 1);

    state.stripStart = targetFrame;
    state.stumpsFrame = null;
    hideSpeedOverlay();

    document.getElementById('phase2').classList.remove('hidden');
    renderStrip();

    // Also jump the main view
    browseSeek(targetFrame);
}

// ── Phase 2: Thumbnail Strip ──

function renderStrip() {
    const strip = document.getElementById('thumb-strip');
    strip.innerHTML = '';

    for (let i = 0; i < state.batchSize; i++) {
        const frameNum = state.stripStart + i;
        if (frameNum >= state.totalFrames) break;

        const div = document.createElement('div');
        div.className = 'thumb';
        if (state.stumpsFrame === frameNum) div.classList.add('selected');
        div.onclick = () => selectStumpsFrame(frameNum);

        const img = document.createElement('img');
        img.src = `/video-frame/${state.sessionId}/${frameNum}`;
        img.alt = `F${frameNum}`;

        const lbl = document.createElement('div');
        lbl.className = 'thumb-label';
        lbl.textContent = `F${frameNum}`;

        div.appendChild(img);
        div.appendChild(lbl);
        strip.appendChild(div);
    }
}

function shiftStrip(delta) {
    state.stripStart = Math.max(0, Math.min(state.stripStart + delta, state.totalFrames - 1));
    renderStrip();
}

function selectStumpsFrame(frameNum) {
    state.stumpsFrame = frameNum;

    // Highlight in strip
    renderStrip();

    // Jump main view to this frame
    browseSeek(frameNum);

    // Calculate speed instantly
    calcSpeed();
}

function updateBatchSize() {
    state.batchSize = parseInt(document.getElementById('batch-input').value) || 5;
    if (state.releaseFrame !== null) renderStrip();
}

// ── Speed Calculation + Overlay ──

async function calcSpeed() {
    if (state.releaseFrame === null || state.stumpsFrame === null) return;

    const distance = parseFloat(document.getElementById('distance-input').value);
    if (!distance || distance <= 0) return;

    const adj = parseFloat(document.getElementById('adj-input').value) || RELEASE_ADJ_DEFAULT;

    const params = new URLSearchParams({
        release_frame: state.releaseFrame,
        gate_frame: state.stumpsFrame,
        fps: state.fps,
        gate: 'custom',
        custom_distance: distance,
        release_adj: adj,
    });

    const res = await fetch(`/calculate-speed?${params}`, { method: 'POST' });
    const data = await res.json();
    if (data.error) return;

    const releaseKph = (data.speed_kph * adj).toFixed(1);
    const releaseMph = (data.speed_mph * adj).toFixed(1);

    // Speed overlay on frame
    const ov = document.getElementById('speed-overlay');
    document.getElementById('ov-delivery').textContent = data.speed_kph;
    document.getElementById('ov-release').textContent = `~${releaseKph} km/h`;
    document.getElementById('ov-mph').textContent = `${data.speed_mph} / ~${releaseMph} mph`;
    document.getElementById('ov-detail').textContent =
        `${data.distance_m}m | ${data.time_s}s | ${data.frame_diff}f @${Math.round(state.fps)}fps | \\u00B1${data.error_kph}`;
    ov.style.display = 'block';

    // Detail strip
    const ds = document.getElementById('detail-strip');
    ds.textContent = `Release F${state.releaseFrame} \\u2192 Stumps F${state.stumpsFrame} | ${data.frame_diff} frames | ${data.time_s}s | ${data.distance_m}m | \\u00B1${data.error_kph} kph`;
    ds.style.display = 'block';

    // Auto-save annotation
    saveAnnotation(data, adj);
}

async function saveAnnotation(speedData, adj) {
    if (!state.filename) return;

    const annotation = {
        filename: state.filename,
        release_frame: state.releaseFrame,
        stumps_frame: state.stumpsFrame,
        fps: state.fps,
        distance_m: speedData.distance_m,
        frame_diff: speedData.frame_diff,
        time_s: speedData.time_s,
        speed_kph: speedData.speed_kph,
        speed_mph: speedData.speed_mph,
        release_est_kph: speedData.release_est_kph,
        release_est_mph: speedData.release_est_mph,
        release_adj: adj,
        error_kph: speedData.error_kph,
        annotated_at: new Date().toISOString(),
    };

    try {
        await fetch(`/annotation/${encodeURIComponent(state.filename)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(annotation),
        });
        const ss = document.getElementById('save-status');
        ss.textContent = `Annotation saved (${speedData.speed_kph} kph)`;
        ss.classList.add('show');
        setTimeout(() => ss.classList.remove('show'), 2000);
    } catch (e) { console.error('Save failed:', e); }
}

function hideSpeedOverlay() {
    document.getElementById('speed-overlay').style.display = 'none';
    document.getElementById('detail-strip').style.display = 'none';
}

// ── Clear / Reset ──

function clearAll() {
    state.releaseFrame = null;
    state.stumpsFrame = null;

    document.getElementById('btn-release').classList.remove('active');
    document.getElementById('btn-release').textContent = 'Mark Release (R)';
    document.getElementById('release-badge').classList.add('hidden');
    document.getElementById('phase2').classList.add('hidden');
    hideSpeedOverlay();
}

function resetToUpload() {
    if (state.playing) { clearInterval(state.playTimer); state.playing = false; }
    state.sessionId = null;
    clearAll();
    document.getElementById('step-measure').classList.add('hidden');
    document.getElementById('step-upload').classList.remove('hidden');
    loadSamples();
}

// ── Keyboard ──

document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
    if (document.getElementById('step-measure').classList.contains('hidden')) return;

    switch (e.key) {
        case 'ArrowLeft':  e.preventDefault(); browseStep(e.shiftKey ? -10 : -1); break;
        case 'ArrowRight': e.preventDefault(); browseStep(e.shiftKey ? 10 : 1); break;
        case 'r': case 'R': markRelease(); break;
        case 'c': case 'C': clearAll(); break;
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
