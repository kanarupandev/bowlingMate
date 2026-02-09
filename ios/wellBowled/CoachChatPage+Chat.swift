import SwiftUI
import AVKit

// MARK: - CoachChatPage Chat & Video Actions
extension CoachChatPage {

    // MARK: - Demo Chat

    func sendDemoMessage(_ text: String) {
        print("💬 [CoachPage] Demo message: \"\(text)\"")

        chatMessages.append(ChatMessage(text: text, isUser: true, videoAction: nil))

        let responses: [String: (String, VideoAction?)] = [
            "Focus on Release": (
                "Your release at 1.8s shows front arm dropping. Watch closely...",
                VideoAction(action: "focus", timestamp: 1.8)
            ),
            "Show Follow-Through": (
                "Here's your follow-through phase at 2.5s. Notice the balance...",
                VideoAction(action: "focus", timestamp: 2.5)
            ),
            "Pause & Explain": (
                "At this moment, your body alignment is off. Let me pause and show you...",
                VideoAction(action: "pause", timestamp: 1.5)
            )
        ]

        if let (reply, action) = responses[text] {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                self.chatMessages.append(ChatMessage(text: reply, isUser: false, videoAction: action))
                if let action = action {
                    self.executeVideoAction(action)
                }
            }
        }
    }

    // MARK: - Live Chat

    func sendChatMessage(_ message: String) {
        guard !message.trimmingCharacters(in: .whitespaces).isEmpty else {
            print("⚠️ [CoachPage] Empty message, ignoring")
            return
        }
        print("💬 ========== CHAT START ==========")
        print("💬 [CoachPage] User message: \"\(message)\"")
        print("💬 [CoachPage] Delivery ID: \(liveDelivery.id.uuidString.prefix(8))...")
        print("💬 [CoachPage] Phases available: \(phases.count)")
        for (i, phase) in phases.enumerated() {
            print("💬 [CoachPage]   [\(i)] \(phase.name): \(phase.status) @ \(phase.clipTimestamp ?? -1)s")
        }

        let userMessage = ChatMessage(text: message, isUser: true, videoAction: nil)
        chatMessages.append(userMessage)
        print("💬 [CoachPage] User message added to chat (total: \(chatMessages.count))")
        isLoading = true

        Task {
            print("💬 [CoachPage] Calling NetworkService.chat()...")
            let startTime = Date()
            do {
                let response = try await CompositeNetworkService.shared.chat(
                    message: message,
                    deliveryId: liveDelivery.id.uuidString,
                    phases: phases
                )
                let latency = Date().timeIntervalSince(startTime)
                await MainActor.run {
                    print("💬 [CoachPage] Response received in \(String(format: "%.2f", latency))s")
                    print("💬 [CoachPage] Coach text: \"\(response.text.prefix(80))...\"")
                    print("💬 [CoachPage] Video action: \(response.video_action?.action ?? "none") @ \(response.video_action?.timestamp ?? -1)s")

                    let coachMessage = ChatMessage(
                        text: response.text,
                        isUser: false,
                        videoAction: response.video_action
                    )
                    chatMessages.append(coachMessage)
                    print("💬 [CoachPage] Coach message added (total: \(chatMessages.count))")
                    isLoading = false

                    if let action = response.video_action {
                        print("💬 [CoachPage] Executing video action...")
                        executeVideoAction(action)
                    } else {
                        print("💬 [CoachPage] No video action to execute")
                    }
                    print("💬 ========== CHAT END ==========")
                }
            } catch {
                let latency = Date().timeIntervalSince(startTime)
                await MainActor.run {
                    print("❌ [CoachPage] Chat FAILED after \(String(format: "%.2f", latency))s")
                    print("❌ [CoachPage] Error: \(error)")
                    print("❌ [CoachPage] Error type: \(type(of: error))")

                    let friendlyMessage = self.friendlyErrorMessage(for: error)
                    let errorMessage = ChatMessage(
                        text: friendlyMessage,
                        isUser: false,
                        videoAction: nil
                    )
                    chatMessages.append(errorMessage)
                    isLoading = false
                    print("💬 ========== CHAT END (ERROR) ==========")
                }
            }
        }
    }

    // MARK: - Video Actions

    func executeVideoAction(_ action: VideoAction) {
        print("🎬 ========== VIDEO ACTION ==========")
        print("🎬 [VideoAction] Action: \(action.action)")
        print("🎬 [VideoAction] Timestamp: \(action.timestamp ?? -1)s")
        print("🎬 [VideoAction] Player exists: \(player != nil)")
        print("🎬 [VideoAction] Current rate: \(player?.rate ?? -1)")

        switch action.action {
        case "focus":
            if let timestamp = action.timestamp {
                print("🎬 [VideoAction] → Starting FOCUS LOOP at \(timestamp)s")
                startFocusLoop(at: timestamp)
            } else {
                print("⚠️ [VideoAction] FOCUS action missing timestamp!")
            }
        case "pause":
            print("🎬 [VideoAction] → PAUSE video")
            stopFocusLoop()
            player?.pause()
            isVideoPlaying = false
            print("🎬 [VideoAction] Video paused, isPlaying=\(isVideoPlaying)")
        case "play":
            print("🎬 [VideoAction] → PLAY video (normal speed)")
            stopFocusLoop()
            player?.rate = 1.0
            player?.play()
            isVideoPlaying = true
            print("🎬 [VideoAction] Video playing, rate=\(player?.rate ?? -1)")
        default:
            print("⚠️ [VideoAction] Unknown action: \(action.action)")
        }
        print("🎬 ========== VIDEO ACTION END ==========")
    }

    func startFocusLoop(at timestamp: Double) {
        print("🔄 ========== FOCUS LOOP START ==========")
        print("🔄 [FocusLoop] Target timestamp: \(timestamp)s")

        stopFocusLoop()

        guard let player = player else {
            print("❌ [FocusLoop] Player is nil, cannot start loop!")
            return
        }

        let targetTime = CMTime(seconds: timestamp, preferredTimescale: 600)

        player.seek(to: targetTime, toleranceBefore: .zero, toleranceAfter: .zero) { [self] completed in
            guard completed else {
                print("❌ [FocusLoop] Seek failed!")
                return
            }

            self.player?.rate = 0.5
            self.isVideoPlaying = true
            print("🔄 [FocusLoop] Playing at rate: \(self.player?.rate ?? -1)")

            self.focusLoopTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [self] timer in
                self.player?.seek(to: targetTime, toleranceBefore: .zero, toleranceAfter: .zero) { seeked in
                    print("🔄 [FocusLoop] Loop seek completed: \(seeked)")
                }
            }
        }
    }

    func stopFocusLoop() {
        if focusLoopTimer != nil {
            print("🔄 [FocusLoop] Stopping active focus loop")
            focusLoopTimer?.invalidate()
            focusLoopTimer = nil
            player?.rate = 1.0
        }
    }

    // MARK: - Error Handling

    func friendlyErrorMessage(for error: Error) -> String {
        let nsError = error as NSError

        if nsError.domain == "NSURLErrorDomain" {
            switch nsError.code {
            case -1009: return "📶 No internet connection. Please check your network and try again."
            case -1001: return "⏱️ Request timed out. The server might be busy - please try again."
            case -1004: return "🔌 Can't reach the server. Please try again in a moment."
            case -1005: return "📡 Connection lost. Please check your network and try again."
            default: return "🌐 Network error. Please check your connection and try again."
            }
        }

        if nsError.domain == "ChatError" {
            let code = nsError.code
            if code == 401 || code == 403 { return "🔐 Authentication error. Please restart the app." }
            if code == 429 { return "🐢 Too many requests. Please wait a moment and try again." }
            if code >= 500 && code < 600 { return "🔧 Server is having issues. Please try again shortly." }
            return "⚠️ Something went wrong. Please try again."
        }

        if error is DecodingError {
            return "📦 Received unexpected response. Please try again."
        }

        return "⚠️ Something went wrong. Please try again."
    }
}
