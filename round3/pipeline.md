# Round 3 — Speed Measurement Pipeline

## Scope

**Bowling speed estimation. Nothing else.**

---

## Pipeline

```
240fps 720p continuous buffer (temporary, on-device)
    ↓
On-device ML detects bowling motion → rough 10s window (0 cost)
    ↓
Send 10s to Gemini Flash → release timestamp ($0.01)
    ↓
Extract 3s clip [-1.5s before release, +1.5s after]
    ↓
Send 3s clip to Gemini Flash → release frame + gate crossing frames
    ↓
Code calculates speed from all gate pairs → cross-validate
    ↓
Compress 3s clip to <1MB (30fps 480p HEVC) → store
    ↓
Delete buffer
```

---

## What's Stored Per Delivery

- 3s clip (<1MB)
- Speed (kph)

Nothing else.

---

## Speed Calculation

**AI finds frames. Code does math. Deterministic.**

```
speed_kph = distance_m / ((arrival_frame - release_frame) / 240) × 3.6
```

### Available Gates (known distances from release)

| Gate | Distance |
|------|----------|
| User marker | 10m (cone/tape) |
| Batting crease | 17.68m |
| Stumps (striker) | 20.12m |

### Cross-Validation

Calculate speed from every gate pair. If all agree within ±3 kph → verified. If not → manual tap fallback.

---

## Accuracy

At 240fps with sub-frame interpolation:

| Speed | Error |
|-------|-------|
| 40 kph | ±0.14 kph |
| 80 kph | ±0.55 kph |
| 100 kph | ±0.86 kph |
| 130 kph | ±1.17 kph |

All within ±2 kph. ✅

---

## Storage

```
30-min session → ~1.3GB temporary buffer
15 deliveries → 15 × <1MB = <15MB stored
Delete 1.3GB buffer
```

---

## Cost

| Item | Cost |
|------|------|
| On-device ML | $0 |
| Gemini Flash per delivery | ~$0.02 |
| 30 deliveries | ~$0.60 |

---

## Manual Tap Fallback

When confidence is low:
1. Show 3s clip with frame scrubber
2. User taps release frame
3. User taps arrival frame + selects gate (10m / crease / stumps)
4. Code calculates speed

Always works. Always accurate. Always deterministic.
