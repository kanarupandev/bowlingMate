# Round 3 — Experiment Plan

## Goal

Validate speed measurement accuracy using real bowling videos with known speeds.
No assumptions. Real data. Decide tech stack based on results.

---

## Experiment Setup

### Equipment
- iPhone 15 on tripod (side-on view of pitch)
- 2 sets of stumps at a real pitch (20.12m apart)
- Optional: marker at 10m (cone or tape) for extra gate
- Optional: visible batting crease line

### Ground Truth Method
**Manual frame counting** — no second phone or speed gun needed.
1. Record delivery at 120fps slo-mo (native iPhone camera)
2. Transfer to Mac
3. Open in QuickTime, step frame-by-frame (arrow keys)
4. Count: release frame → stumps frame
5. Ground truth speed = 20.12m / (frame_count / 120) × 3.6

This IS the speed gun. Your eyes + frame counting = absolute truth.

### Recording Instructions
1. **Settings → Camera → Record Slo-mo → 1080p HD at 120 fps**
2. Open Camera app → swipe to **Slo-Mo** mode
3. Position tripod side-on, both sets of stumps visible in frame
4. Hit record, bowl, stop
5. Trim clip to ~5s around delivery (optional, saves transfer time)

### Recording Plan
- Record at **120fps 1080p** (primary — sweet spot of quality + temporal resolution)
- Also record a few at **240fps 720p** for comparison
- Record a few at **60fps** to see where it breaks
- Aim for 10-20 deliveries across speed range:
  - 3-4 deliveries at ~40-60 kph (slow/spin)
  - 3-4 deliveries at ~70-90 kph (medium)
  - 3-4 deliveries at ~100-120 kph (fast)
  - 3-4 deliveries at ~120-130 kph (express, if available)

### Data to Capture Per Delivery
- Video file (AirDrop to Mac)
- Ground truth speed (manual frame count in QuickTime)
- Release frame number (from QuickTime)
- Arrival frame number (from QuickTime)
- FPS used
- Camera position (side-on / behind-arm / angle)
- Conditions (daylight, ball colour, background)

---

## Tech Stack for Experiment

### Option A: Python + OpenCV (classical CV — deterministic)

```
python3 + opencv-python + numpy + matplotlib
```

**How it measures speed:**
1. Define ROIs around each gate (stumps, crease, marker) — click on first frame
2. Frame-by-frame: compute |frame[n] - frame[n-1]| in each ROI
3. Ball crossing a gate creates a motion energy spike
4. Sub-frame interpolation (parabolic fit) on each spike
5. Speed = distance / time between spikes
6. Cross-validate across all gate pairs

**Strengths:** Fully deterministic. Same video = same result. No API cost. Sub-second computation.

### Option B: Python + Gemini API (AI frame detection)

```
python3 + google-genai SDK
```

**How it measures speed:**
1. Send 3s clip to Gemini
2. Prompt: "find exact frame where ball leaves hand + frame where ball crosses each gate"
3. Gemini returns frame numbers
4. Code calculates speed = distance / (frame_diff / fps) × 3.6
5. Run 3 times to check consistency (temperature=0)

**Strengths:** Can identify release frame visually (hard for classical CV). Handles complex scenes.

### Option C: Hybrid (best of both)

1. Gemini identifies approximate release frame (±3-5 frames)
2. Classical CV (frame differencing) finds exact spike within that window
3. Code calculates speed

**Strengths:** AI handles the hard visual problem, code handles precision. Deterministic final measurement.

### Run ALL THREE on the same videos. Compare. Pick the winner.

---

## Directory Structure

```
round3/
├── context.md                  # Journey: R1 → R2 → R3 + comparison
├── speed_measurement_research.md  # Technical research
├── pipeline.md                 # Full pipeline design
├── experiment_plan.md          # This file
└── experiments/
    ├── videos/                 # Raw iPhone slo-mo clips (AirDrop from phone)
    ├── ground_truth.csv        # Manual frame counts + calculated speeds
    ├── frame_diff.py           # Option A: classical CV
    ├── gemini_detect.py        # Option B: Gemini frame detection
    ├── compare.py              # Accuracy analysis + plots
    ├── requirements.txt        # Python dependencies
    └── results/                # Output charts, logs, JSON
```

---

## ground_truth.csv Format

```csv
delivery_id,video_file,speed_kph,fps,release_frame,arrival_frame,arrival_gate,camera_angle,ball_colour,notes
d001,videos/d001.mov,95.2,120,241,308,stumps,side_on,red,sunny
d002,videos/d002.mov,112.4,120,185,243,stumps,side_on,red,sunny
d003,videos/d003.mov,95.2,240,482,616,stumps,side_on,red,same delivery as d001 at 240fps
d004,videos/d004.mov,68.0,120,300,400,stumps,side_on,red,spin bowling
```

**How to fill this in:**
1. Open video in QuickTime
2. Use arrow keys to step frame by frame
3. Note the release frame (ball leaves hand)
4. Note the arrival frame (ball passes stumps/crease)
5. Calculate: speed = distance / ((arrival - release) / fps) × 3.6

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Mean absolute error | ≤2 kph |
| Max error (95th percentile) | ≤4 kph |
| Consistency (same video, 3 runs) | Identical (frame diff) / ±1 frame (Gemini) |
| Works at 120fps 1080p | Must |
| Works at 60fps | Bonus |
| Speed range | 40-130 kph |
| Processing time per delivery | <10 seconds |
| Cost per delivery | <$0.05 |

---

## Decision Matrix (after experiments)

| Result | Decision |
|--------|----------|
| Frame diff alone meets ±2 kph | Use frame diff only. Zero cost. Fastest. |
| Frame diff needs help finding release | Hybrid: Gemini finds release window, CV refines. |
| Frame diff fails, Gemini is consistent | Gemini for frames + code for math. |
| Both fail at 120fps, work at 240fps | Record at 240fps (accept 720p). |
| Neither works reliably | Manual tap fallback as primary. Rethink. |

---

## Workflow

```
1. Record deliveries (iPhone slo-mo 120fps)
     ↓
2. AirDrop to Mac → round3/experiments/videos/
     ↓
3. Manual frame count in QuickTime → fill ground_truth.csv
     ↓
4. pip install -r requirements.txt
     ↓
5. python frame_diff.py videos/d001.mov --fps 120 --ground-truth 95.2
     ↓
6. python gemini_detect.py videos/d001.mov --fps 120 --ground-truth 95.2
     ↓
7. python compare.py  (after all deliveries processed)
     ↓
8. Review results/ → pick tech stack → build into app
```

---

## After Experiments: Build Plan

Once tech stack is decided, port the winning approach to iOS:
- **If classical CV wins:** Pure on-device, CoreImage/Accelerate framework, zero API cost
- **If Gemini wins:** 3s clip → API call → code math, ~$0.03/delivery
- **If hybrid wins:** On-device CV + one Gemini call for release detection

Then integrate into bowlingMate's existing pipeline:
```
Scout detects delivery → extract 3s clip → measure speed → show in <10s
                                         → send to Expert for 6-phase analysis (parallel)
```

Speed is instant. Deep analysis streams in after.
