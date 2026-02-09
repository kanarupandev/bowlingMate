import SwiftUI

// MARK: - Chat Bubble
struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.isUser { Spacer() }

            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 6) {
                Text(message.text)
                    .font(.system(size: 14))
                    .foregroundColor(.white)
                    .multilineTextAlignment(message.isUser ? .trailing : .leading)

                // Show video action indicator if present
                if let action = message.videoAction {
                    HStack(spacing: 4) {
                        Image(systemName: action.action == "focus" ? "arrow.trianglehead.clockwise.rotate.90" : "play.circle")
                            .font(.system(size: 10))
                        if let ts = action.timestamp {
                            Text("@ \(String(format: "%.1f", ts))s")
                                .font(.system(size: 10))
                        }
                    }
                    .foregroundColor(DesignSystem.Colors.primary)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(message.isUser ? DesignSystem.Colors.primary.opacity(0.3) : Color.white.opacity(0.1))
            .cornerRadius(16)

            if !message.isUser { Spacer() }
        }
    }
}

// MARK: - Quick Chip (Compact inline suggestion)
struct QuickChip: View {
    let text: String
    var onTap: (String) -> Void

    var body: some View {
        Button(action: { onTap(text) }) {
            Text(text)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.white.opacity(0.8))
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.white.opacity(0.08))
                .cornerRadius(14)
        }
    }
}

// MARK: - Speed Badge
struct SpeedBadge: View {
    let speed: String

    var body: some View {
        HStack(spacing: 8) {
            Text("~\(speed)")
                .font(.system(size: 32, weight: .black))
                .foregroundStyle(DesignSystem.Gradients.main)
            Image(systemName: "figure.cricket")
                .font(.system(size: 24))
                .foregroundColor(.white)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .background(Color.black.opacity(0.6))
        .cornerRadius(20)
    }
}

// MARK: - Bullet Point
struct BulletPoint: View {
    let text: String
    let isPositive: Bool

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(isPositive ? DesignSystem.Colors.success : DesignSystem.Colors.error)
                .frame(width: 8, height: 8)
            Text(text)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white)
        }
    }
}

// MARK: - Swipe Indicator
struct SwipeIndicator: View {
    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: "chevron.down")
                .font(.system(size: 16, weight: .bold))
            Text("swipe for more")
                .font(.system(size: 13))
        }
        .foregroundColor(.white.opacity(0.5))
    }
}

// MARK: - Annotating Indicator (90-second progress overlay)
struct AnnotatingIndicator: View {
    var text: String = "Annotating"
    var maxDuration: TimeInterval = 90.0  // 90 seconds

    @State private var progress: Double = 0.0  // 0.0 to 1.0
    @State private var elapsedTime: Int = 0  // seconds
    @State private var timer: Timer? = nil
    @State private var timedOut: Bool = false

    var body: some View {
        VStack(spacing: 12) {
            if timedOut {
                // Error state after 90 seconds
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 40))
                    .foregroundColor(.red)
                Text("Overlay generation timed out")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.red)
                Text("This may take longer than usual")
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.7))
            } else {
                // Standard iOS progress view
                ProgressView(value: progress, total: 1.0)
                    .tint(.blue)
                    .scaleEffect(1.5)

                Text(text)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(.white)

                // Timer display
                Text("\(elapsedTime)s / 90s")
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.6))
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.black.opacity(0.8))
        )
        .onAppear {
            startTimer()
        }
        .onDisappear {
            timer?.invalidate()
            timer = nil
        }
    }

    private func startTimer() {
        // Update every 5 seconds as requested
        timer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { _ in
            elapsedTime += 5
            progress = Double(elapsedTime) / maxDuration

            if elapsedTime >= Int(maxDuration) {
                timedOut = true
                timer?.invalidate()
                print("❌ [Overlay] Timeout: Annotation not ready after 90 seconds")
            }
        }
    }
}

// MARK: - Color Legend for Overlay Annotations
struct OverlayColorLegend: View {
    var body: some View {
        HStack(spacing: 12) {
            LegendItem(color: .green, label: "Good")
            LegendItem(color: .yellow, label: "Attention")
            LegendItem(color: .red, label: "Injury Risk")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color.black.opacity(0.75))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.white.opacity(0.15), lineWidth: 1)
        )
    }

    struct LegendItem: View {
        let color: Color
        let label: String

        var body: some View {
            HStack(spacing: 6) {
                Circle()
                    .fill(color)
                    .frame(width: 10, height: 10)
                Text(label)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.85))
            }
        }
    }
}
