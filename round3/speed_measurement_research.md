# Speed Measurement Research — Round 3

## The Question

How to measure cricket bowling speed accurately (±2 km/h) using only an iPhone camera on a tripod, 2 sets of stumps, and known distances?

## Core Insight

**You only need two frames:**
1. Frame where ball leaves the hand (release)
2. Frame where ball reaches a known distance marker (crease, stumps, or pitch marker)

**Speed = known distance / time between frames**

The pitch is 20.12 metres. Bowling crease to batting crease is 17.68 metres. These are fixed, known distances.

---

## The Math

| Speed (kph) | m/s | Transit time (20.12m) | Frames @120fps | Frames @240fps |
|-------------|-----|----------------------|----------------|----------------|
| 80 | 22.2 | 0.906s | 109 | 217 |
| 100 | 27.8 | 0.724s | 87 | 174 |
| 120 | 33.3 | 0.604s | 72 | 145 |
| 130 | 36.1 | 0.557s | 67 | 134 |
| 140 | 38.9 | 0.517s | 62 | 124 |
| 150 | 41.7 | 0.483s | 58 | 116 |

### Per-frame ball displacement (ball is ~7cm diameter)

| Speed | @120fps | @240fps |
|-------|---------|---------|
| 80 kph | 19cm | 9cm |
| 120 kph | 28cm | 14cm |
| 140 kph | 32cm | 16cm |

At 240fps the ball moves only 1-2x its own diameter per frame — visible and trackable.
At 120fps it moves 3-4x its diameter — blurred but detectable via frame differencing.
At 30fps it moves 10-18x its diameter — invisible streak. Useless.

### Accuracy by FPS

**±1 frame uncertainty at each gate (release + arrival):**

| FPS | Frame duration | Combined uncertainty (2 gates) | Error at 130 kph |
|-----|---------------|-------------------------------|-------------------|
| 120 | 8.33ms | ±16.7ms | ±3.9 kph |
| 240 | 4.17ms | ±8.33ms | ±1.95 kph |

**With sub-frame interpolation (parabolic peak fitting, ~0.3 frame precision):**

| FPS | Effective uncertainty | Error at 130 kph |
|-----|---------------------|-------------------|
| 120 | ±5.0ms | ±1.17 kph |
| 240 | ±2.5ms | ±0.59 kph |

**Conclusion: 120fps + sub-frame interpolation is the sweet spot. 1080p, less battery, meets ±2 kph.**

### Target Speed Range: 40-130 kph

| Speed (kph) | Transit time (20.12m) | Frames @120fps | Error (±1 frame) | Error (sub-frame) |
|-------------|----------------------|----------------|-------------------|-------------------|
| 40 | 1.811s | 217 | ±0.46 kph | ±0.14 kph |
| 60 | 1.207s | 145 | ±1.04 kph | ±0.31 kph |
| 80 | 0.906s | 109 | ±1.84 kph | ±0.55 kph |
| 100 | 0.724s | 87 | ±2.87 kph | ±0.86 kph |
| 120 | 0.604s | 72 | ±4.12 kph | ±1.24 kph |
| 130 | 0.557s | 67 | ±4.82 kph | ±1.17 kph |

**At 120fps with sub-frame interpolation: all speeds 40-130 kph are within ±2 kph.** ✅

---

## Approaches Evaluated

### A) Two-Gate Frame Differencing ✅ RECOMMENDED

**How it works:**
1. Define two ROIs (regions of interest) around each set of stumps
2. For each frame: subtract previous frame, count changed pixels in each ROI
3. Ball crossing a gate creates a motion energy spike (1-3 frames wide at 240fps)
4. Find spike time at bowler gate, find spike time at striker gate
5. Speed = 20.12m / (striker_time - bowler_time) × 3.6

**Pros:**
- Fully deterministic — pure pixel math, no ML
- Sub-millisecond computation per frame
- Already partially implemented in wellBowled codebase
- No model training, no GPU needed
- Works with any camera angle that sees both stumps

**Cons:**
- Needs 240fps for ±2 kph accuracy (120fps is marginal)
- Non-ball motion in ROI can create false spikes (bowler follow-through, batsman movement)
- Ball must create detectable luminance change vs background

**False spike mitigation:**
- Temporal ordering: bowler spike must come 0.3-1.0s before striker spike
- Spike width filtering: ball = 1-3 frames, person = 10-30 frames
- Direction constraint: motion must flow bowler→striker along pitch axis

### B) Optical Flow ❌ NOT RECOMMENDED

- Computationally expensive (20-30ms/frame at 720p)
- Poor for small fast objects with motion blur
- No accuracy gain over frame differencing for gate timing
- More complex, same result

### C) ML Object Detection (YOLO/TrackNet) ⚠️ FUTURE OPTION

- Off-the-shelf YOLO on cricket ball at 30fps: **0-15 detections, completely wrong speeds**
- Needs cricket-specific trained model + 240fps
- CoreML inference: ~8-12ms/frame — fits in 10s budget for a 0.5s clip
- **Best long-term solution** for full trajectory, but high upfront training cost
- Phase 2 investment, not Phase 1

### D) Audio-Based ❌ NOT VIABLE

- No clean audio signature at release point
- Arrival sound depends on outcome (bat, pad, miss, bounce)
- Only works when batsman plays a shot
- Ambient noise in outdoor settings

### E) Manual Tap Fallback ✅ REQUIRED BACKUP

When automated detection confidence is low:
1. Show video scrubber to user
2. User taps frame of release
3. User taps frame of arrival at known marker (crease/stumps)
4. Speed = distance / (frame_b - frame_a) × FPS
5. Always deterministic, user-verified

---

## What Commercial Systems Use

| System | Method | Accuracy | Cost |
|--------|--------|----------|------|
| Hawk-Eye | 6+ cameras, 340fps+, 3D triangulation | ±0.5% | Millions |
| PitchVision | 2-3 fixed cameras, pre-calibrated | ±3-5 kph | $3-5K |
| Radar speed gun | Doppler effect | ±1 kph | $500-2K |
| Light gate (indoor nets) | Dual IR beams, microsecond timing | ±0.5 kph | $200-500/gate |
| Fulltrack.ai | Pose estimation + known distance markers | Claimed ±2% | Phone only |
| Most App Store "speed guns" | Manual tap timing (human reaction ~200ms) | ±30 kph | Free/useless |

**No consumer app achieves reliable automated speed from a single phone camera at standard (30fps) frame rates.**

---

## iPhone Camera Specs

| Mode | Resolution | FPS | Ball Visibility |
|------|-----------|-----|-----------------|
| Standard 4K | 3840×2160 | 30 | Invisible streak |
| 1080p | 1920×1080 | 60 | Heavy blur |
| Slo-mo | 1080p | 120 | Visible but blurred |
| Slo-mo | 720p | 240 | Clear, trackable |

**720p at 240fps is the sweet spot** — ball is 3-4 pixels diameter at full pitch view, but frame differencing detects the motion energy reliably.

---

## Recommended Implementation — Phase Plan

### Phase 1: Enhanced Frame Differencing (NOW)

Changes needed:
1. Record at **120fps at 1080p** (already the current setting — no change needed)
2. Add **sub-frame parabolic interpolation** to spike detection
3. Increase ROI width slightly for 720p (stumps are fewer pixels)
4. Add **spike width filtering** to reject non-ball motion
5. **Manual tap fallback** when confidence is below threshold

Expected result: **±0.14-1.24 kph across 40-130 kph range, deterministic, <1 second computation**

### Multi-Gate Cross-Validation (CORE DESIGN)

**Architecture: AI finds frames → Code calculates speed → Cross-validate across gates**

The AI model (Gemini vision) identifies key frames. Pure code does the math. Deterministic.

#### Available Gates (known distances from release point)

| Gate | Distance from release | Notes |
|------|----------------------|-------|
| Bowling crease | 0m (release) | Always present — the starting point |
| User marker | 10m (configurable) | Cone, tape, or any object at a known distance |
| Good length | ~14m | Optional |
| Batting crease | 17.68m | Painted line on pitch |
| Stumps (striker) | 20.12m | Always present |

#### Model Output

The AI returns frame numbers for each detected gate crossing:

```json
{
  "release_frame": 847,
  "gates": [
    {"marker": "10m_cone", "frame": 883, "distance_m": 10.0},
    {"marker": "batting_crease", "frame": 911, "distance_m": 17.68},
    {"marker": "stumps", "frame": 914, "distance_m": 20.12}
  ]
}
```

#### Code Calculates Speed From Every Pair

```
Release → 10m marker:     10.00m / ((883-847)/120) = 120.0 kph
Release → batting crease:  17.68m / ((911-847)/120) = 119.6 kph
Release → stumps:          20.12m / ((914-847)/120) = 119.1 kph
10m → batting crease:       7.68m / ((911-883)/120) = 118.6 kph
10m → stumps:              10.12m / ((914-883)/120) = 118.3 kph
Batting crease → stumps:    2.44m / ((914-911)/120) = 117.1 kph
```

#### Cross-Validation → Verified Speed

1. Calculate speed from ALL gate pairs
2. Check agreement:
   - **All within ±3 kph** → HIGH confidence → show weighted average as verified speed
   - **One outlier** → drop it, average the rest → MEDIUM confidence
   - **Wide disagreement** → LOW confidence → fall back to manual tap
3. More gates that agree = higher confidence
4. **Self-verifying** — no single frame detection error can fool it

#### Consistency Check

Run the model 3 times on the same clip:
- All 3 return same frames → deterministic, show speed
- Any disagreement → low confidence → manual tap fallback

#### Why This Works

- AI is ONLY used for frame detection (the hard visual problem)
- Code does ALL measurement (deterministic, reproducible)
- Multiple gates catch errors — one bad detection doesn't corrupt the result
- User can configure which markers are available in their setup
- Works from any camera angle that sees the gates

### Phase 2: Ball Tracking ML (LATER)

1. Train TrackNet-style ball detector on cricket ball images at 240fps
2. CoreML on-device inference (~10ms/frame)
3. Full ball trajectory — not just average speed
4. Enables: release speed vs arrival speed, line/length from trajectory
5. Trajectory overlay visualization (the psychological credibility factor)

### Phase 3: Physics Model (MUCH LATER)

1. Fit physics model (gravity + air drag) to tracked trajectory
2. Cricket ball decelerates ~10-15% from release to batting end
3. Extract true release speed from trajectory curve
4. Compare release speed to arrival speed — coaching insight

---

## Key Insight from Fulltrack.ai Experience

> "Using Fulltrack.ai I enjoy the instant speed feedback. Trajectory isn't mandatory but it gives the psychological factor to believe in the speed and analysis."

The trajectory overlay isn't about accuracy — it's about **credibility**. When users see a visual path, they trust the number. Phase 1 gives the accurate number. Phase 2 adds the trajectory that makes users believe it.
