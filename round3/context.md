# Round 3 — Context & Direction

## Journey So Far

### Round 1: bowlingMate (Gemini 3 Hackathon)
- Video-first approach: Record → Scout detects → Clip → Expert analyzes 6 phases
- FastAPI backend, Cloud Run, MediaPipe skeleton overlay
- Works well but analysis takes ~30s — too slow for real-time feel
- No audio, no live coaching, text/video only

### Round 2: wellBowled.ai (Gemini Live API experiment)
- Audio-first approach: Live AI "mate" talks to you during bowling
- Gemini Live API native audio — real-time conversation
- Delivery detection via Apple Watch wrist motion
- DNA matching to famous bowlers, stump calibration, speed estimation
- **Finding: Audio live agent is NOT up to mark to be truly useful (as of Feb 2026)**
  - Latency too high for real-time coaching
  - Audio feedback hard to absorb while bowling
  - Setup friction (tripod, calibration, watch) too high for casual sessions
  - Gemini Live API still preview/experimental

### Round 3: Frugal approach
- Stick to what works. Don't over-engineer.
- Key insight from using **Fulltrack.ai**: instant speed feedback is the killer feature
- Trajectory overlay isn't mandatory BUT it gives the **psychological factor** — users believe in the speed and analysis more when they see a visual trajectory

## What's Pending

1. **Speed within 10 seconds, accurate to ±2 km/h**
   - This is the #1 priority — instant gratification after each delivery
   - Fulltrack.ai does this well — we need to match or beat it
   - Camera-based speed estimation using stump-to-stump transit time
   - Must show speed FAST — before user walks back to their mark

2. **Consistent measurement — deterministic, not probabilistic**
   - Same video, run 100 times, must get the same speed result every time
   - No LLM/vision model in the speed measurement loop — they're non-deterministic
   - Must use classical CV (frame differencing, optical flow, or object tracking)
   - Gemini can assist with calibration/setup but NOT with the actual measurement

3. **Manual fallback when confidence is low**
   - If automated speed detection confidence is below threshold (case by case)
   - Ask user to tap two frames:
     a. Frame of release
     b. Frame where ball meets a known distance marker (batting crease, stumps, or a user-placed marker at a known distance like middle of pitch)
   - Speed = known distance / (frame_b - frame_a) × FPS
   - This is always deterministic and user-verified

4. TBD

---

## bowlingMate vs wellBowled.ai — Comparison

### bowlingMate (Round 1)

**Architecture:** Video-first, post-delivery analysis
- FastAPI backend on Cloud Run
- Scout (Gemini Flash) detects deliveries in video chunks
- Clipper extracts 5s clips via bitstream passthrough (no re-encode)
- Expert (Gemini Pro) does 6-phase biomechanical analysis streamed via SSE
- MediaPipe skeleton overlay with color-coded joints (green/yellow/red)
- Interactive text chat with video playback control
- Streamlit web demo
- SQLite + GCS persistence
- 18 test files

**Strengths:**
- Proper backend with cloud deployment
- Clean Scout → Clipper → Expert pipeline
- MediaPipe skeleton gives visual credibility
- Works without any hardware (no watch, no tripod required for basic use)
- Protocol-based networking (testable)
- Web demo for sharing

**Weaknesses:**
- ~30s analysis wait per delivery — too slow
- No real-time feedback during bowling
- No speed measurement
- No audio/voice — all text
- No personality or engagement factor
- SQLite on Cloud Run is ephemeral (lost on restart)

### wellBowled.ai (Round 2)

**Architecture:** Audio-first, live AI companion
- Gemini Live API (native audio WebSocket) — real-time conversation
- Apple Watch delivery detection via wrist angular velocity
- 8 mate personas (Aussie/English/Tamil/Tanglish × Male/Female)
- Stump calibration via Gemini vision (single frame analysis)
- Speed estimation via frame differencing between stump gates
- Bowling DNA matching to 103 famous bowlers
- Quality dampener for realistic similarity scores
- Post-delivery deep analysis (Gemini Pro) fed back to live mate
- Challenge mode (mate sets targets)

**Strengths:**
- Live audio mate — genuinely novel UX
- Personality system makes it engaging
- DNA matching is fun and shareable
- Speed estimation exists (camera-based)
- Delivery detection works without manual intervention
- Real-time — mate reacts as you bowl

**Weaknesses:**
- Gemini Live API is preview/experimental — unreliable
- Audio feedback hard to absorb while bowling
- High setup friction: tripod + stump alignment + watch + calibration
- Speed estimation not validated for accuracy
- No backend — everything on-device + direct Gemini calls
- No persistence beyond the session
- No web demo
- Audio latency makes "real-time" feel laggy

### Verdict

| Feature | bowlingMate | wellBowled.ai | Round 3 Target |
|---------|-------------|---------------|----------------|
| Speed feedback | None | Estimated (unvalidated) | ±2 km/h in <10s |
| Analysis depth | 6-phase + skeleton | 6-phase + DNA | 6-phase + skeleton |
| Real-time feel | No (30s wait) | Yes (but laggy audio) | Yes (speed instant, analysis streams) |
| Setup friction | Low (just phone) | High (tripod+watch+calibrate) | Low |
| Audio coaching | None | Live mate (unreliable) | Optional layer |
| Consistency | Deterministic (classical CV) | Non-deterministic (LLM) | Deterministic speed, LLM for analysis |
| Backend | FastAPI + Cloud Run | None (on-device) | FastAPI + Cloud Run |
| Persistence | SQLite + GCS | None | Proper DB + GCS |
| Fun factor | Low | High (DNA, mate) | DNA + speed = engagement |

### Key Takeaway

bowlingMate has the better architecture. wellBowled has the better engagement ideas. Round 3 merges both: bowlingMate's pipeline + instant deterministic speed + DNA matching + optional audio mate (when the tech matures).
