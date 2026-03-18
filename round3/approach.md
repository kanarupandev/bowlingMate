# Speed Measurement — Simplest Approach

**Hit the stumps, get your speed.**

## Setup

1. Set up stumps at regulation distance (bowling crease to stumps = 18.9m)
2. Record with iPhone slo-mo (120fps or 240fps)
3. Bowl at the stumps

## Measurement

Only when the ball hits the stumps:

1. Open speed tool, pick the video
2. Scrub to the **release frame** — ball leaves the hand. Press R.
3. Scrub to the **impact frame** — ball hits the stumps. Press G.
4. Gate = "Bowling Crease to Striker Stumps (18.90m)" (default). Calculate.

Miss the stumps? No speed. Rewards accuracy.

## Why This Works

- **Stump impact is unmistakable** — stumps fly, ball deflects. Can't miss the frame.
- **Known distance** — 18.9m, regulation. No calibration needed.
- **Deterministic** — same video, same frames, same speed. Every time.
- **No AI needed** — human eyes pick two frames. Simple division.
- **Motivates accuracy** — only clean hits get measured.

## Accuracy (18.9m gate)

| FPS | 80 kph | 100 kph | 120 kph |
|-----|--------|---------|---------|
| 120 | ±2.5 kph | ±4 kph | ±6 kph |
| 240 | ±1.2 kph | ±2 kph | ±3 kph |

120fps is good enough for club pace. 240fps nails it.

## Alternatives

- **Wall** (10m) — bowl softball into a wall. Ball stops dead. Clear impact frame.
- **Net** — net deforms on impact. Works but less precise than stumps/wall.
- **Custom distance** — any known gate works. Longer = more accurate.

## What You Need

- iPhone (any model with slo-mo)
- Stumps at 18.9m
- The speed tool
- That's it
