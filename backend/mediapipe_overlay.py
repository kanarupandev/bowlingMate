"""
MediaPipe Overlay with TIME-BASED Feedback
Colors change based on action phases (run-up, landing, release, follow-through)
Usage: python overlay_timed.py input.mp4 timed_feedback.json output.mp4

Note: MediaPipe is OPTIONAL. If not installed (ENABLE_OVERLAY=false),
overlay generation will be skipped gracefully.
"""
import json
import sys
import logging

logger = logging.getLogger(__name__)

# Conditional MediaPipe import - may not be installed for fast builds
MEDIAPIPE_AVAILABLE = False
mp_pose = None
try:
    import cv2
    import mediapipe as mp
    mp_pose = mp.solutions.pose
    MEDIAPIPE_AVAILABLE = True
    logger.info("✅ MediaPipe loaded successfully")
except ImportError as e:
    logger.warning(f"⚠️ MediaPipe not available: {e}. Overlay generation disabled.")
    # Create stub for cv2 if not available
    try:
        import cv2
    except ImportError:
        cv2 = None


def is_overlay_available() -> bool:
    """Check if MediaPipe overlay generation is available."""
    return MEDIAPIPE_AVAILABLE and mp_pose is not None

# Only show key bowling joints (12 instead of 33)
KEY_JOINTS = {
    'LEFT_SHOULDER', 'RIGHT_SHOULDER',
    'LEFT_ELBOW', 'RIGHT_ELBOW',
    'LEFT_WRIST', 'RIGHT_WRIST',
    'LEFT_HIP', 'RIGHT_HIP',
    'LEFT_KNEE', 'RIGHT_KNEE',
    'LEFT_ANKLE', 'RIGHT_ANKLE'
}

GREEN = (0, 255, 0)
YELLOW = (0, 255, 255)
RED = (0, 0, 255)
WHITE = (255, 255, 255)

def load_timed_feedback(json_path):
    with open(json_path) as f:
        return json.load(f)['phases']

def get_phase_feedback(phases, timestamp):
    """Get feedback for current timestamp."""
    for idx, phase in enumerate(phases):
        if phase['start'] <= timestamp < phase['end']:
            return idx, phase['name'], phase['feedback']
    return len(phases)-1, "done", {"good": [], "slow": [], "injury_risk": []}

def get_color(name, feedback, phase_idx):
    """
    Phase 0 (run_up): Show all joints in white (scanning)
    Phase 1+: Only show joints with feedback, hide others
    """
    in_feedback = (name in feedback.get('injury_risk', []) or
                   name in feedback.get('slow', []) or
                   name in feedback.get('good', []))

    if phase_idx == 0:
        # Scanning phase - show all as white/light
        return (180, 180, 180)  # Light gray = "scanning"

    if not in_feedback:
        return None  # Don't draw

    if name in feedback.get('injury_risk', []):
        return RED
    if name in feedback.get('slow', []):
        return YELLOW
    return GREEN

def process(input_path, feedback_path, output_path):
    """Generate overlay video with color-coded skeleton feedback.

    Returns:
        str: Output path if successful, None if MediaPipe unavailable.
    Raises:
        RuntimeError: If video cannot be opened or has invalid properties.
    """
    if not is_overlay_available():
        logger.warning("⚠️ MediaPipe not available. Skipping overlay generation.")
        return None

    phases = load_timed_feedback(feedback_path)
    logger.info(f"[MediaPipe] Loaded {len(phases)} phases from {feedback_path}")

    # Detect rotation metadata from original video
    import subprocess
    rotation_degrees = 0
    try:
        probe_cmd = [
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream_tags=rotate:stream_side_data=rotation',
            '-of', 'default=noprint_wrappers=1',
            input_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        output = result.stdout.strip()

        for line in output.split('\n'):
            if line.startswith('rotate='):
                rotation_degrees = int(line.split('=')[1].strip())
                break
            elif line.startswith('rotation='):
                rotation_degrees = int(line.split('=')[1].strip())
                break

        # Normalize negative rotations: -90 -> 270, -180 -> 180, -270 -> 90
        if rotation_degrees < 0:
            rotation_degrees = 360 + rotation_degrees

        if rotation_degrees != 0:
            logger.info(f"[MediaPipe] Detected rotation metadata: {rotation_degrees}° (normalized)")
    except Exception as e:
        logger.warning(f"[MediaPipe] Could not detect rotation: {e}")

    cap = cv2.VideoCapture(input_path)

    # CRITICAL: Validate video opened successfully
    if not cap.isOpened():
        raise RuntimeError(f"cv2.VideoCapture failed to open: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Validate video properties
    if fps <= 0 or w <= 0 or h <= 0:
        cap.release()
        raise RuntimeError(f"Invalid video properties: fps={fps}, w={w}, h={h}. Check codec support.")

    logger.info(f"[MediaPipe] Video opened: {w}x{h} @ {fps}fps, {frame_count} frames")

    # Calculate output dimensions based on rotation
    # For 90/270 degree rotations, swap width and height
    if rotation_degrees in [90, 270]:
        output_w, output_h = h, w
        logger.info(f"[MediaPipe] Output dimensions (after rotation): {output_w}x{output_h}")
    else:
        output_w, output_h = w, h

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), int(fps), (output_w, output_h))

    if not out.isOpened():
        cap.release()
        raise RuntimeError(f"cv2.VideoWriter failed to create: {output_path}")

    frame_num = 0
    with mp_pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Rotate frame BEFORE MediaPipe processing for better pose detection
            # Note: rotation metadata indicates how much to rotate to correct orientation
            if rotation_degrees == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif rotation_degrees == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif rotation_degrees == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

            # Get actual frame dimensions after rotation
            frame_h, frame_w = frame.shape[:2]

            # Debug logging on first frame
            if frame_num == 0:
                logger.info(f"[MediaPipe] First frame after rotation: {frame_w}x{frame_h} (expected: {output_w}x{output_h})")

            timestamp = frame_num / fps
            phase_idx, phase_name, feedback = get_phase_feedback(phases, timestamp)

            results = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            # Debug logging on first frame
            if frame_num == 0:
                if results.pose_landmarks:
                    logger.info(f"[MediaPipe] ✅ Pose detected on first frame")
                    first_landmark = results.pose_landmarks.landmark[0]
                    logger.info(f"[MediaPipe] First landmark coords: ({first_landmark.x:.3f}, {first_landmark.y:.3f})")
                else:
                    logger.warning(f"[MediaPipe] ⚠️ NO POSE DETECTED on first frame!")

            # Draw phase label
            label = "ANALYZING..." if phase_idx == 0 else phase_name.upper()
            cv2.putText(frame, f"{label} ({timestamp:.1f}s)",
                       (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, WHITE, 2)

            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark

                # Draw connections (only between key joints)
                key_connections = [
                    (11, 12),  # shoulders
                    (11, 13), (13, 15),  # left arm
                    (12, 14), (14, 16),  # right arm
                    (11, 23), (12, 24),  # torso
                    (23, 24),  # hips
                    (23, 25), (25, 27),  # left leg
                    (24, 26), (26, 28),  # right leg
                ]
                line_color = (80, 80, 80) if phase_idx == 0 else (200, 200, 200)
                line_width = 2  # Increase from 1 to 2 for visibility
                for conn in key_connections:
                    p1, p2 = landmarks[conn[0]], landmarks[conn[1]]
                    cv2.line(frame,
                            (int(p1.x*frame_w), int(p1.y*frame_h)),
                            (int(p2.x*frame_w), int(p2.y*frame_h)), line_color, line_width)

                # Draw color-coded joints (only key joints)
                for idx, lm in enumerate(landmarks):
                    name = mp_pose.PoseLandmark(idx).name
                    if name not in KEY_JOINTS:
                        continue
                    color = get_color(name, feedback, phase_idx)
                    if color is None:
                        continue  # Skip joints without feedback
                    x, y = int(lm.x * frame_w), int(lm.y * frame_h)

                    # Debug first joint on first frame
                    if frame_num == 0 and idx == 11:  # Left shoulder
                        logger.info(f"[MediaPipe] Drawing left shoulder at pixel coords: ({x}, {y}), frame size: {frame_w}x{frame_h}")

                    size = 5 if phase_idx == 0 else 8  # Increase sizes for visibility
                    cv2.circle(frame, (x, y), size, color, -1)

            # Slow down on feedback phases (repeat frames)
            if phase_idx == 0:
                repeats = 1  # Normal speed while scanning
            else:
                repeats = 4  # 4x slower when showing feedback

            for _ in range(repeats):
                out.write(frame)
            frame_num += 1

    cap.release()
    out.release()

    # Validate output was created and has content
    import os
    if not os.path.exists(output_path):
        raise RuntimeError(f"Output file not created: {output_path}")

    output_size = os.path.getsize(output_path)
    if output_size < 1000:  # Less than 1KB is suspicious
        raise RuntimeError(f"Output file too small ({output_size} bytes), likely corrupted: {output_path}")

    logger.info(f"[MediaPipe] Output saved: {output_path} ({output_size} bytes, {frame_num} frames)")
    logger.info(f"[MediaPipe] Frames were rotated {rotation_degrees}° before processing for optimal MediaPipe accuracy")
    return output_path

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python overlay_timed.py input.mp4 timed_feedback.json output.mp4")
        sys.exit(1)
    process(sys.argv[1], sys.argv[2], sys.argv[3])
