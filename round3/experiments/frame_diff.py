"""
Frame Differencing Speed Estimation — Experiment Script

Usage:
    python frame_diff.py videos/d001_120fps.mov --fps 120 --pitch-length 20.12

Interactive first run:
    - Click to mark gate ROIs on the first frame
    - Script saves ROI positions for reuse

Output:
    - Motion energy plot per gate
    - Detected spike frames
    - Estimated speed from each gate pair
    - Cross-validation result
"""

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import numpy as np


# ──────────────────────────────────────────────────────────
# ROI Selection
# ──────────────────────────────────────────────────────────

def select_rois(frame, roi_file="rois.json"):
    """Let user draw rectangle ROIs on the first frame. Save for reuse."""
    if Path(roi_file).exists():
        with open(roi_file) as f:
            saved = json.load(f)
        print(f"Loaded {len(saved)} ROIs from {roi_file}")
        return saved

    rois = {}
    gates = [
        ("release_zone", "Draw ROI around BOWLING CREASE (release area)"),
        ("marker_10m", "Draw ROI around 10m MARKER (or press ESC to skip)"),
        ("batting_crease", "Draw ROI around BATTING CREASE (or press ESC to skip)"),
        ("stumps", "Draw ROI around STRIKER STUMPS"),
    ]

    for name, prompt in gates:
        print(f"\n{prompt}")
        roi = cv2.selectROI(f"Select: {name}", frame, fromCenter=False, showCrosshair=True)
        cv2.destroyAllWindows()
        if roi[2] > 0 and roi[3] > 0:  # width and height > 0
            rois[name] = {"x": int(roi[0]), "y": int(roi[1]),
                          "w": int(roi[2]), "h": int(roi[3])}
            print(f"  ✓ {name}: {rois[name]}")
        else:
            print(f"  ✗ {name}: skipped")

    with open(roi_file, "w") as f:
        json.dump(rois, f, indent=2)
    print(f"\nSaved ROIs to {roi_file}")
    return rois


# ──────────────────────────────────────────────────────────
# Frame Differencing
# ──────────────────────────────────────────────────────────

def compute_motion_energy(video_path, rois, fps):
    """Compute per-frame motion energy in each ROI via absolute frame differencing."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"ERROR: Cannot open {video_path}")
        sys.exit(1)

    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Video: {video_path}")
    print(f"  FPS (metadata): {actual_fps}, FPS (override): {fps}")
    print(f"  Frames: {frame_count}")
    print(f"  Duration: {frame_count / fps:.2f}s")

    # Initialize energy arrays
    energy = {name: [] for name in rois}
    prev_gray = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)

            for name, roi in rois.items():
                region = diff[roi["y"]:roi["y"] + roi["h"],
                              roi["x"]:roi["x"] + roi["w"]]
                # Sum of pixel differences normalized by ROI area
                e = float(np.sum(region)) / (roi["w"] * roi["h"])
                energy[name].append(e)
        else:
            for name in rois:
                energy[name].append(0.0)

        prev_gray = gray
        frame_idx += 1

    cap.release()
    print(f"  Processed {frame_idx} frames")
    return energy


# ──────────────────────────────────────────────────────────
# Spike Detection with Sub-Frame Interpolation
# ──────────────────────────────────────────────────────────

def find_spike(energy_array, noise_multiplier=3.0):
    """Find the first significant motion spike. Returns sub-frame index."""
    arr = np.array(energy_array)
    if len(arr) < 5:
        return None, 0.0

    # Noise floor: median of all values
    noise_floor = np.median(arr)
    threshold = noise_floor * noise_multiplier

    # Find first frame above threshold
    candidates = np.where(arr > threshold)[0]
    if len(candidates) == 0:
        return None, 0.0

    # Find the peak within the first spike cluster
    first = candidates[0]
    cluster_end = first
    for i in range(1, len(candidates)):
        if candidates[i] - candidates[i - 1] <= 3:  # within 3 frames = same spike
            cluster_end = candidates[i]
        else:
            break

    peak_idx = first + np.argmax(arr[first:cluster_end + 1])

    # Sub-frame parabolic interpolation
    if 0 < peak_idx < len(arr) - 1:
        e_prev = arr[peak_idx - 1]
        e_peak = arr[peak_idx]
        e_next = arr[peak_idx + 1]
        denom = e_prev - 2 * e_peak + e_next
        if abs(denom) > 1e-6:
            offset = 0.5 * (e_prev - e_next) / denom
            sub_frame = peak_idx + offset
        else:
            sub_frame = float(peak_idx)
    else:
        sub_frame = float(peak_idx)

    return sub_frame, float(arr[peak_idx])


# ──────────────────────────────────────────────────────────
# Speed Calculation
# ──────────────────────────────────────────────────────────

# Known distances from bowling crease (release point)
GATE_DISTANCES = {
    "marker_10m": 10.0,
    "batting_crease": 17.68,
    "stumps": 20.12,
}


def calculate_speeds(spikes, fps):
    """Calculate speed from every pair of detected gates."""
    results = []

    release_frame = spikes.get("release_zone")
    if release_frame is None:
        print("  WARNING: No release spike detected!")
        return results

    # Speed from release to each gate
    for gate_name, distance in GATE_DISTANCES.items():
        gate_frame = spikes.get(gate_name)
        if gate_frame is None:
            continue

        frame_diff = gate_frame - release_frame
        if frame_diff <= 0:
            print(f"  WARNING: {gate_name} spike before release — skipping")
            continue

        time_s = frame_diff / fps
        speed_kph = (distance / time_s) * 3.6
        results.append({
            "from": "release",
            "to": gate_name,
            "distance_m": distance,
            "frames": frame_diff,
            "time_s": time_s,
            "speed_kph": speed_kph,
        })

    # Speed between gate pairs (cross-validation)
    gate_names = list(GATE_DISTANCES.keys())
    for i in range(len(gate_names)):
        for j in range(i + 1, len(gate_names)):
            g1, g2 = gate_names[i], gate_names[j]
            f1, f2 = spikes.get(g1), spikes.get(g2)
            if f1 is None or f2 is None:
                continue
            frame_diff = f2 - f1
            if frame_diff <= 0:
                continue
            distance = GATE_DISTANCES[g2] - GATE_DISTANCES[g1]
            time_s = frame_diff / fps
            speed_kph = (distance / time_s) * 3.6
            results.append({
                "from": g1,
                "to": g2,
                "distance_m": distance,
                "frames": frame_diff,
                "time_s": time_s,
                "speed_kph": speed_kph,
            })

    return results


def cross_validate(speed_results):
    """Cross-validate speeds from all gate pairs. Return verified speed + confidence."""
    if not speed_results:
        return None, "NO_DATA"

    speeds = [r["speed_kph"] for r in speed_results]
    mean_speed = np.mean(speeds)
    spread = max(speeds) - min(speeds)

    if spread <= 3.0:
        return round(mean_speed, 1), "HIGH"
    elif spread <= 6.0:
        # Drop the outlier, average the rest
        median = np.median(speeds)
        filtered = [s for s in speeds if abs(s - median) <= 3.0]
        if filtered:
            return round(np.mean(filtered), 1), "MEDIUM"
        return round(mean_speed, 1), "MEDIUM"
    else:
        return round(np.median(speeds), 1), "LOW"


# ──────────────────────────────────────────────────────────
# Plotting
# ──────────────────────────────────────────────────────────

def plot_motion_energy(energy, spikes, fps, output_path="results/motion_energy.png"):
    """Plot motion energy for each ROI with detected spikes."""
    fig, axes = plt.subplots(len(energy), 1, figsize=(14, 3 * len(energy)), sharex=True)
    if len(energy) == 1:
        axes = [axes]

    for ax, (name, values) in zip(axes, energy.items()):
        time_axis = np.arange(len(values)) / fps
        ax.plot(time_axis, values, linewidth=0.5, label=name)
        ax.set_ylabel("Motion Energy")
        ax.set_title(name)
        ax.legend()

        # Mark spike
        spike_frame = spikes.get(name)
        if spike_frame is not None:
            spike_time = spike_frame / fps
            ax.axvline(x=spike_time, color="red", linestyle="--", linewidth=1.5,
                       label=f"spike @ {spike_time:.3f}s (frame {spike_frame:.1f})")
            ax.legend()

    axes[-1].set_xlabel("Time (seconds)")
    plt.tight_layout()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150)
    print(f"\n  Plot saved: {output_path}")
    plt.close()


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Frame differencing speed estimation")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--fps", type=float, default=120, help="Recording FPS (default: 120)")
    parser.add_argument("--pitch-length", type=float, default=20.12, help="Pitch length in metres")
    parser.add_argument("--roi-file", default="rois.json", help="ROI positions file")
    parser.add_argument("--ground-truth", type=float, default=None, help="Known speed in kph")
    args = parser.parse_args()

    # Load first frame for ROI selection
    cap = cv2.VideoCapture(args.video)
    ret, first_frame = cap.read()
    cap.release()
    if not ret:
        print(f"ERROR: Cannot read {args.video}")
        sys.exit(1)

    # Select/load ROIs
    rois = select_rois(first_frame, args.roi_file)
    if not rois:
        print("ERROR: No ROIs defined")
        sys.exit(1)

    # Compute motion energy
    print("\nComputing motion energy...")
    energy = compute_motion_energy(args.video, rois, args.fps)

    # Find spikes
    print("\nDetecting spikes...")
    spikes = {}
    for name, values in energy.items():
        frame, peak = find_spike(values)
        if frame is not None:
            spikes[name] = frame
            print(f"  {name}: spike at frame {frame:.2f} (sub-frame), peak energy={peak:.1f}")
        else:
            print(f"  {name}: no spike detected")

    # Calculate speeds
    print("\nCalculating speeds...")
    speed_results = calculate_speeds(spikes, args.fps)
    for r in speed_results:
        print(f"  {r['from']} → {r['to']}: {r['distance_m']:.2f}m in {r['time_s']:.3f}s = {r['speed_kph']:.1f} kph")

    # Cross-validate
    verified_speed, confidence = cross_validate(speed_results)
    print(f"\n{'='*50}")
    print(f"  VERIFIED SPEED: {verified_speed} kph [{confidence} confidence]")
    if args.ground_truth:
        error = abs(verified_speed - args.ground_truth) if verified_speed else None
        print(f"  GROUND TRUTH:   {args.ground_truth} kph")
        print(f"  ERROR:          {error:.1f} kph" if error else "  ERROR: N/A")
    print(f"{'='*50}")

    # Plot
    video_name = Path(args.video).stem
    plot_motion_energy(energy, spikes, args.fps, f"results/{video_name}_energy.png")


if __name__ == "__main__":
    main()
