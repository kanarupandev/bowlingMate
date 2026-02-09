import os
import logging
import time
import json
from typing import TypedDict, Annotated, List, Union
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
import operator
import google.generativeai as genai

from rag import retrieve_knowledge
from database import insert_summary, get_summaries, get_next_bowl_num
from config import get_settings
from prompts import get_analysis_prompt

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    video_path: str
    config: str
    language: str
    bowl_count: int
    report: str
    speed_est: str

# --- Tools (Simulated as functions for the node) ---

def analyze_video_tool(video_path: str, config: str, language: str) -> str:
    """
    Constructs the prompt and calls Gemini with the video.
    In a real scenario, this would upload the video file to Gemini API first.
    For MVP, we assume the LLM can process the video content (or we describe it).
    """
    # Note: In actual implementation, we need to upload the file to File API.
    # Here we construct the multimodal prompt.
    
    prompt = f"""
    Analyze this cricket bowling video clip (backyard setting).
    Configuration: {config} (Junior: simple/encouraging, Club: direct/motivational, Technical: analytical).
    Language: {language}.
    
    Identify 4-6 critical points:
    1. Run-up
    2. Loading/Coil
    3. Release Action
    4. Snap/Wrist
    5. Head/Eyes
    6. Follow-through
    
    For each valid point, provide:
    - Status: (Good) or (Needs Improvement)
    - Observation: Brief description.
    - Advice: One specific actionable tip.
    
    Also estimate the bowling speed (approx km/h) based on visual cues (assume 20m pitch).
    
    Return the response in a structured format (JSON or Markdown bullet points) suitable for parsing.
    End with a specifically formatted line: "SPEED_EST: <value> km/h"
    """
    return prompt

# --- Nodes ---

def agent_node(state: AgentState):
    video_path = state.get("video_path")
    config = state.get("config", "club")
    language = state.get("language", "en")
    
    logger = logging.getLogger("wellBowled.agent")
    logger.info(f"Agent Node Started. Video: {video_path}")
    
    settings = get_settings()
    genai.configure(api_key=settings.GOOGLE_API_KEY)

    logger.info("Uploading video to Gemini File API...")
    try:
        video_file = genai.upload_file(path=video_path)
        logger.info(f"Video uploaded: {video_file.name}")

        # Wait for processing
        while video_file.state.name == "PROCESSING":
            logger.info("Waiting for video processing...")
            time.sleep(2)
            video_file = genai.get_file(video_file.name)

        if video_file.state.name == "FAILED":
            raise ValueError(f"Video processing failed: {video_file.state.name}")

        logger.info("Video is ACTIVE. Generating content...")

        prompt = get_analysis_prompt(config, language, release_ts=3.0)
        model = genai.GenerativeModel(model_name=settings.COACH_MODEL)

        start_time = time.time()
        logger.info(f"Generating content with model {settings.COACH_MODEL}...")
        response = model.generate_content([video_file, prompt])
        duration = time.time() - start_time

        content = response.text
        logger.info(f"Gemini Response received in {duration:.2f}s: {content}")

        # Parse JSON
        try:
            # Strip markdown code blocks if present
            clean_content = content.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_content)
            report_body = data.get("report", content)
            speed_est = data.get("speed_est", "0 km/h")
            tips = data.get("tips", [])
            release_ts = data.get("release_timestamp", 0.0)
        except Exception as e:
            logger.error(f"JSON Parse Error: {e}")
            report_body = content
            speed_est = "0 km/h"
            tips = []
            release_ts = 0.0
            
    except Exception as e:
        logger.error(f"Error in Gemini Video Analysis: {e}")
        report_body = "Analysis failed. Please try again."
        speed_est = "0 km/h"
        tips = []
        release_ts = 0.0

    # Save result (with tips and timestamp in report for now)
    bowl_num = get_next_bowl_num()
    logger.info(f"Saving summary for Bowl #{bowl_num}...")
    # For MVP we stick to report_body, we can join tips if needed
    full_report = f"{report_body}\n\nTIPS:\n- " + "\n- ".join(tips)
    insert_summary(bowl_num, full_report, speed_est, config)
    
    return {
        "messages": [AIMessage(content=report_body)],
        "report": report_body,
        "speed_est": speed_est,
        "bowl_count": bowl_num,
        "tips": tips,
        "release_timestamp": release_ts
    }

# --- Graph Construction ---

workflow = StateGraph(AgentState)
workflow.add_node("agent", agent_node)
workflow.set_entry_point("agent")
workflow.add_edge("agent", END)

app_graph = workflow.compile()

async def run_streamed_agent(video_bytes: bytes, config: str, language: str):
    logger = logging.getLogger("wellBowled.agent")
    from prompts import get_analysis_prompt
    import google.generativeai as genai
    from google.generativeai.types import RequestOptions
    import json
    import asyncio
    import time
    from config import get_settings
    settings = get_settings()

    logger.info(f"[Coach] Starting analysis. Video size: {len(video_bytes)} bytes")

    # Mock mode - return actual Gemini response for 3sec_vid.mp4 (2026-02-08)
    if settings.MOCK_COACH:
        logger.info("[Coach] MOCK_COACH enabled - returning cached response for 3sec_vid.mp4")
        yield {"status": "event", "message": "🧠 Coach AI (Gemini 3 Pro) Thinking...", "type": "info"}
        await asyncio.sleep(1.0)  # Fast mock response (was 28s)
        # ACTUAL Gemini 3 Pro response for 3sec_vid.mp4 (2026-02-08)
        mock_response = {
            "status": "success",
            "report": "You have a natural ability to spin the ball, but the immediate priority is fixing the bent arm to ensure a legal delivery action.",
            "speed_est": "75 km/h",
            "tips": [
                "Lengthen your run-up slightly to establish a consistent rhythm before the jump.",
                "Try to keep the front shoulder closed longer during the jump to create torque.",
                "Focus on locking the elbow straight early in the swing to correct the throwing motion.",
                "Isolate this wrist snap; ensure it acts as a hinge at the end of a straight arm.",
                "Keep your head upright and eyes level to improve target accuracy.",
                "Continue the arm path across the body to safely dissipate energy."
            ],
            "release_timestamp": 1.0,
            "bowl_id": int(time.time()),
            "phases": [
                {"name": "Run-up", "status": "NEEDS WORK", "observation": "Short approach with limited momentum build-up into the crease.", "tip": "Lengthen your run-up slightly to establish a consistent rhythm before the jump."},
                {"name": "Loading/Coil", "status": "NEEDS WORK", "observation": "Action is quite 'chest-on' with hips and shoulders facing the batter simultaneously.", "tip": "Try to keep the front shoulder closed longer during the jump to create torque."},
                {"name": "Release Action", "status": "NEEDS WORK", "observation": "Visible elbow flexion and extension (jerking) during the arm cycle.", "tip": "Focus on locking the elbow straight early in the swing to correct the throwing motion."},
                {"name": "Wrist/Snap", "status": "GOOD", "observation": "Strong wrist input generating visible revolutions on the ball.", "tip": "Isolate this wrist snap; ensure it acts as a hinge at the end of a straight arm."},
                {"name": "Head/Eyes", "status": "NEEDS WORK", "observation": "Head falls away to the left (off-side) significantly at release.", "tip": "Keep your head upright and eyes level to improve target accuracy."},
                {"name": "Follow-through", "status": "GOOD", "observation": "Good body rotation and pivot on the front foot after release.", "tip": "Continue the arm path across the body to safely dissipate energy."}
            ],
            "effort": "Medium",
            "latency": 27.8,
            "mock": True
        }
        yield mock_response
        return

    genai.configure(api_key=settings.GOOGLE_API_KEY)

    try:
        # 1. Direct Analysis (Single Shot - GCS & File API Bypass)
        logger.info(f"[Coach] Using model: {settings.COACH_MODEL}")

        yield {"status": "event", "message": "🧠 Coach AI (Gemini 3 Pro) Thinking...", "type": "info"}

        model = genai.GenerativeModel(model_name=settings.COACH_MODEL)
        # Fixed release_ts at 3.0 for the 5s clip (T-3s preroll means release is at ~3s)
        release_ts = 3.0
        analysis_prompt = get_analysis_prompt(config, language, release_ts=release_ts)

        logger.info(f"[Coach] Calling Gemini with inline video data...")
        start_time = asyncio.get_event_loop().time()

        # Inline Content Pass (No File API delay)
        # CRITICAL: Add timeout to prevent infinite hangs
        def call_gemini():
            return model.generate_content(
                [
                    {"mime_type": "video/mp4", "data": video_bytes},
                    analysis_prompt
                ],
                generation_config={"response_mime_type": "application/json"},
                request_options=RequestOptions(timeout=120)  # 2 minute SDK timeout
            )

        response = await asyncio.wait_for(
            asyncio.to_thread(call_gemini),
            timeout=180  # 3 minute total timeout (includes async overhead)
        )
        e2e_latency = asyncio.get_event_loop().time() - start_time
        
        logger.info(f"Gemini 3 Pro Latency: {e2e_latency:.2f}s")
        
        try:
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            # --- LOG RAW COACH RESPONSE ---
            logger.info(f"raw_coach_response: {clean_text}")
            # ------------------------------
            raw_data = json.loads(clean_text)
            
            # Map new schema to App compatibility
            speed_val = raw_data.get("estimated_speed_kmh")
            # If speed is 0, "_", or missing, set to N/A
            if not speed_val or speed_val == 0 or speed_val == "_":
                speed_str = "N/A"
            else:
                speed_str = f"{speed_val} km/h"
                
            # Extract tips from phases
            extracted_tips = [p.get("tip") for p in raw_data.get("phases", []) if p.get("tip")]
            
            data = {
                "status": "success",
                "report": raw_data.get("summary", ""),
                "speed_est": speed_str,
                "tips": extracted_tips,
                "release_timestamp": raw_data.get("release_timestamp", release_ts),
                "bowl_id": int(time.time()), # Adding session-unique ID for app compatibility
                "phases": raw_data.get("phases", []), 
                "effort": raw_data.get("effort", "Medium"),
                "latency": e2e_latency
            }
            yield data
            
        except Exception as e:
            logger.error(f"JSON Parse Error: {e}")
            yield {"status": "error", "message": f"Failed to understand Coach's advice ({str(e)})"}
            
    except asyncio.TimeoutError:
        logger.error("Coach analysis timed out after 180s")
        yield {"status": "error", "message": "Analysis timed out. The video may be too complex. Please try a shorter clip."}
    except Exception as e:
        logger.error(f"Stream Agent Error: {e}")
        yield {"status": "error", "message": f"Global Error: {str(e)}"}

