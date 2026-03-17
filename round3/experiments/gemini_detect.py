"""
Gemini Frame Detection — Experiment Script

Usage:
    python gemini_detect.py videos/d001_120fps.mov --fps 120 --runs 3

Sends a short bowling clip to Gemini and asks it to identify:
1. The frame where the ball leaves the bowler's hand
2. The frame where the ball crosses each visible gate (crease, stumps, marker)

Runs multiple times to check consistency.

Requires: GOOGLE_API_KEY environment variable
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import google.generativeai as genai

PROMPT = """You are analyzing a slow-motion cricket bowling video recorded at {fps} frames per second.

The camera is positioned to see the full pitch with stumps at each end.

Your task: find the EXACT frame numbers for these events:

1. **release_frame**: The frame where the ball LEAVES the bowler's hand. Look for the moment
   of separation between hand and ball.

2. **gate_crossings**: For each visible landmark, the frame where the ball's center passes it:
   - "stumps_bowler": Bowler's end stumps (where the bowler releases from)
   - "marker_10m": Any visible marker/cone at approximately 10 metres from the bowling crease
   - "batting_crease": The batting crease line (white line near the batsman)
   - "stumps_striker": Striker's end stumps

Rules:
- Return ONLY frame numbers (integers, 0-indexed from start of video)
- If you cannot see a landmark, omit it from gate_crossings
- If the ball bounces before reaching a gate, still report the gate crossing frame
- Be as precise as possible — ±1 frame matters

Return STRICT JSON only:
{{
  "release_frame": 241,
  "gate_crossings": [
    {{"marker": "stumps_bowler", "frame": 243}},
    {{"marker": "marker_10m", "frame": 277}},
    {{"marker": "batting_crease", "frame": 305}},
    {{"marker": "stumps_striker", "frame": 308}}
  ]
}}
"""

# Known distances from release point (bowling crease)
GATE_DISTANCES = {
    "marker_10m": 10.0,
    "batting_crease": 17.68,
    "stumps_striker": 20.12,
}


def detect_frames(video_path, fps, model_name="gemini-2.5-flash"):
    """Send video to Gemini, get frame numbers back."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: Set GOOGLE_API_KEY environment variable")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    # Upload video
    print(f"  Uploading {video_path}...")
    video_file = genai.upload_file(str(video_path))

    # Wait for processing
    while video_file.state.name == "PROCESSING":
        print("  Waiting for video processing...")
        time.sleep(2)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name != "ACTIVE":
        print(f"  ERROR: Video processing failed: {video_file.state.name}")
        return None

    # Generate
    prompt = PROMPT.format(fps=int(fps))
    response = model.generate_content(
        [video_file, prompt],
        generation_config=genai.GenerationConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )

    # Parse response
    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        result = json.loads(text)
        return result
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"  ERROR parsing response: {e}")
        print(f"  Raw response: {response.text[:500]}")
        return None


def calculate_speed(result, fps):
    """Calculate speed from Gemini's frame detections."""
    if not result or "release_frame" not in result:
        return []

    release = result["release_frame"]
    speeds = []

    for gate in result.get("gate_crossings", []):
        marker = gate["marker"]
        frame = gate["frame"]
        distance = GATE_DISTANCES.get(marker)
        if distance is None:
            continue

        frame_diff = frame - release
        if frame_diff <= 0:
            continue

        time_s = frame_diff / fps
        speed_kph = (distance / time_s) * 3.6
        speeds.append({
            "marker": marker,
            "release_frame": release,
            "gate_frame": frame,
            "frame_diff": frame_diff,
            "time_s": round(time_s, 4),
            "speed_kph": round(speed_kph, 1),
        })

    return speeds


def main():
    parser = argparse.ArgumentParser(description="Gemini frame detection for speed")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--fps", type=float, default=120)
    parser.add_argument("--runs", type=int, default=3, help="Number of runs for consistency check")
    parser.add_argument("--model", default="gemini-2.5-flash", help="Gemini model name")
    parser.add_argument("--ground-truth", type=float, default=None, help="Known speed in kph")
    args = parser.parse_args()

    all_results = []
    all_speeds = []

    for run in range(args.runs):
        print(f"\n--- Run {run + 1}/{args.runs} ---")
        result = detect_frames(args.video, args.fps, args.model)
        if result:
            all_results.append(result)
            print(f"  Release frame: {result.get('release_frame')}")
            for gate in result.get("gate_crossings", []):
                print(f"  {gate['marker']}: frame {gate['frame']}")

            speeds = calculate_speed(result, args.fps)
            all_speeds.append(speeds)
            for s in speeds:
                print(f"  → {s['marker']}: {s['speed_kph']} kph ({s['time_s']}s)")

    # Consistency check
    print(f"\n{'='*50}")
    print("CONSISTENCY CHECK")
    print(f"{'='*50}")

    if len(all_results) >= 2:
        release_frames = [r.get("release_frame") for r in all_results if r]
        print(f"  Release frames across {len(release_frames)} runs: {release_frames}")
        if len(set(release_frames)) == 1:
            print("  ✓ Release frame: CONSISTENT")
        else:
            spread = max(release_frames) - min(release_frames)
            print(f"  ✗ Release frame: VARIES by {spread} frames")

        # Check gate consistency
        for gate_name in GATE_DISTANCES:
            gate_frames = []
            for r in all_results:
                for g in r.get("gate_crossings", []):
                    if g["marker"] == gate_name:
                        gate_frames.append(g["frame"])
            if gate_frames:
                if len(set(gate_frames)) == 1:
                    print(f"  ✓ {gate_name}: CONSISTENT (frame {gate_frames[0]})")
                else:
                    spread = max(gate_frames) - min(gate_frames)
                    print(f"  ✗ {gate_name}: VARIES by {spread} frames — {gate_frames}")

    # Average speed across runs
    if all_speeds:
        avg_speeds = {}
        for run_speeds in all_speeds:
            for s in run_speeds:
                marker = s["marker"]
                if marker not in avg_speeds:
                    avg_speeds[marker] = []
                avg_speeds[marker].append(s["speed_kph"])

        print(f"\nSPEED ESTIMATES (averaged across {len(all_speeds)} runs):")
        for marker, speeds in avg_speeds.items():
            mean = sum(speeds) / len(speeds)
            spread = max(speeds) - min(speeds)
            print(f"  {marker}: {mean:.1f} kph (spread: ±{spread/2:.1f} kph)")

        all_flat = [s for speeds in all_speeds for s in speeds]
        overall_mean = sum(s["speed_kph"] for s in all_flat) / len(all_flat)
        print(f"\n  OVERALL AVERAGE: {overall_mean:.1f} kph")

        if args.ground_truth:
            error = abs(overall_mean - args.ground_truth)
            print(f"  GROUND TRUTH:   {args.ground_truth} kph")
            print(f"  ERROR:          {error:.1f} kph")

    # Save results
    output_path = f"results/{Path(args.video).stem}_gemini.json"
    Path("results").mkdir(exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "video": args.video,
            "fps": args.fps,
            "model": args.model,
            "runs": all_results,
            "ground_truth_kph": args.ground_truth,
        }, f, indent=2)
    print(f"\n  Results saved: {output_path}")


if __name__ == "__main__":
    main()
