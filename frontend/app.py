"""BowlingMate Web Demo — Streamlit frontend calling the Cloud Run backend."""
import streamlit as st
import requests
import json
import struct
import time
import os

BACKEND_URL = os.getenv("BACKEND_URL", "https://bowlingmate-m4xzkste5q-uc.a.run.app")
API_SECRET = os.getenv("API_SECRET", "bowlingmate-hackathon-secret")
HEADERS = {"Authorization": f"Bearer {API_SECRET}"}
MAX_UPLOAD_MB = 5
MAX_DURATION_S = 120  # 2 minutes max

SAMPLE_VIDEO_PATH = os.path.join(os.path.dirname(__file__), "sample_bowling_clip.mp4")

def get_mp4_duration(data: bytes) -> float:
    """Extract duration in seconds from MP4/MOV mvhd atom. Returns 0 on failure."""
    i = 0
    while i < len(data) - 8:
        size = struct.unpack('>I', data[i:i+4])[0]
        box_type = data[i+4:i+8]
        if size < 8:
            break
        if box_type == b'moov':
            j = i + 8
            while j < i + size - 8:
                inner_size = struct.unpack('>I', data[j:j+4])[0]
                inner_type = data[j+4:j+8]
                if inner_size < 8:
                    break
                if inner_type == b'mvhd':
                    version = data[j+8]
                    if version == 0:
                        timescale = struct.unpack('>I', data[j+20:j+24])[0]
                        duration = struct.unpack('>I', data[j+24:j+28])[0]
                    else:
                        timescale = struct.unpack('>I', data[j+28:j+32])[0]
                        duration = struct.unpack('>Q', data[j+32:j+40])[0]
                    return duration / timescale if timescale else 0
                j += inner_size
        i += size
    return 0


CHAT_CHIPS = [
    "How can I improve my release?",
    "What should I focus on in my run-up?",
    "Is my follow-through safe for my body?",
    "Show me the wrist snap moment",
]

# ── Page config ──
st.set_page_config(page_title="BowlingMate", page_icon="🏏", layout="centered")

# ── Custom CSS ──
st.markdown("""
<style>
    .stApp { max-width: 800px; margin: 0 auto; }
    .phase-good { background: #f5f0e8; border-left: 4px solid #5a7247; padding: 12px; border-radius: 6px; margin: 8px 0; color: #2c2c2c; }
    .phase-bad { background: #faf5ef; border-left: 4px solid #c4956a; padding: 12px; border-radius: 6px; margin: 8px 0; color: #2c2c2c; }
    .phase-title { font-weight: bold; font-size: 1.05em; color: #3a3a3a; }
    .speed-badge { background: #3b5249; color: #f5f0e8;
        padding: 8px 20px; border-radius: 20px; display: inline-block; font-size: 1.3em; font-weight: bold; }
    .metric-row { display: flex; gap: 12px; margin: 12px 0; }
    .metric-card { flex: 1; background: #f5f0e8; padding: 12px; border-radius: 6px; text-align: center; color: #2c2c2c; }
</style>
""", unsafe_allow_html=True)


def call_scout(video_bytes: bytes, filename: str) -> dict:
    """POST /detect-action — find delivery timestamps."""
    resp = requests.post(
        f"{BACKEND_URL}/detect-action",
        headers=HEADERS,
        files={"file": (filename, video_bytes, "video/mp4")},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def call_analyze(video_bytes: bytes) -> str:
    """POST /analyze — submit for Expert analysis, return video_id."""
    resp = requests.post(
        f"{BACKEND_URL}/analyze",
        headers=HEADERS,
        files={"video": ("clip.mp4", video_bytes, "video/mp4")},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["video_id"]


def stream_analysis(video_id: str) -> dict:
    """GET /stream-analysis — consume SSE, return final result."""
    resp = requests.get(
        f"{BACKEND_URL}/stream-analysis",
        headers=HEADERS,
        params={"video_id": video_id, "generate_overlay": "true"},
        stream=True,
        timeout=300,
    )
    resp.raise_for_status()
    result = {}
    for line in resp.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data: "):
            continue
        payload = line[6:]
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if data.get("status") == "success":
            result = data
        elif data.get("status") == "overlay":
            result["overlay_url"] = data.get("overlay_url")
    return result


def call_chat(message: str, delivery_id: str, phases: list) -> dict:
    """POST /chat — interactive follow-up."""
    resp = requests.post(
        f"{BACKEND_URL}/chat",
        headers=HEADERS,
        json={"message": message, "delivery_id": delivery_id, "phases": phases},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def render_phases(phases: list):
    """Render the 6-phase analysis cards."""
    good = [p for p in phases if p.get("status") == "GOOD"]
    needs_work = [p for p in phases if p.get("status") != "GOOD"]
    sorted_phases = good + needs_work

    for phase in sorted_phases:
        css_class = "phase-good" if phase.get("status") == "GOOD" else "phase-bad"
        icon = "✅" if phase.get("status") == "GOOD" else "⚠️"
        st.markdown(f"""
        <div class="{css_class}">
            <div class="phase-title">{icon} {phase['name']} — {phase.get('status', '')}</div>
            <div style="margin-top:6px; color:#4a4a4a;">{phase.get('observation', '')}</div>
            <div style="margin-top:6px; color:#5a7247;"><b>Tip:</b> {phase.get('tip', '')}</div>
        </div>
        """, unsafe_allow_html=True)


# ── Session state init ──
for key in ["video_bytes", "video_name", "scout_result", "analysis_result",
            "video_id", "delivery_id", "chat_messages", "step", "video_seek"]:
    if key not in st.session_state:
        st.session_state[key] = None
if st.session_state.step is None:
    st.session_state.step = "upload"
if st.session_state.chat_messages is None:
    st.session_state.chat_messages = []


# ══════════════════════════════════════
# STEP 1: Upload / Select Video
# ══════════════════════════════════════
st.title("🏏 BowlingMate")
st.caption("AI-native cricket bowling analysis — powered by Gemini 3")

if st.session_state.step == "upload":
    st.subheader("Select a video")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📎 Use Sample Clip", use_container_width=True):
            with open(SAMPLE_VIDEO_PATH, "rb") as f:
                st.session_state.video_bytes = f.read()
            st.session_state.video_name = "sample_bowling_clip.mp4"
            st.session_state.step = "detect"
            st.rerun()

    with col2:
        st.caption("MP4, max 5MB, first 2 mins only")
        uploaded = st.file_uploader(
            "Upload your own",
            type=["mp4"],
            label_visibility="collapsed",
        )
        if uploaded:
            if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(f"File too large ({uploaded.size / 1024 / 1024:.1f}MB). Max {MAX_UPLOAD_MB}MB.")
            else:
                st.session_state.video_bytes = uploaded.read()
                st.session_state.video_name = uploaded.name
                st.session_state.step = "detect"
                st.rerun()


# ══════════════════════════════════════
# STEP 2: Scout Detection
# ══════════════════════════════════════
elif st.session_state.step == "detect":
    st.subheader("📹 Your Video")
    st.video(st.session_state.video_bytes)

    if st.session_state.scout_result is None:
        with st.spinner("🔍 Scout (Gemini 3 Flash) scanning for deliveries..."):
            try:
                result = call_scout(st.session_state.video_bytes, st.session_state.video_name)
                timestamps = result.get("deliveries_detected_at_time", [])
                # Get actual video duration from MP4 header
                video_duration = get_mp4_duration(st.session_state.video_bytes)
                if video_duration > 0:
                    # Filter out hallucinated timestamps beyond video length
                    timestamps = [t for t in timestamps if t <= video_duration + 1]
                # Deduplicate within +-0.5s
                deduped = []
                for t in sorted(timestamps):
                    if not deduped or abs(t - deduped[-1]) > 0.5:
                        deduped.append(t)
                result["deliveries_detected_at_time"] = deduped
                result["total_count"] = len(deduped)
                if not deduped:
                    result["found"] = False
                st.session_state.scout_result = result
                st.rerun()
            except Exception as e:
                st.error(f"Scout failed: {e}")
                if st.button("← Back"):
                    st.session_state.step = "upload"
                    st.session_state.scout_result = None
                    st.rerun()
    else:
        result = st.session_state.scout_result
        if result.get("found"):
            timestamps = result.get("deliveries_detected_at_time", [])
            st.success(f"Found **{result['total_count']}** delivery(s) at: {', '.join(f'{t:.1f}s' for t in timestamps)}")

            st.subheader("🎯 Detected Deliveries")
            for i, ts in enumerate(timestamps):
                with st.container():
                    st.markdown(f"**Delivery {i + 1}** — detected at {ts:.1f}s")
                    st.video(st.session_state.video_bytes)
                    if st.button(f"Analyze Delivery {i + 1}", key=f"analyze_{i}", use_container_width=True):
                        st.session_state.step = "analyze"
                        st.rerun()
        else:
            st.warning("No deliveries detected. Try a different video.")

        if st.button("← Choose another video"):
            for key in ["video_bytes", "video_name", "scout_result", "analysis_result",
                        "video_id", "delivery_id", "chat_messages"]:
                st.session_state[key] = None
            st.session_state.step = "upload"
            st.rerun()


# ══════════════════════════════════════
# STEP 3: Expert Analysis
# ══════════════════════════════════════
elif st.session_state.step == "analyze":
    if st.session_state.analysis_result is None:
        st.subheader("🧠 Expert Analysis")
        status_text = st.empty()
        progress_bar = st.progress(0)

        try:
            status_text.markdown("**Uploading clip to Expert (Gemini 3 Pro)...**")
            progress_bar.progress(10)
            video_id = call_analyze(st.session_state.video_bytes)
            st.session_state.video_id = video_id
            st.session_state.delivery_id = video_id

            status_text.markdown("**Expert AI (Gemini 3 Pro) Thinking...**")
            progress_bar.progress(30)

            result = stream_analysis(video_id)
            progress_bar.progress(90)

            if result:
                st.session_state.analysis_result = result
                progress_bar.progress(100)
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("Analysis returned empty. Try again.")
                if st.button("← Back"):
                    st.session_state.step = "detect"
                    st.rerun()

        except Exception as e:
            st.error(f"Expert analysis failed: {e}")
            if st.button("← Back"):
                st.session_state.step = "detect"
                st.rerun()
    else:
        result = st.session_state.analysis_result

        # ── Summary ──
        st.subheader("📊 Analysis Summary")

        st.video(st.session_state.video_bytes)

        # Speed + effort
        col1, col2, col3 = st.columns(3)
        with col1:
            speed = result.get("speed_est", result.get("estimated_speed_kmh", "—"))
            if isinstance(speed, (int, float)):
                speed = f"{speed} km/h"
            st.markdown(f'<div class="speed-badge">{speed}</div>', unsafe_allow_html=True)
        with col2:
            st.metric("Effort", result.get("effort", "—"))
        with col3:
            st.metric("Latency", f"{result.get('latency', 0):.1f}s")

        # Report
        report = result.get("report", "")
        if report:
            st.info(report)

        # Tips
        tips = result.get("tips", [])
        if tips:
            st.subheader("💡 Quick Tips")
            for tip in tips:
                st.markdown(f"- {tip}")

        st.divider()

        # ── Expert Phases ──
        st.subheader("🔬 Expert Breakdown (6 Phases)")
        phases = result.get("phases", [])
        render_phases(phases)

        st.divider()

        # ── Overlay ──
        overlay_url = result.get("overlay_url")
        if overlay_url:
            st.subheader("🦴 Skeleton Overlay")
            st.caption("MediaPipe pose detection — Green: good, Red: injury risk, Yellow: needs work")
            try:
                overlay_resp = requests.get(overlay_url, headers=HEADERS, timeout=30)
                if overlay_resp.status_code == 200:
                    st.video(overlay_resp.content)
                else:
                    st.warning("Overlay video not yet available.")
            except Exception:
                st.warning("Could not load overlay video.")
        else:
            with st.spinner("⏳ Generating skeleton overlay..."):
                time.sleep(2)
                st.caption("Overlay generation may take up to 60 seconds. Refresh to check.")

        st.divider()

        # ── Chat ──
        st.subheader("💬 Ask the Expert")
        st.caption("The Expert references specific moments in your delivery and controls video playback — powered by Gemini 3 Pro function calling.")

        # Video action indicator
        if st.session_state.video_seek is not None and st.session_state.video_seek > 0:
            st.info(f"On iOS: video loops in slow-motion at {st.session_state.video_seek:.1f}s")

        # Chat history
        for msg in st.session_state.chat_messages:
            if msg["role"] == "user":
                st.chat_message("user").write(msg["content"])
            else:
                content = msg["content"]
                action = msg.get("video_action")
                with st.chat_message("assistant"):
                    st.write(content)
                    if action:
                        ts = action.get("timestamp", 0)
                        st.caption(f"Video: {action.get('action', 'focus')} at {ts:.1f}s")

        # Chips
        st.markdown("**Ask about a specific phase:**")
        chip_cols = st.columns(2)
        for i, chip in enumerate(CHAT_CHIPS):
            col = chip_cols[i % 2]
            with col:
                if st.button(chip, key=f"chip_{i}", use_container_width=True):
                    st.session_state.chat_messages.append({"role": "user", "content": chip})
                    try:
                        chat_resp = call_chat(chip, st.session_state.delivery_id, phases)
                        reply = chat_resp.get("text", "Sorry, I couldn't generate a response.")
                        video_action = chat_resp.get("video_action")
                        msg = {"role": "assistant", "content": reply}
                        if video_action:
                            msg["video_action"] = video_action
                            st.session_state.video_seek = video_action.get("timestamp", 0)
                        st.session_state.chat_messages.append(msg)
                    except Exception as e:
                        st.session_state.chat_messages.append({"role": "assistant", "content": f"Error: {e}"})
                    st.rerun()

        # Free text
        user_input = st.chat_input("Ask anything about your delivery...")
        if user_input:
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            try:
                chat_resp = call_chat(user_input, st.session_state.delivery_id, phases)
                reply = chat_resp.get("text", "Sorry, I couldn't generate a response.")
                video_action = chat_resp.get("video_action")
                msg = {"role": "assistant", "content": reply}
                if video_action:
                    msg["video_action"] = video_action
                    st.session_state.video_seek = video_action.get("timestamp", 0)
                st.session_state.chat_messages.append(msg)
            except Exception as e:
                st.session_state.chat_messages.append({"role": "assistant", "content": f"Error: {e}"})
            st.rerun()

        st.divider()
        if st.button("← Analyze another delivery", use_container_width=True):
            st.session_state.analysis_result = None
            st.session_state.chat_messages = []
            st.session_state.step = "detect"
            st.rerun()


# ── Footer ──
st.markdown("---")
st.caption("BowlingMate — Gemini 3 Hackathon 2026 | [GitHub](https://github.com/kanarupandev/bowlingMate)")
