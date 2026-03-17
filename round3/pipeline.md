# Round 3 — Speed Measurement Pipeline

## Design Principle

**On-device detects the delivery → extract 3s clip → AI finds the frames → code calculates speed**

Minimal cost. Minimal latency. Deterministic measurement.

---

## Pipeline

```
Full session recording (120fps 1080p, on-device)
        ↓
Step 1: On-device spike detection (0 cost, real-time)
        ↓
Step 2: Extract 3s clip [-2s before release, +1s after] (~18MB)
        ↓
Step 3: Send clip to Gemini → returns frame numbers
        ↓
Step 4: Code calculates speed from all gate pairs
        ↓
Step 5: Cross-validate → show verified speed (<10s total)
```

---

## Step 1: On-Device Spike Detection

Goal: Detect every delivery with zero false negatives, minimal false positives.

### Option A: Apple Watch (best)
- Wrist angular velocity during bowling: ~1000-1900 deg/s
- Walking / arm swings: ~200-350 deg/s
- Threshold: 450 deg/s
- Near zero false negatives for actual deliveries
- Already implemented in wellBowled (`DeliveryDetector`)

### Option B: Frame Differencing (no watch needed)
- Define ROI around bowling crease area
- Large motion burst = delivery event
- Fast arm motion is distinct from walking/standing
- Runs on-device in real-time at 120fps
- May produce occasional false positives (bowler practice swing, fielder movement) — acceptable since cost of a false positive is just one extra Gemini call

### Option C: Device Accelerometer (phone on tripod)
- Ball hitting pitch creates vibration detectable by phone accelerometer
- Supplementary signal, not primary

### False Positive vs False Negative Trade-off
- **False negative** (missed delivery) = user loses data → unacceptable
- **False positive** (extra clip sent) = one wasted Gemini call (~$0.01) → acceptable
- Set threshold conservatively: catch everything, tolerate a few extras

---

## Step 2: Extract 3-Second Clip

On spike detection:
- **2 seconds before** the spike: captures approach + release point
- **1 second after** the spike: captures ball reaching gates (stumps/crease/marker)

### Why 3 seconds is enough
- At 40 kph (slowest target): ball takes 1.81s to travel 20.12m → 1s after release captures it
- At 130 kph (fastest target): ball takes 0.56s → well within 1s window
- Release point is always within the 2s before the spike

### Clip specs
- 120fps × 3s = 360 frames
- 1080p HEVC ≈ 18MB per clip
- Bitstream passthrough extraction (no re-encode, instant, preserves quality)

---

## Step 3: Send Clip to Gemini → Get Frame Numbers

### What Gemini returns

```json
{
  "release_frame": 241,
  "confidence": 0.95,
  "gates": [
    {"marker": "10m_cone", "frame": 277, "distance_m": 10.0, "confidence": 0.90},
    {"marker": "batting_crease", "frame": 305, "distance_m": 17.68, "confidence": 0.88},
    {"marker": "stumps", "frame": 308, "distance_m": 20.12, "confidence": 0.92}
  ]
}
```

### Consistency guarantee
- Set temperature=0 for deterministic output
- Run model 3 times on same clip
- If 2/3 agree on frame numbers → use those frames
- If all disagree → low confidence → manual tap fallback

### Hybrid refinement (optional enhancement)
1. Gemini returns approximate frame (±3-5 frame window)
2. Classical CV (frame differencing) finds exact motion spike within that window
3. Best of both: AI narrows the search, code finds the precise frame

### Cost per delivery
- One Gemini call on a 3s 1080p clip
- ~360 frames ≈ small video payload
- Estimated cost: ~$0.01-0.03 per delivery
- vs sending full 10-minute session: ~$0.50-1.00

---

## Step 4: Code Calculates Speed

Pure math. No AI. Deterministic.

```
speed_kph = distance_m / ((arrival_frame - release_frame) / fps) × 3.6
```

### With sub-frame interpolation (parabolic peak fitting)
- Fit parabola to 3-5 frames around each spike
- Find sub-frame peak: ~0.3 frame precision
- Reduces error from ±4 kph to ±1.2 kph at 130 kph

---

## Step 5: Cross-Validate Across All Gates

Calculate speed from every gate pair:

```
Release → 10m marker:      10.00m / 0.300s = 120.0 kph
Release → batting crease:   17.68m / 0.533s = 119.4 kph
Release → stumps:           20.12m / 0.558s = 129.8 kph  ← outlier
10m → stumps:               10.12m / 0.258s = 141.1 kph  ← outlier (stumps frame wrong)
```

### Verification rules
1. Calculate speed from ALL available gate pairs
2. **All within ±3 kph** → HIGH confidence → weighted average = verified speed ✅
3. **One outlier** → drop it, average the rest → MEDIUM confidence ⚠️
4. **Wide disagreement** → LOW confidence → manual tap fallback ❌
5. More gates that agree = higher confidence score

### Confidence display
- HIGH: "120 kph" (solid, no qualifier)
- MEDIUM: "~120 kph" (tilde prefix)
- LOW: prompt user to tap release + arrival frames manually

---

## Manual Tap Fallback

When automated confidence is below threshold:

1. Show video scrubber with frame-by-frame control
2. User taps **frame of release** (ball leaves hand)
3. User taps **frame of arrival** at a known marker (crease/stumps/cone)
4. User selects which marker (dropdown: "10m marker", "batting crease", "stumps")
5. Code calculates: speed = distance / time
6. Always deterministic. Always accurate. User-verified.

---

## Setup Requirements

### Minimum (always available)
- iPhone on tripod
- 2 sets of stumps (20.12m apart)
- Recording at 120fps 1080p

### Better (user adds a marker)
- Above + a cone/tape at 10m from bowling crease
- Gives an additional gate for cross-validation
- Ball hasn't bounced yet at 10m → cleaner detection

### Best (full setup)
- Above + batting crease line clearly visible
- 3 gates after release: 10m, batting crease (17.68m), stumps (20.12m)
- Maximum cross-validation

---

## Latency Budget (target: <10 seconds)

| Step | Time |
|------|------|
| Spike detection | Real-time (0s) |
| Clip extraction | <1s (bitstream passthrough) |
| Upload 18MB clip | ~2-3s (4G/5G) |
| Gemini processing | ~3-5s |
| Speed calculation | <0.01s |
| **Total** | **~6-9 seconds** ✅ |

---

## Cost Per Session

| Item | Cost |
|------|------|
| On-device spike detection | $0 |
| Clip extraction | $0 |
| Gemini call per delivery | ~$0.01-0.03 |
| 30 deliveries per session | ~$0.30-0.90 |
| **Total per session** | **<$1.00** |

---

## Summary

| Requirement | Solution | Status |
|-------------|----------|--------|
| Speed within 10 seconds | Pipeline: detect → clip → Gemini → code | ✅ |
| Accurate to ±2 kph | 120fps + sub-frame interpolation + multi-gate | ✅ |
| Consistent (same video = same result) | Code does math, AI only finds frames, temp=0 + 3-run vote | ✅ |
| Manual fallback | Frame scrubber + tap release/arrival | ✅ |
| Cost effective | ~$0.03 per delivery, <$1 per session | ✅ |
| No extra hardware | iPhone + tripod + stumps | ✅ |
| Speed range 40-130 kph | All within ±2 kph at 120fps with interpolation | ✅ |
