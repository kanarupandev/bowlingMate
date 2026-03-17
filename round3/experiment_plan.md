# Round 3 — Experiment Plan

## Goal

Validate speed measurement accuracy using real bowling videos with known speeds.
No assumptions. Real data. Decide tech stack based on results.

---

## Experiment Setup

### What you need
- iPhone 15 on tripod (side-on or behind-arm)
- 2 sets of stumps at a real pitch (20.12m apart)
- A speed gun or Fulltrack.ai as ground truth (known speed)
- A marker at 10m (cone or tape)
- Record the same delivery with iPhone AND get speed gun reading

### Recording plan
- Record at **120fps** (iPhone slo-mo, 1080p)
- Also record a few at **240fps** (720p) for comparison
- Record at **60fps** and **30fps** too — see where it breaks
- Aim for 10-20 deliveries across speed range:
  - 3-4 deliveries at ~40-60 kph (slow/spin)
  - 3-4 deliveries at ~70-90 kph (medium)
  - 3-4 deliveries at ~100-120 kph (fast)
  - 3-4 deliveries at ~120-130 kph (express, if available)

### Data to capture per delivery
- Video file (iPhone)
- Ground truth speed (speed gun / Fulltrack reading)
- FPS used
- Camera position (side-on / behind-arm / angle)
- Conditions (daylight, ball colour, background)

---

## Tech Stack for Experiment

### Option A: Python + OpenCV (fastest to prototype)

```
python3 + opencv-python + numpy + matplotlib
```

**Why:** Iterate fast. Read video frames, compute frame diffs, find spikes, calculate speed. Plot results. No iOS build cycle.

**Script flow:**
1. Load video (cv2.VideoCapture)
2. Define ROIs for each gate (stumps, crease, marker)
3. Frame-by-frame: compute |frame[n] - frame[n-1]| in each ROI
4. Find motion energy spikes per ROI
5. Sub-frame interpolation on spikes
6. Calculate speed from all gate pairs
7. Cross-validate
8. Compare to ground truth
9. Plot accuracy chart

### Option B: Python + Gemini API

```
python3 + google-genai SDK
```

**Script flow:**
1. Extract 3s clip around delivery
2. Send to Gemini: "find release frame and gate crossing frames"
3. Get frame numbers back
4. Calculate speed (same math)
5. Run 3 times → check consistency
6. Compare to ground truth

### Option C: Swift Playground / on-device

Skip this for experimentation. Too slow to iterate. Use Python first, port to iOS after validation.

### Recommended: Run BOTH A and B on the same videos

Compare:
- Classical CV (frame differencing) accuracy vs ground truth
- Gemini frame detection accuracy vs ground truth
- Gemini consistency (same video, 3 runs)
- Which approach is more reliable at each speed range

---

## Experiment Script (Python)

### Directory structure

```
round3/
├── experiment_plan.md      (this file)
├── context.md
├── pipeline.md
├── speed_measurement_research.md
├── experiments/
│   ├── videos/             (raw iPhone videos)
│   ├── ground_truth.csv    (delivery_id, speed_kph, fps, camera_angle)
│   ├── frame_diff.py       (Option A: classical CV)
│   ├── gemini_detect.py    (Option B: Gemini frame detection)
│   ├── compare.py          (plot results, accuracy analysis)
│   └── results/            (output charts, logs)
```

### ground_truth.csv format

```csv
delivery_id,video_file,speed_kph,fps,camera_angle,ball_colour,notes
d001,videos/d001_120fps.mov,95,120,side_on,red,sunny
d002,videos/d002_120fps.mov,112,120,side_on,red,sunny
d003,videos/d003_240fps.mov,95,240,side_on,red,sunny (same delivery as d001 different fps)
d004,videos/d004_60fps.mov,95,60,side_on,red,sunny (same delivery at 60fps)
```

### frame_diff.py — what it does

1. Read video frame by frame
2. Convert to grayscale
3. User defines ROIs (first run: click on video to mark gate positions)
4. For each frame: sum of absolute pixel differences in each ROI
5. Plot motion energy over time for each ROI
6. Find spikes (threshold = 3× noise floor)
7. Sub-frame interpolation (parabolic fit around peak)
8. Calculate speed from each gate pair
9. Output: estimated speed, confidence, comparison to ground truth

### gemini_detect.py — what it does

1. Extract 3s clip around delivery
2. Send to Gemini with prompt:
   "Find the exact frame number where:
   (a) ball leaves the bowler's hand
   (b) ball crosses each visible marker/crease/stumps
   Return frame numbers only."
3. Run 3 times, check consistency
4. Calculate speed from returned frames
5. Output: estimated speed, frame variance, comparison to ground truth

### compare.py — what it does

1. Load ground truth + frame_diff results + gemini results
2. Plot: estimated vs actual speed (scatter plot)
3. Plot: error distribution (histogram)
4. Plot: error by speed range (are slow balls harder than fast?)
5. Plot: error by FPS (120 vs 240 vs 60)
6. Summary table: mean error, max error, consistency score

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Mean absolute error | ≤2 kph |
| Max error (95th percentile) | ≤4 kph |
| Consistency (same video, 3 runs) | Identical result (frame diff) / ±1 frame (Gemini) |
| Works at 120fps | Yes |
| Works at 60fps | Bonus (not required) |
| Speed range covered | 40-130 kph |
| Processing time per delivery | <10 seconds |

---

## Decision Matrix (after experiments)

Based on results, pick the approach:

| If... | Then... |
|-------|---------|
| Frame diff alone meets ±2 kph at 120fps | Use frame diff only. No Gemini needed for speed. Cheapest. |
| Frame diff needs Gemini to find release frame | Hybrid: Gemini finds approximate frame, CV refines. |
| Frame diff fails but Gemini is consistent | Use Gemini for frame detection + code for math. |
| Both fail at 120fps but work at 240fps | Record at 240fps (accept 720p trade-off). |
| Neither works reliably | Manual tap fallback as primary. Rethink approach. |

---

## Next Steps

1. Record 10-20 deliveries with known speeds (iPhone + speed gun/Fulltrack)
2. Transfer videos to Mac
3. Run frame_diff.py → get results
4. Run gemini_detect.py → get results
5. Run compare.py → decide tech stack
6. Build the winner into the app
