def get_multi_bowl_detection_prompt(config: str, language: str) -> str:
    return f"""
    Analyze this cricket bowling video for a {config} level player in {language}.
    This video may contain multiple deliveries.
    
    TASK:
    1. Identify EVERY distinct bowling delivery in the video.
    2. For each delivery, find the precise arm-high release timestamp.
    
    OUTPUT FORMAT:
    Provide a JSON list of objects, each containing:
    - "release_ts": float (seconds)
    - "label": string (e.g. "Bowl 1", "Bowl 2")
    
    Example:
    [
        {{"release_ts": 3.4, "label": "Bowl 1"}},
        {{"release_ts": 12.1, "label": "Bowl 2"}}
    ]
    """

def get_analysis_prompt(config: str, language: str, release_ts: float) -> str:
    return f"""
Analyze this cricket bowling delivery. Release point is at {release_ts}s.

Setting: Any — backyard, park, indoor, net session. Shadow bowling (no ball) is valid.

Config: {config}
- Junior: Encouraging, simple language
- Club: Direct, balanced feedback
- Technical: Biomechanical detail

Analyze 6 phases around the release point:
1. Run-up (rhythm, balance)
2. Loading/Coil (hip/shoulder separation)
3. Release Action (arm path, elbow legality ≤15°)
4. Wrist/Snap (position, seam orientation)
5. Head/Eyes (stability, target focus)
6. Follow-through (arm continuation, balance)

IMPORTANT: For each phase, provide `clip_ts` - the timestamp in THIS video clip where that phase is best visible.
The clip is ~5 seconds with release around 2.0s. Estimate timestamps based on what you see.

Speed: Estimate km/h if ball visible (assume 20m pitch). Use "_" if shadow bowling or unsure.
Effort: Low | Medium | High | Max

OUTPUT (JSON only):
{{
  "phases": [
    {{"name": "Run-up", "status": "GOOD|NEEDS WORK", "observation": "...", "tip": "...", "clip_ts": 0.5}},
    {{"name": "Loading/Coil", "status": "...", "observation": "...", "tip": "...", "clip_ts": 1.5}},
    {{"name": "Release Action", "status": "...", "observation": "...", "tip": "...", "clip_ts": 2.0}},
    {{"name": "Wrist/Snap", "status": "...", "observation": "...", "tip": "...", "clip_ts": 2.2}},
    {{"name": "Head/Eyes", "status": "...", "observation": "...", "tip": "...", "clip_ts": 2.0}},
    {{"name": "Follow-through", "status": "...", "observation": "...", "tip": "...", "clip_ts": 3.0}}
  ],
  "estimated_speed_kmh": 85,
  "effort": "High",
  "summary": "One sentence: biggest strength + priority fix",
  "release_timestamp": {release_ts}
}}
    """
