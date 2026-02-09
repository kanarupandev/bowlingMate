# BowlingMate Backend - Triggered CI/CD
import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from database import init_db
from rag import init_rag_index
from agent import run_streamed_agent

from contextlib import asynccontextmanager
from config import get_settings

settings = get_settings()

# Configure Logging - Use DEBUG from settings
import logging
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.DEBUG)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logging.getLogger("python_multipart").setLevel(logging.WARNING)

logger = logging.getLogger("BowlingMate")
logger.setLevel(log_level)
logger.info(f"Logging initialized at level: {settings.LOG_LEVEL}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Startup complete.")
    logger.info(f"🔑 DEBUG KEY: {settings.GOOGLE_API_KEY}") 
    logger.info(f"🤖 DEBUG MODEL: {settings.GEMINI_MODEL_NAME}")
    
    init_db()
    init_rag_index()
    yield
    # Shutdown
    logger.info("Shutdown complete.")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

# --- SECURITY MIDDLEWARE ---
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

@app.middleware("http")
async def verify_authentication(request: Request, call_next):
    # Allow health check and docs without auth (for Cloud Run probes)
    if request.url.path in ["/", "/docs", "/openapi.json", "/health"]:
        return await call_next(request)

    # Try Bearer token first, then fall back to legacy header
    auth_header = request.headers.get("Authorization")
    legacy_secret = request.headers.get("X-WellBowled-Secret")

    authenticated = False

    # Method 1: Bearer Token (preferred)
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Strip "Bearer " prefix
        if token == settings.API_SECRET:
            authenticated = True
            logger.debug(f"✅ Bearer auth successful from {request.client.host}")

    # Method 2: Legacy X-WellBowled-Secret header (backwards compatibility)
    if not authenticated and legacy_secret == settings.API_SECRET:
        authenticated = True
        logger.debug(f"✅ Legacy header auth successful from {request.client.host}")

    if not authenticated:
        logger.warning(f"⛔ Unauthorized Access Attempt from {request.client.host} to {request.url.path}")
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Invalid or missing authentication"},
            headers={"WWW-Authenticate": "Bearer"}
        )

    return await call_next(request)
# ---------------------------


class AnalysisResponse(BaseModel):
    report: str
    speed_est: str
    bowl_id: int
    tips: list[str] = []
    release_timestamp: float = 0.0

@app.get("/")
def health_check():
    return {"status": "ok", "service": "BowlingMate-backend", "model": settings.GEMINI_MODEL_NAME}

@app.get("/debug-overlay")
def debug_overlay():
    """Check MediaPipe and overlay configuration status."""
    result = {
        "enable_overlay": settings.ENABLE_OVERLAY,
        "mock_scout": settings.MOCK_SCOUT,
        "mock_coach": settings.MOCK_COACH,
    }
    try:
        from mediapipe_overlay import is_overlay_available
        result["mediapipe_available"] = is_overlay_available()
    except ImportError as e:
        result["mediapipe_available"] = False
        result["mediapipe_error"] = str(e)

    try:
        import cv2
        result["opencv_version"] = cv2.__version__
    except ImportError as e:
        result["opencv_error"] = str(e)

    try:
        import subprocess
        ffmpeg_result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        result["ffmpeg_available"] = ffmpeg_result.returncode == 0
    except Exception as e:
        result["ffmpeg_error"] = str(e)

    return result


@app.get("/test-overlay-stream")
async def test_overlay_stream(video_url: str = None):
    """Debug endpoint: Stream step-by-step overlay generation progress."""
    import tempfile
    import subprocess
    import time as time_module

    async def step_generator():
        steps = []

        def log_step(name: str, status: str, detail: str = ""):
            step = {"step": name, "status": status, "detail": detail}
            steps.append(step)
            return f"data: {json.dumps(step)}\n\n"

        # Use a small test video from GCS or create synthetic
        yield log_step("init", "start", "Starting overlay test")

        # Step 1: Import MediaPipe
        try:
            from mediapipe_overlay import process as create_overlay, is_overlay_available
            yield log_step("import_mediapipe", "ok", "mediapipe_overlay imported")
        except Exception as e:
            yield log_step("import_mediapipe", "FAIL", str(e))
            return

        # Step 2: Check availability
        try:
            available = is_overlay_available()
            if available:
                yield log_step("check_available", "ok", f"is_overlay_available={available}")
            else:
                yield log_step("check_available", "FAIL", "MediaPipe not available")
                return
        except Exception as e:
            yield log_step("check_available", "FAIL", str(e))
            return

        # Step 3: Import cv2
        try:
            import cv2
            yield log_step("import_cv2", "ok", f"OpenCV {cv2.__version__}")
        except Exception as e:
            yield log_step("import_cv2", "FAIL", str(e))
            return

        # Step 4: Create synthetic test video (3 seconds, 640x480)
        try:
            import numpy as np
            test_video_path = "/tmp/test_input.mp4"
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(test_video_path, fourcc, 30, (640, 480))
            for i in range(90):  # 3 seconds at 30fps
                frame = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(frame, f"Frame {i}", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
                out.write(frame)
            out.release()
            size = os.path.getsize(test_video_path)
            yield log_step("create_test_video", "ok", f"Created {test_video_path} ({size} bytes)")
        except Exception as e:
            yield log_step("create_test_video", "FAIL", str(e))
            return

        # Step 5: Verify video readable
        try:
            cap = cv2.VideoCapture(test_video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            yield log_step("verify_video", "ok", f"fps={fps}, w={w}, h={h}, frames={frame_count}")
        except Exception as e:
            yield log_step("verify_video", "FAIL", str(e))
            return

        # Step 6: Create feedback JSON
        try:
            feedback = {
                "phases": [
                    {"start": 0, "end": 1.5, "name": "Phase1", "feedback": {"good": ["RIGHT_SHOULDER"], "slow": [], "injury_risk": []}},
                    {"start": 1.5, "end": 3.0, "name": "Phase2", "feedback": {"good": [], "slow": ["RIGHT_WRIST"], "injury_risk": []}}
                ]
            }
            feedback_path = "/tmp/test_feedback.json"
            with open(feedback_path, "w") as f:
                json.dump(feedback, f)
            yield log_step("create_feedback", "ok", f"Created {feedback_path}")
        except Exception as e:
            yield log_step("create_feedback", "FAIL", str(e))
            return

        # Step 7: Run MediaPipe overlay
        try:
            output_path = "/tmp/test_overlay.mp4"
            start = time_module.time()
            create_overlay(test_video_path, feedback_path, output_path)
            duration = time_module.time() - start
            if os.path.exists(output_path):
                size = os.path.getsize(output_path)
                yield log_step("mediapipe_process", "ok", f"Created {output_path} ({size} bytes) in {duration:.1f}s")
            else:
                yield log_step("mediapipe_process", "FAIL", f"Output file not created after {duration:.1f}s")
                return
        except Exception as e:
            import traceback
            yield log_step("mediapipe_process", "FAIL", f"{e}\n{traceback.format_exc()}")
            return

        # Step 8: FFmpeg compression
        try:
            compressed_path = "/tmp/test_compressed.mp4"
            start = time_module.time()
            result = subprocess.run([
                "ffmpeg", "-y", "-i", output_path,
                "-vcodec", "libx264", "-crf", "28", "-vf", "scale=480:-2",
                "-preset", "fast", compressed_path
            ], capture_output=True, timeout=60)
            duration = time_module.time() - start
            if result.returncode == 0 and os.path.exists(compressed_path):
                size = os.path.getsize(compressed_path)
                yield log_step("ffmpeg_compress", "ok", f"Created {compressed_path} ({size} bytes) in {duration:.1f}s")
            else:
                yield log_step("ffmpeg_compress", "FAIL", f"returncode={result.returncode}, stderr={result.stderr.decode()[:500]}")
                return
        except Exception as e:
            yield log_step("ffmpeg_compress", "FAIL", str(e))
            return

        # Step 9: GCS upload test
        try:
            storage = get_storage_service()
            test_id = f"test_{int(time_module.time())}"
            base_url = "https://bowlingmate-230175862422.us-central1.run.app"
            video_url, _ = storage.upload_clip(compressed_path, f"overlay_{test_id}", base_url=base_url)
            yield log_step("gcs_upload", "ok", f"Uploaded to {video_url}")
        except Exception as e:
            yield log_step("gcs_upload", "FAIL", str(e))
            return

        yield log_step("complete", "SUCCESS", f"All steps passed! URL: {video_url}")

        # Cleanup
        for p in [test_video_path, feedback_path, output_path, compressed_path]:
            if os.path.exists(p):
                os.remove(p)

    return StreamingResponse(step_generator(), media_type="text/event-stream")


@app.post("/test-overlay")
async def test_overlay(file: UploadFile = File(...)):
    """Debug endpoint: Test overlay generation with step-by-step diagnostics."""
    import traceback
    import tempfile
    import subprocess
    import time as time_module

    steps = []
    def step(name, status, detail=""):
        steps.append({"step": name, "status": status, "detail": detail})
        logger.info(f"[test-overlay] {name}: {status} - {detail}")

    video_bytes = await file.read()
    step("receive_file", "ok", f"{len(video_bytes)} bytes")

    # Step 1: Import MediaPipe
    try:
        from mediapipe_overlay import process as create_overlay, is_overlay_available
        step("import_mediapipe", "ok", "imported")
    except Exception as e:
        step("import_mediapipe", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Step 2: Check availability
    try:
        available = is_overlay_available()
        if available:
            step("check_available", "ok", str(available))
        else:
            step("check_available", "FAIL", "MediaPipe not available")
            return {"success": False, "steps": steps}
    except Exception as e:
        step("check_available", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Step 3: Import cv2 and mediapipe
    try:
        import cv2
        import mediapipe as mp
        step("import_cv2_mp", "ok", f"cv2={cv2.__version__}, mp={mp.__version__}")
    except Exception as e:
        step("import_cv2_mp", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Step 4: Save input video to temp
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            input_path = tmp.name
        step("save_input", "ok", input_path)
    except Exception as e:
        step("save_input", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Step 5: Verify video readable with OpenCV
    try:
        cap = cv2.VideoCapture(input_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        ret, frame = cap.read()
        cap.release()
        if ret and fps > 0:
            step("verify_video", "ok", f"fps={fps}, w={w}, h={h}, frames={frame_count}")
        else:
            step("verify_video", "FAIL", f"Cannot read video: fps={fps}, ret={ret}")
            return {"success": False, "steps": steps}
    except Exception as e:
        step("verify_video", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Step 6: Test MediaPipe Pose on one frame
    try:
        cap = cv2.VideoCapture(input_path)
        ret, frame = cap.read()
        cap.release()
        mp_pose = mp.solutions.pose
        with mp_pose.Pose(min_detection_confidence=0.5) as pose:
            results = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            has_landmarks = results.pose_landmarks is not None
        step("mediapipe_pose_test", "ok", f"landmarks_detected={has_landmarks}")
    except Exception as e:
        step("mediapipe_pose_test", "FAIL", f"{e}\n{traceback.format_exc()}")
        return {"success": False, "steps": steps}

    # Step 7: Create feedback JSON
    try:
        feedback = {"phases": [
            {"start": 0, "end": 2.5, "name": "Phase1", "feedback": {"good": ["RIGHT_SHOULDER"], "slow": [], "injury_risk": []}},
            {"start": 2.5, "end": 5.0, "name": "Phase2", "feedback": {"good": [], "slow": ["RIGHT_WRIST"], "injury_risk": []}}
        ]}
        feedback_path = input_path.replace(".mp4", "_fb.json")
        with open(feedback_path, "w") as f:
            json.dump(feedback, f)
        step("create_feedback", "ok", feedback_path)
    except Exception as e:
        step("create_feedback", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Step 8: Run full MediaPipe overlay
    try:
        output_path = input_path.replace(".mp4", "_overlay.mp4")
        start = time_module.time()
        create_overlay(input_path, feedback_path, output_path)
        duration = time_module.time() - start
        if os.path.exists(output_path):
            size = os.path.getsize(output_path)
            step("mediapipe_overlay", "ok", f"{output_path} ({size} bytes, {duration:.1f}s)")
        else:
            step("mediapipe_overlay", "FAIL", f"Output not created after {duration:.1f}s")
            return {"success": False, "steps": steps}
    except Exception as e:
        step("mediapipe_overlay", "FAIL", f"{e}\n{traceback.format_exc()}")
        return {"success": False, "steps": steps}

    # Step 9: FFmpeg compression
    try:
        compressed_path = output_path.replace(".mp4", "_web.mp4")
        start = time_module.time()
        result = subprocess.run([
            "ffmpeg", "-y", "-i", output_path,
            "-vcodec", "libx264", "-crf", "28", "-vf", "scale=480:-2",
            "-preset", "fast", compressed_path
        ], capture_output=True, timeout=120)
        duration = time_module.time() - start
        if result.returncode == 0 and os.path.exists(compressed_path):
            size = os.path.getsize(compressed_path)
            step("ffmpeg", "ok", f"{compressed_path} ({size} bytes, {duration:.1f}s)")
        else:
            step("ffmpeg", "FAIL", f"rc={result.returncode}, stderr={result.stderr.decode()[:300]}")
            return {"success": False, "steps": steps}
    except Exception as e:
        step("ffmpeg", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Step 10: GCS upload
    try:
        storage = get_storage_service()
        test_id = f"test_{int(time_module.time())}"
        base_url = "https://bowlingmate-230175862422.us-central1.run.app"
        video_url, _ = storage.upload_clip(compressed_path, f"overlay_{test_id}", base_url=base_url)
        step("gcs_upload", "ok", video_url)
    except Exception as e:
        step("gcs_upload", "FAIL", str(e))
        return {"success": False, "steps": steps}

    # Cleanup
    for p in [input_path, feedback_path, output_path, compressed_path]:
        if os.path.exists(p):
            os.remove(p)

    return {"success": True, "overlay_url": video_url, "steps": steps}

@app.get("/debug-gemini")
async def debug_gemini():
    """Smoke test for Gemini API Key and Connectivity via REST"""
    import requests
    import json
    
    key = settings.GOOGLE_API_KEY
    model_name = settings.GEMINI_MODEL_NAME
    
    # Masked key for logging
    key_masked = f"{key[:4]}...{key[-5:]}" if key else "None"
    
    logger.info(f"DEBUG SMOKE TEST: Key={key_masked}, Model={model_name}")
    print(f"!!! DEBUG ENDPOINT HIT: Key={key_masked} Model={model_name} !!!")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": "Hello, say 'Gemini REST OK'"}]}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        data = response.json()
        
        if response.status_code == 200:
            return {
                "status": "success", 
                "key_used": key_masked,
                "model_used": model_name,
                "gemini_response": data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "No text")
            }
        else:
            return {
                "status": "error",
                "key_used": key_masked,
                "model_used": model_name,
                "error_message": f"Code {response.status_code}: {json.dumps(data)}"
            }
    except Exception as e:
        logger.error(f"DEBUG TEST FAILED: {str(e)}")
        import traceback
        return {
            "status": "error",
            "key_used": key_masked,
            "model_used": model_name,
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }

from fastapi.responses import StreamingResponse
import json
import asyncio

# In-memory store for pending analysis (Bypass Disk)
analysis_cache = {}

@app.post("/analyze")
async def analyze_bowl(
    video: UploadFile = File(...),
    config: str = Form("club"),
    language: str = Form("en")
):
    logger.info(f"Received analysis request: {video.filename} (Bypassing Disk)")
    video_id = str(uuid.uuid4())
    video_bytes = await video.read()
    analysis_cache[video_id] = video_bytes
    
    # Auto-cleanup cache after 10 mins
    async def cleanup():
        await asyncio.sleep(600)
        analysis_cache.pop(video_id, None)
    asyncio.create_task(cleanup())

    return {"status": "accepted", "video_id": video_id}

@app.get("/stream-analysis")
async def stream_analysis(video_id: str = None, video_path: str = None, config: str = "club", language: str = "en", generate_overlay: bool = False):
    async def event_generator():
        video_bytes = None
        if video_id and video_id in analysis_cache:
            video_bytes = analysis_cache.get(video_id)  # Keep in cache for overlay
            logger.info(f"Streaming from memory: {video_id}")
        elif video_path and os.path.exists(video_path):
            with open(video_path, "rb") as f:
                video_bytes = f.read()
            logger.info(f"Streaming from disk (fallback): {video_path}")
        elif video_id:
            # Fallback: fetch from GCS (for clips uploaded via /upload-clip)
            logger.info(f"Fetching from GCS: clips/{video_id}.mp4")
            storage = get_storage_service()
            video_bytes = storage.download_blob(f"clips/{video_id}.mp4")
            if video_bytes:
                logger.info(f"Loaded {len(video_bytes)} bytes from GCS")

        if not video_bytes:
            yield f"data: {json.dumps({'status': 'error', 'message': 'Media not found or expired'})}\n\n"
            return

        from agent import run_streamed_agent
        phases_data = []

        async for event in run_streamed_agent(video_bytes, config, language):
            yield f"data: {json.dumps(event)}\n\n"
            # Capture phases for overlay
            if event.get("status") == "success" and "phases" in event:
                phases_data = event.get("phases", [])

        # Generate overlay after streaming completes
        if generate_overlay and phases_data and video_bytes:
            yield f"data: {json.dumps({'status': 'event', 'message': 'Annotating biomechanics...'})}\n\n"
            try:
                overlay_url = await generate_overlay_video(video_bytes, phases_data)
                if overlay_url:
                    yield f"data: {json.dumps({'status': 'overlay', 'overlay_url': overlay_url})}\n\n"
                    logger.info(f"[Stream] Overlay URL sent to client: {overlay_url}")
                else:
                    yield f"data: {json.dumps({'status': 'event', 'message': 'Overlay generation skipped or failed - check logs'})}\n\n"
                    logger.warning("[Stream] Overlay generation returned None")
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                logger.error(f"Overlay generation failed: {e}\n{error_detail}")
                yield f"data: {json.dumps({'status': 'event', 'message': f'Overlay generation failed: {str(e)}'})}\n\n"

        # Cleanup cache
        if video_id and video_id in analysis_cache:
            analysis_cache.pop(video_id, None)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _generate_overlay_sync(video_bytes: bytes, phases_data: list) -> str:
    """Sync function that does the actual overlay generation (blocking)."""
    import tempfile
    import subprocess
    import traceback

    # HARDCODED: Always enable overlay
    logger.info("[Overlay] Overlay generation enabled (hardcoded)")
    logger.info(f"[Overlay] Received {len(video_bytes)} bytes, {len(phases_data)} phases")

    logger.info(f"[Overlay] Starting generation with {len(phases_data)} phases")

    try:
        logger.info("[Overlay] Step 1: Importing mediapipe_overlay...")
        from mediapipe_overlay import process as create_overlay, is_overlay_available
        logger.info("[Overlay] Step 2: Checking is_overlay_available()...")
        available = is_overlay_available()
        logger.info(f"[Overlay] Step 3: is_overlay_available = {available}")
        if not available:
            logger.warning("[Overlay] MediaPipe not installed, skipping overlay")
            return None
        logger.info("[Overlay] Step 4: MediaPipe check passed")
    except ImportError as e:
        logger.error(f"[Overlay] MediaPipe import failed: {e}")
        return None  # Graceful fallback instead of exception

    # Convert phases to MediaPipe feedback
    joint_map = {
        "run-up": {"good": ["RIGHT_KNEE", "LEFT_KNEE", "RIGHT_HIP", "LEFT_HIP"]},
        "loading/coil": {"good": ["RIGHT_SHOULDER", "LEFT_SHOULDER", "RIGHT_HIP"]},
        "release action": {"injury_risk": ["RIGHT_ELBOW"], "good": ["RIGHT_WRIST"]},
        "release": {"injury_risk": ["RIGHT_ELBOW"], "good": ["RIGHT_WRIST"]},
        "wrist/snap": {"slow": ["RIGHT_WRIST"]},
        "follow-through": {"slow": ["RIGHT_HIP"], "good": ["RIGHT_SHOULDER"]},
        "head/eyes": {"slow": ["LEFT_SHOULDER"]}
    }

    feedback = {"phases": []}
    duration = 5.0
    phase_duration = duration / max(len(phases_data), 1)

    for i, p in enumerate(phases_data):
        name = p.get("name", "").lower()
        status = p.get("status", "").upper()

        fb = {"good": [], "slow": [], "injury_risk": []}
        if "GOOD" in status:
            fb["good"] = joint_map.get(name, {}).get("good", ["RIGHT_SHOULDER"])
        elif "NEEDS WORK" in status:
            fb["injury_risk"] = joint_map.get(name, {}).get("injury_risk", [])
            fb["slow"] = joint_map.get(name, {}).get("slow", ["RIGHT_SHOULDER"])

        feedback["phases"].append({
            "start": i * phase_duration,
            "end": (i + 1) * phase_duration,
            "name": p.get("name", f"phase_{i}"),
            "feedback": fb
        })

    # Save to temp files
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            input_path = tmp.name
        logger.info(f"[Overlay] Saved input video: {input_path} ({len(video_bytes)} bytes)")

        feedback_path = input_path.replace(".mp4", "_fb.json")
        with open(feedback_path, "w") as f:
            json.dump(feedback, f)
        logger.info(f"[Overlay] Saved feedback JSON: {feedback_path}")

        output_path = input_path.replace(".mp4", "_overlay.mp4")
        logger.info(f"[Overlay] Starting MediaPipe processing...")
        import time as time_module
        start_time = time_module.time()
        create_overlay(input_path, feedback_path, output_path)
        mp_duration = time_module.time() - start_time
        logger.info(f"[Overlay] MediaPipe completed in {mp_duration:.1f}s")

        if not os.path.exists(output_path):
            logger.error(f"[Overlay] MediaPipe failed - output file not created")
            return None

        # Compress
        compressed_path = output_path.replace(".mp4", "_web.mp4")
        logger.info(f"[Overlay] Starting FFmpeg compression...")
        start_time = time_module.time()
        result = subprocess.run([
            "ffmpeg", "-y", "-i", output_path,
            "-vcodec", "libx264", "-crf", "28", "-vf", "scale=480:-2",
            "-preset", "fast", compressed_path
        ], capture_output=True, timeout=120)
        ffmpeg_duration = time_module.time() - start_time
        logger.info(f"[Overlay] FFmpeg completed in {ffmpeg_duration:.1f}s")

        if result.returncode != 0:
            logger.error(f"[Overlay] FFmpeg failed: {result.stderr.decode()}")
            return None

        if not os.path.exists(compressed_path):
            logger.error(f"[Overlay] Compressed file not created")
            return None

        # Upload to GCS
        delivery_id = str(uuid.uuid4())
        storage = get_storage_service()
        base_url = "https://bowlingmate-230175862422.us-central1.run.app"
        logger.info(f"[Overlay] Uploading to GCS: overlay_{delivery_id}")
        video_url, _ = storage.upload_clip(compressed_path, f"overlay_{delivery_id}", base_url=base_url)
        logger.info(f"[Overlay] Upload complete: {video_url}")

        # Cleanup
        for p in [input_path, feedback_path, output_path, compressed_path]:
            if os.path.exists(p):
                os.remove(p)

        return video_url

    except subprocess.TimeoutExpired:
        logger.error("[Overlay] FFmpeg timeout (>120s)")
        return None
    except Exception as e:
        logger.error(f"[Overlay] Unexpected error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


async def generate_overlay_video(video_bytes: bytes, phases_data: list) -> str:
    """Async wrapper - runs blocking overlay generation in thread pool."""
    import asyncio
    return await asyncio.to_thread(_generate_overlay_sync, video_bytes, phases_data)


@app.post("/detect-action")
async def detect_action(file: UploadFile = File(...)):
    """
    Batch delivery detection: Scans video chunk for ALL bowling deliveries.
    Returns: {"found": bool, "deliveries_detected_at_time": [float], "total_count": int}
    """
    import google.generativeai as genai
    import time
    import tempfile

    request_id = f"REQ-{int(time.time()*1000)}"
    logger.info(f"[{request_id}] === DETECT-ACTION START === File: {file.filename}")

    # 1. Read video bytes
    try:
        video_bytes = await file.read()
        size_mb = len(video_bytes) / 1024 / 1024
        logger.info(f"[{request_id}] Video: {size_mb:.2f}MB")
    except Exception as e:
        logger.error(f"[{request_id}] Read Error: {e}")
        return {"found": False, "deliveries_detected_at_time": [], "total_count": 0, "error": str(e)}

    # Mock mode - return actual Gemini response for 3sec_vid.mp4 (2026-02-08)
    if settings.MOCK_SCOUT:
        import time as time_module
        time_module.sleep(1.0)  # Fast mock response (was 7.7s)
        logger.info(f"[{request_id}] MOCK_SCOUT enabled - returning cached response for 3sec_vid.mp4")
        # Actual Scout response for 3sec_vid.mp4 (3.76s video, 1 delivery at 1.3s)
        mock_response = {
            "found": True,
            "deliveries_detected_at_time": [1.3],
            "total_count": 1,
            "mock": True
        }
        logger.info(f"[{request_id}] === DETECT-ACTION END (MOCK) === {mock_response}")
        return mock_response

    uploaded_file = None  # Track for cleanup
    try:
        # 2. Configure Gemini
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(model_name=settings.SCOUT_MODEL)
        logger.info(f"[{request_id}] Using SCOUT_MODEL: {settings.SCOUT_MODEL}")

        # 3. Load prompt
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "detect_action_prompt.txt")
        try:
            with open(prompt_path, "r") as f:
                PROMPT = f.read()
            logger.info(f"[{request_id}] Prompt loaded: {len(PROMPT)} chars")
        except FileNotFoundError:
            logger.error(f"[{request_id}] PROMPT FILE NOT FOUND: {prompt_path}")
            return {"found": False, "deliveries_detected_at_time": [], "total_count": 0, "error": "Prompt file missing"}

        # 4. Call Gemini - use File API for videos >5MB (safer for longer videos)
        # Gemini inline has issues with longer videos regardless of size
        gemini_start = time.time()
        FILE_SIZE_THRESHOLD_MB = 5.0

        if size_mb > FILE_SIZE_THRESHOLD_MB:
            # Large file: use File API
            logger.info(f"[{request_id}] Using File API (size {size_mb:.2f}MB > {FILE_SIZE_THRESHOLD_MB}MB threshold)")
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(video_bytes)
                tmp_path = tmp.name

            try:
                uploaded_file = genai.upload_file(tmp_path, mime_type="video/mp4")
                logger.info(f"[{request_id}] File uploaded: {uploaded_file.name}")

                # Wait for processing with timeout (max 120 seconds)
                import time as time_module
                processing_start = time_module.time()
                max_processing_time = 120  # 2 minutes max for file processing
                while uploaded_file.state.name == "PROCESSING":
                    elapsed = time_module.time() - processing_start
                    if elapsed > max_processing_time:
                        raise Exception(f"File processing timeout after {max_processing_time}s")
                    logger.info(f"[{request_id}] Waiting for file processing... ({elapsed:.1f}s)")
                    time_module.sleep(2)
                    uploaded_file = genai.get_file(uploaded_file.name)

                if uploaded_file.state.name != "ACTIVE":
                    raise Exception(f"File processing failed: {uploaded_file.state.name}")

                logger.info(f"[{request_id}] File ACTIVE. Calling Gemini...")
                response = model.generate_content(
                    [uploaded_file, PROMPT],
                    generation_config={"response_mime_type": "application/json"},
                    request_options={"timeout": 300}  # 5 min timeout for large videos
                )
            finally:
                os.unlink(tmp_path)
        else:
            # Small file: use inline (faster)
            logger.info(f"[{request_id}] Using inline data (size {size_mb:.2f}MB)")
            response = model.generate_content(
                [
                    {"mime_type": "video/mp4", "data": video_bytes},
                    PROMPT
                ],
                generation_config={"response_mime_type": "application/json"},
                request_options={"timeout": 120}  # 2 min timeout for small videos
            )

        gemini_elapsed = time.time() - gemini_start
        logger.info(f"[{request_id}] Gemini latency: {gemini_elapsed:.2f}s")
        logger.info(f"[{request_id}] Raw response: {response.text}")

        # 5. Parse response
        result = json.loads(response.text)

        # New format: {"found": bool, "deliveries_detected_at_time": [...], "total_count": int}
        if "deliveries_detected_at_time" in result:
            timestamps = result.get("deliveries_detected_at_time", [])
            timestamps = sorted([float(t) for t in timestamps])  # Ensure sorted floats
            final_response = {
                "found": len(timestamps) > 0,
                "deliveries_detected_at_time": timestamps,
                "total_count": len(timestamps)
            }
            logger.info(f"[{request_id}] === DETECT-ACTION END === {final_response}")
            return final_response

        # Legacy format fallback: {"deliveries": [{timestamp, confidence}, ...]}
        if "deliveries" in result:
            deliveries = result.get("deliveries", [])
            threshold = settings.SCOUT_CONFIDENCE_THRESHOLD
            valid_timestamps = sorted([
                float(d.get("timestamp", 0))
                for d in deliveries
                if d.get("confidence", 0) >= threshold
            ])
            final_response = {
                "found": len(valid_timestamps) > 0,
                "deliveries_detected_at_time": valid_timestamps,
                "total_count": len(valid_timestamps)
            }
            logger.info(f"[{request_id}] === DETECT-ACTION END (legacy deliveries) === {final_response}")
            return final_response

        # Legacy list format: [{found, timestamp, confidence}, ...]
        if isinstance(result, list):
            threshold = settings.SCOUT_CONFIDENCE_THRESHOLD
            valid_timestamps = sorted([
                float(d.get("timestamp", 0))
                for d in result
                if d.get("found", True) and d.get("confidence", 0) >= threshold
            ])
            final_response = {
                "found": len(valid_timestamps) > 0,
                "deliveries_detected_at_time": valid_timestamps,
                "total_count": len(valid_timestamps)
            }
            logger.info(f"[{request_id}] === DETECT-ACTION END (legacy list) === {final_response}")
            return final_response

        # Legacy single dict: {"found": bool, "timestamp": float, "confidence": float}
        if result.get("found") and result.get("confidence", 0) >= settings.SCOUT_CONFIDENCE_THRESHOLD:
            ts = float(result.get("timestamp", 0))
            final_response = {
                "found": True,
                "deliveries_detected_at_time": [ts],
                "total_count": 1
            }
            logger.info(f"[{request_id}] === DETECT-ACTION END (legacy single) === {final_response}")
            return final_response

        # No deliveries found
        final_response = {"found": False, "deliveries_detected_at_time": [], "total_count": 0}
        logger.info(f"[{request_id}] === DETECT-ACTION END (none found) === {final_response}")
        return final_response

    except Exception as e:
        import traceback
        logger.error(f"[{request_id}] Detection Error: {e}")
        logger.error(f"[{request_id}] Traceback: {traceback.format_exc()}")
        return {"found": False, "deliveries_detected_at_time": [], "total_count": 0, "error": str(e)}
    finally:
        # Cleanup uploaded file from Gemini
        if uploaded_file:
            try:
                genai.delete_file(uploaded_file.name)
                logger.info(f"[{request_id}] Cleaned up uploaded file: {uploaded_file.name}")
            except Exception as cleanup_err:
                logger.warning(f"[{request_id}] Failed to cleanup file: {cleanup_err}")


# ============ Session History Endpoints ============

from storage import get_storage_service
from database import insert_delivery, get_deliveries, get_delivery, get_next_delivery_sequence

@app.post("/upload-clip")
async def upload_clip(
    file: UploadFile = File(...),
    release_timestamp: float = Form(0.0),
    speed: str = Form(None),
    report: str = Form(None),
    tips: str = Form("")
):
    """
    Upload a video clip to cloud storage for session history.
    Returns cloud URLs for video and thumbnail.
    """
    logger.info(f"Uploading clip: {file.filename}")
    
    # 1. Save locally
    temp_dir = "temp_videos"
    os.makedirs(temp_dir, exist_ok=True)
    delivery_id = str(uuid.uuid4())
    file_path = os.path.join(temp_dir, f"{delivery_id}.mp4")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    try:
        # 2. Upload to GCS
        logger.info(f"[upload-clip] Attempting GCS upload for {delivery_id}")
        storage = get_storage_service()
        logger.info(f"[upload-clip] Storage service initialized, bucket: {storage.bucket_name}")
        # Use proxy URLs (streams through backend, no signed URL needed)
        base_url = str(settings.BASE_URL) if hasattr(settings, 'BASE_URL') else "https://bowlingmate-230175862422.us-central1.run.app"
        video_url, thumbnail_url = storage.upload_clip(file_path, delivery_id, base_url=base_url)
        logger.info(f"[upload-clip] GCS upload successful, proxy URLs generated")
        
        # 3. Save to database
        sequence = get_next_delivery_sequence()
        insert_delivery(
            delivery_id=delivery_id,
            sequence=sequence,
            cloud_video_url=video_url,
            cloud_thumbnail_url=thumbnail_url,
            release_timestamp=release_timestamp,
            speed=speed,
            report=report,
            tips=tips
        )
        
        logger.info(f"Clip uploaded: {delivery_id}")
        
        # 4. Cleanup local file
        if os.path.exists(file_path):
            os.remove(file_path)
        
        return {
            "id": delivery_id,
            "sequence": sequence,
            "video_url": video_url,
            "thumbnail_url": thumbnail_url
        }
        
    except Exception as e:
        import traceback
        logger.error(f"[upload-clip] Upload failed: {e}")
        logger.error(f"[upload-clip] Traceback: {traceback.format_exc()}")
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "id": None, "video_url": None, "thumbnail_url": None}
        )


@app.get("/deliveries")
async def list_deliveries(limit: int = 50):
    """Get all deliveries for session history, newest first."""
    deliveries = get_deliveries(limit)
    return {"deliveries": deliveries}


@app.get("/media/{media_type}/{delivery_id}")
async def stream_media(media_type: str, delivery_id: str):
    """
    Stream media (video/thumbnail) from GCS through the backend.
    Secure: no public GCS access needed, auth still required.
    """
    from fastapi.responses import Response

    storage = get_storage_service()

    if media_type == "video":
        blob_name = f"clips/{delivery_id}.mp4"
        content_type = "video/mp4"
    elif media_type == "thumb":
        blob_name = f"thumbs/{delivery_id}.jpg"
        content_type = "image/jpeg"
    else:
        return {"error": "Invalid media type"}

    logger.info(f"[media] Streaming {blob_name}")
    data = storage.download_blob(blob_name)

    if data is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Media not found"})

    return Response(content=data, media_type=content_type)


@app.get("/clip/{delivery_id}/signed-url")
async def get_clip_signed_url(delivery_id: str):
    """Generate a fresh signed URL for video playback (15 min expiry)."""
    storage = get_storage_service()
    url = storage.refresh_signed_url(delivery_id)
    return {"video_url": url}


@app.post("/generate-overlay")
async def generate_overlay(
    video: UploadFile = File(...),
    phases: str = Form(...)
):
    """
    Generate MediaPipe biomechanics overlay video.
    Takes video + Coach phases JSON, returns overlay video URL.
    """
    import tempfile
    import subprocess
    from mediapipe_overlay import process as create_overlay

    logger.info(f"Generating overlay for: {video.filename}")

    try:
        # Parse phases from Coach analysis
        phases_data = json.loads(phases)

        # Convert Coach phases to MediaPipe feedback format
        joint_map = {
            "run-up": {"good": ["RIGHT_KNEE", "LEFT_KNEE", "RIGHT_HIP", "LEFT_HIP"]},
            "loading/coil": {"good": ["RIGHT_SHOULDER", "LEFT_SHOULDER", "RIGHT_HIP"]},
            "release action": {"injury_risk": ["RIGHT_ELBOW"], "good": ["RIGHT_WRIST"]},
            "release": {"injury_risk": ["RIGHT_ELBOW"], "good": ["RIGHT_WRIST"]},
            "wrist/snap": {"slow": ["RIGHT_WRIST"]},
            "follow-through": {"slow": ["RIGHT_HIP"], "good": ["RIGHT_SHOULDER"]}
        }

        feedback = {"phases": []}
        duration = 5.0
        phase_duration = duration / max(len(phases_data), 1)

        for i, p in enumerate(phases_data):
            name = p.get("name", "").lower()
            status = p.get("status", "").upper()

            fb = {"good": [], "slow": [], "injury_risk": []}
            if "GOOD" in status:
                fb["good"] = joint_map.get(name, {}).get("good", ["RIGHT_SHOULDER"])
            elif "NEEDS WORK" in status:
                fb["injury_risk"] = joint_map.get(name, {}).get("injury_risk", [])
                fb["slow"] = joint_map.get(name, {}).get("slow", ["RIGHT_SHOULDER"])

            feedback["phases"].append({
                "start": i * phase_duration,
                "end": (i + 1) * phase_duration,
                "name": p.get("name", f"phase_{i}"),
                "feedback": fb
            })

        # Save video to temp file
        video_bytes = await video.read()
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(video_bytes)
            input_path = tmp.name

        # Save feedback
        feedback_path = input_path.replace(".mp4", "_fb.json")
        with open(feedback_path, "w") as f:
            json.dump(feedback, f)

        # Generate overlay
        output_path = input_path.replace(".mp4", "_overlay.mp4")
        create_overlay(input_path, feedback_path, output_path)

        # Compress for mobile
        compressed_path = output_path.replace(".mp4", "_web.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-i", output_path,
            "-vcodec", "libx264", "-crf", "28", "-vf", "scale=480:-2",
            "-preset", "fast", compressed_path
        ], capture_output=True)

        # Upload to GCS
        delivery_id = str(uuid.uuid4())
        storage = get_storage_service()
        base_url = "https://bowlingmate-230175862422.us-central1.run.app"
        video_url, _ = storage.upload_clip(compressed_path, f"overlay_{delivery_id}", base_url=base_url)

        # Cleanup temp files
        for p in [input_path, feedback_path, output_path, compressed_path]:
            if os.path.exists(p):
                os.remove(p)

        logger.info(f"Overlay generated: {video_url}")
        return {"overlay_url": video_url}

    except Exception as e:
        logger.error(f"Overlay generation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": str(e)}


# ============ Interactive Coach Chat ============

class ChatRequest(BaseModel):
    message: str
    delivery_id: str
    phases: list  # List of phase dicts with name, status, clip_ts

class ChatResponse(BaseModel):
    text: str
    video_action: dict | None = None

# Gemini function calling tool for video control
COACH_CHAT_TOOL = {
    "function_declarations": [{
        "name": "control_video",
        "description": "Control the bowling video to illustrate your coaching point. Use this to show specific moments when explaining technique.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["focus", "pause", "play"],
                    "description": "focus=loop subsection at 0.5x speed, pause=stop playback, play=resume normal"
                },
                "timestamp": {
                    "type": "number",
                    "description": "Seconds into clip (0-5). Required for 'focus' action. Use the clip_ts from phases."
                }
            },
            "required": ["action"]
        }
    }]
}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_coach(request: ChatRequest):
    """
    Interactive chat with Coach AI. Returns coaching response with optional video control action.
    Video actions: focus (loop at timestamp), pause, play
    """
    import google.generativeai as genai
    import time

    request_id = f"CHAT-{int(time.time()*1000)}"
    logger.info(f"[{request_id}] === CHAT START ===")
    logger.info(f"[{request_id}] Message: {request.message}")
    logger.info(f"[{request_id}] Delivery: {request.delivery_id}")
    logger.info(f"[{request_id}] Phases count: {len(request.phases)}")

    try:
        # Configure Gemini
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(
            model_name=settings.GEMINI_MODEL_NAME,
            tools=[COACH_CHAT_TOOL]
        )
        logger.info(f"[{request_id}] Model: {settings.GEMINI_MODEL_NAME}")

        # Build context with phase timestamps
        phases_context = []
        for p in request.phases:
            clip_ts = p.get("clip_ts") or p.get("clipTimestamp")
            phases_context.append({
                "name": p.get("name", "Unknown"),
                "status": p.get("status", ""),
                "clip_ts": clip_ts,
                "observation": p.get("observation", ""),
                "tip": p.get("tip", "")
            })
            logger.info(f"[{request_id}] Phase: {p.get('name')} @ {clip_ts}s")

        # Load prompt template from file
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "coach_chat_prompt.txt")
        try:
            with open(prompt_path, "r") as f:
                prompt_template = f.read()
            system_prompt = prompt_template.replace("{phases_json}", json.dumps(phases_context, indent=2))
            logger.info(f"[{request_id}] Prompt loaded from file")
        except FileNotFoundError:
            logger.warning(f"[{request_id}] Prompt file not found, using inline")
            system_prompt = f"You are Coach analyzing bowling. Phases: {json.dumps(phases_context)}"

        # Generate response with function calling
        start_time = time.time()
        response = model.generate_content(
            [system_prompt, f"User: {request.message}"],
            tool_config={"function_calling_config": {"mode": "AUTO"}}
        )
        latency = time.time() - start_time
        logger.info(f"[{request_id}] Gemini latency: {latency:.2f}s")

        # Extract text and function call
        text_response = ""
        video_action = None

        for part in response.parts:
            if hasattr(part, 'text') and part.text:
                text_response += part.text
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                video_action = {
                    "action": fc.args.get("action"),
                    "timestamp": fc.args.get("timestamp")
                }
                logger.info(f"[{request_id}] Video action: {video_action}")

        logger.info(f"[{request_id}] Response: {text_response[:100]}...")
        logger.info(f"[{request_id}] === CHAT END ===")
        return ChatResponse(text=text_response, video_action=video_action)

    except Exception as e:
        import traceback
        logger.error(f"[{request_id}] Error: {e}")
        logger.error(f"[{request_id}] Traceback: {traceback.format_exc()}")
        return ChatResponse(text="Sorry, I couldn't process that. Please try again.", video_action=None)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
