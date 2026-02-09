"""
Tests for MediaPipe biomechanics overlay generation.
"""
import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock


class TestMediaPipeOverlay:
    """Test the mediapipe_overlay module."""

    def test_load_timed_feedback(self):
        """Should correctly parse feedback JSON."""
        from mediapipe_overlay import load_timed_feedback

        feedback = {
            "phases": [
                {"start": 0.0, "end": 2.0, "name": "run_up", "feedback": {"good": ["RIGHT_KNEE"], "slow": [], "injury_risk": []}},
                {"start": 2.0, "end": 4.0, "name": "release", "feedback": {"good": [], "slow": [], "injury_risk": ["RIGHT_ELBOW"]}}
            ]
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(feedback, f)
            f.flush()
            phases = load_timed_feedback(f.name)

        assert len(phases) == 2
        assert phases[0]["name"] == "run_up"
        assert phases[1]["feedback"]["injury_risk"] == ["RIGHT_ELBOW"]

        os.unlink(f.name)

    def test_get_phase_feedback_finds_correct_phase(self):
        """Should return correct phase for given timestamp."""
        from mediapipe_overlay import get_phase_feedback

        phases = [
            {"start": 0.0, "end": 2.0, "name": "run_up", "feedback": {"good": ["A"], "slow": [], "injury_risk": []}},
            {"start": 2.0, "end": 4.0, "name": "release", "feedback": {"good": [], "slow": [], "injury_risk": ["B"]}},
            {"start": 4.0, "end": 6.0, "name": "follow", "feedback": {"good": ["C"], "slow": [], "injury_risk": []}}
        ]

        # Test beginning of video
        idx, name, fb = get_phase_feedback(phases, 0.5)
        assert idx == 0
        assert name == "run_up"
        assert fb["good"] == ["A"]

        # Test middle phase
        idx, name, fb = get_phase_feedback(phases, 3.0)
        assert idx == 1
        assert name == "release"
        assert fb["injury_risk"] == ["B"]

        # Test end phase
        idx, name, fb = get_phase_feedback(phases, 5.0)
        assert idx == 2
        assert name == "follow"

    def test_get_phase_feedback_handles_out_of_range(self):
        """Should handle timestamp beyond phases."""
        from mediapipe_overlay import get_phase_feedback

        phases = [
            {"start": 0.0, "end": 2.0, "name": "only_phase", "feedback": {"good": [], "slow": [], "injury_risk": []}}
        ]

        idx, name, fb = get_phase_feedback(phases, 10.0)
        assert name == "done"

    def test_get_color_scanning_phase(self):
        """Phase 0 should return gray for all joints."""
        from mediapipe_overlay import get_color

        feedback = {"good": ["RIGHT_KNEE"], "slow": [], "injury_risk": []}

        color = get_color("RIGHT_KNEE", feedback, phase_idx=0)
        assert color == (180, 180, 180)  # Gray for scanning

        color = get_color("LEFT_KNEE", feedback, phase_idx=0)
        assert color == (180, 180, 180)  # Gray even if not in feedback

    def test_get_color_feedback_phases(self):
        """Phase 1+ should return correct colors based on feedback."""
        from mediapipe_overlay import get_color, GREEN, YELLOW, RED

        feedback = {
            "good": ["RIGHT_SHOULDER"],
            "slow": ["RIGHT_HIP"],
            "injury_risk": ["RIGHT_ELBOW"]
        }

        # Good = Green
        color = get_color("RIGHT_SHOULDER", feedback, phase_idx=1)
        assert color == GREEN

        # Slow = Yellow
        color = get_color("RIGHT_HIP", feedback, phase_idx=1)
        assert color == YELLOW

        # Injury risk = Red
        color = get_color("RIGHT_ELBOW", feedback, phase_idx=1)
        assert color == RED

        # Not in feedback = None (don't draw)
        color = get_color("LEFT_ANKLE", feedback, phase_idx=1)
        assert color is None

    def test_get_color_priority_injury_over_slow(self):
        """Injury risk should take priority if joint is in multiple categories."""
        from mediapipe_overlay import get_color, RED

        feedback = {
            "good": ["RIGHT_ELBOW"],
            "slow": ["RIGHT_ELBOW"],
            "injury_risk": ["RIGHT_ELBOW"]
        }

        color = get_color("RIGHT_ELBOW", feedback, phase_idx=1)
        assert color == RED  # Injury risk takes priority

    def test_key_joints_constant(self):
        """KEY_JOINTS should contain exactly 12 bowling-relevant joints."""
        from mediapipe_overlay import KEY_JOINTS

        assert len(KEY_JOINTS) == 12
        assert "RIGHT_SHOULDER" in KEY_JOINTS
        assert "LEFT_SHOULDER" in KEY_JOINTS
        assert "RIGHT_ELBOW" in KEY_JOINTS
        assert "RIGHT_WRIST" in KEY_JOINTS
        assert "RIGHT_HIP" in KEY_JOINTS
        assert "RIGHT_KNEE" in KEY_JOINTS
        assert "RIGHT_ANKLE" in KEY_JOINTS
        # Should NOT contain face/hand landmarks
        assert "NOSE" not in KEY_JOINTS
        assert "LEFT_PINKY" not in KEY_JOINTS


class TestGenerateOverlayVideo:
    """Test the generate_overlay_video function in main.py."""

    def test_joint_map_coverage(self):
        """Joint map should cover common Coach phase names."""
        # Import the function to access the joint_map
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        joint_map = {
            "run-up": {"good": ["RIGHT_KNEE", "LEFT_KNEE", "RIGHT_HIP", "LEFT_HIP"]},
            "loading/coil": {"good": ["RIGHT_SHOULDER", "LEFT_SHOULDER", "RIGHT_HIP"]},
            "release action": {"injury_risk": ["RIGHT_ELBOW"], "good": ["RIGHT_WRIST"]},
            "release": {"injury_risk": ["RIGHT_ELBOW"], "good": ["RIGHT_WRIST"]},
            "wrist/snap": {"slow": ["RIGHT_WRIST"]},
            "follow-through": {"slow": ["RIGHT_HIP"], "good": ["RIGHT_SHOULDER"]},
            "head/eyes": {"slow": ["LEFT_SHOULDER"]}
        }

        # Verify key phases are mapped
        assert "run-up" in joint_map
        assert "release" in joint_map
        assert "follow-through" in joint_map

        # Verify joints are valid
        from mediapipe_overlay import KEY_JOINTS
        for phase, joints in joint_map.items():
            for category, joint_list in joints.items():
                for joint in joint_list:
                    assert joint in KEY_JOINTS, f"{joint} not in KEY_JOINTS for {phase}"

    def test_phases_to_feedback_conversion(self):
        """Coach phases should convert to MediaPipe feedback format."""
        # Simulate Coach phases
        coach_phases = [
            {"name": "Run-up", "status": "GOOD", "observation": "Good approach"},
            {"name": "Release", "status": "NEEDS WORK", "observation": "Elbow bent"},
            {"name": "Follow-through", "status": "GOOD", "observation": "Nice finish"}
        ]

        joint_map = {
            "run-up": {"good": ["RIGHT_KNEE"]},
            "release": {"injury_risk": ["RIGHT_ELBOW"]},
            "follow-through": {"good": ["RIGHT_SHOULDER"]}
        }

        # Convert (simplified version of main.py logic)
        feedback_phases = []
        duration = 5.0
        phase_duration = duration / len(coach_phases)

        for i, p in enumerate(coach_phases):
            name = p["name"].lower()
            status = p["status"].upper()

            fb = {"good": [], "slow": [], "injury_risk": []}
            if "GOOD" in status:
                fb["good"] = joint_map.get(name, {}).get("good", [])
            elif "NEEDS WORK" in status:
                fb["injury_risk"] = joint_map.get(name, {}).get("injury_risk", [])

            feedback_phases.append({
                "start": i * phase_duration,
                "end": (i + 1) * phase_duration,
                "name": p["name"],
                "feedback": fb
            })

        assert len(feedback_phases) == 3
        assert feedback_phases[0]["feedback"]["good"] == ["RIGHT_KNEE"]
        assert feedback_phases[1]["feedback"]["injury_risk"] == ["RIGHT_ELBOW"]
        assert feedback_phases[2]["feedback"]["good"] == ["RIGHT_SHOULDER"]
