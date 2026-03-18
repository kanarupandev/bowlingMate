# Speed Measurement — Simplest Approach

**Hit the stumps, get your speed.**

## Setup

1. Set up stumps at regulation distance (bowling crease to stumps = 18.9m)
2. Record with iPhone slo-mo at **240fps** (locked decision — see Decisions below)
3. Bowl at the stumps (tennis ball is fine)

## Measurement

Only when the ball hits the stumps:

1. Open speed tool, pick the video
2. Find the delivery, mark the **release frame** (R) — ball leaves the hand
3. Tool auto-jumps ~0.6s ahead, shows thumbnail strip of frames
4. Click the **impact frame** — ball hits stumps. Speed calculates instantly.

Miss the stumps? No speed. Rewards accuracy.

## UX Design (approved)

**Two-phase frame picking:**

### Phase 1 — Find Release (coarse)
- Full video scrubber with slider + single frame view
- Arrow keys: ←/→ ±1 frame, Shift+arrows ±10 frames
- Press R to mark release → Phase 2 appears

### Phase 2 — Find Stumps Hit (fine)
- Auto-jumps 0.6s ahead (configurable)
- Horizontal thumbnail strip — N frames side by side (batch size 2-8, default 5)
- Navigation: ◀◀ shift by batch, ◀/▶ shift by 1 frame, ▶▶ shift by batch
- Click any thumbnail → selected as impact frame, speed calculates instantly
- No separate "Calculate" button needed

### Settings (always visible)
- Distance: editable, default 18.90m
- Batch size: 2-8, default 5
- Jump offset: default 0.6s

### Keyboard
- ←/→ ±1 frame, Shift ±10
- R mark release, C clear all, Space play/pause

## Why This Works

- **Stump impact is unmistakable** — stumps fly, ball deflects. Can't miss the frame.
- **Known distance** — 18.9m, regulation. No calibration needed.
- **Deterministic** — same video, same frames, same speed. Every time.
- **No AI needed** — human eyes pick two frames. Simple division.
- **Motivates accuracy** — only clean hits get measured.

## Accuracy (18.9m gate, 240fps)

| Speed | Frame diff | Error (±1 frame) |
|-------|-----------|-------------------|
| 80 kph | ~41 frames | ±1.2 kph |
| 100 kph | ~33 frames | ±2 kph |
| 120 kph | ~27 frames | ±3 kph |
| 140 kph | ~23 frames | ±3.5 kph |

## Alternatives (not primary, available via distance field)

- **Wall** — bowl softball into a wall at known distance. Ball stops dead.
- **Net** — net deforms on impact. Works but less precise than stumps/wall.
- **Custom distance** — any known gate. Longer = more accurate.

## What You Need

- iPhone (any model with slo-mo 240fps)
- Stumps at 18.9m
- Tennis ball (or any ball)
- The speed tool
- That's it

---

# Decisions Log

## D1: Recording FPS — 240fps (locked)

**Date:** 2026-03-18

**Options considered:**
1. **120fps** — available on all iPhones, less storage, but ±1 frame = 8.3ms uncertainty
2. **240fps** — available on iPhone 8+, more storage, ±1 frame = 4.2ms uncertainty
3. **Frame interpolation (RIFE/FILM)** — generate synthetic frames between real ones to virtually double fps

**Decision:** Option 2 — 240fps native recording

**Rationale:**
- 240fps halves the timing error mechanically — real temporal data, not guesses
- Frame interpolation (Option 3) rejected: synthetic frames are interpolated guesses, not real data. The ball position in generated frames could be off. It's like drawing extra marks on a ruler with a pencil — looks precise, isn't.
- 120fps (Option 1) gives ±2.5-6 kph error at club pace. Acceptable but 240fps is free improvement.
- 240fps supported on iPhone 8 and newer — covers all realistic users
- Storage cost is negligible for 3-5 second clips

## D2: Impact detection — Manual frame picking (for now)

**Date:** 2026-03-18

**Options considered:**
1. **Manual frame picking** — user scrubs to impact frame
2. **Audio spike detection** — detect the crack of ball hitting stumps
3. **ML classification** — on-device model classifies "stumps intact" vs "stumps hit" per frame
4. **Frame differencing on stump ROI** — pixel change detection in calibrated stump region

**Decision:** Option 1 — Manual picking (current phase)

**Rationale:**
- Need ground truth data first before automating
- Manual is 100% accurate — human eyes easily spot stumps flying
- Audio (Option 2) rejected for primary: outdoor noise, phone 20m away, sound delay ~60ms, tennis ball on plastic stumps is quiet
- ML (Option 3) and frame diff (Option 4) are future automation candidates once we validate the speed measurement pipeline end-to-end
- Two-phase thumbnail UX makes manual picking fast enough (~5 seconds)

## D3: Air resistance / bounce — Accept "delivery speed" not "release speed"

**Date:** 2026-03-18

**Trade-off analysis:**
- Radar guns measure speed at release point
- Our measurement is average speed over 18.9m (release to stumps)
- Ball loses 3-8 kph to air drag over the distance
- Ball loses 8-15 kph on pitch bounce (hard ball) or 5-8 kph (tennis ball)
- Our reading is 10-20 kph below radar for hard ball, closer for tennis ball

**Decision:** Accept the difference. Our number is "delivery speed" — consistent, comparable, useful. Not the same as a speed gun but valid for:
- Comparing yourself session to session
- Relative improvement tracking
- "Am I bowling 80 or 110" level accuracy
- Tennis ball reduces the gap (less speed lost on bounce)

## D4: Gate type — Stumps hit only (primary)

**Date:** 2026-03-18

**Decision:** Only calculate speed when stumps are rattled. Miss = no speed.

**Rationale:**
- Stump impact is the sharpest visual signal — unmistakable frame
- Rewards bowling accuracy alongside speed
- Distance is known and fixed (crease to stumps)
- Wall/net/custom distance available as alternatives via distance field
