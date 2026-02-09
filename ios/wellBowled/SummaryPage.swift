import SwiftUI
import AVKit

// MARK: - Page 0: Summary Video (Overlay preferred)
struct OriginalVideoPage: View {
    let delivery: Delivery
    let phases: [AnalysisPhase]
    @Binding var player: AVPlayer?

    var goodPhases: [AnalysisPhase] { phases.filter { $0.isGood }.prefix(2).map { $0 } }
    var badPhases: [AnalysisPhase] { phases.filter { !$0.isGood }.prefix(2).map { $0 } }

    // Check if overlay is ready (downloaded) or no overlay expected
    private var isOverlayReady: Bool {
        if delivery.overlayVideoURL == nil && delivery.localOverlayPath == nil { return true }
        guard let localPath = delivery.localOverlayPath else { return false }
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let localURL = documents.appendingPathComponent("overlays").appendingPathComponent(localPath)
        return FileManager.default.fileExists(atPath: localURL.path)
    }

    // Resolve overlay URL: prefer local cache, fallback to original video
    private var effectiveVideoURL: URL? {
        // Check local overlay cache first
        if let localPath = delivery.localOverlayPath {
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let localURL = documents.appendingPathComponent("overlays").appendingPathComponent(localPath)
            if FileManager.default.fileExists(atPath: localURL.path) {
                print("🎬 [SummaryPage] Using LOCAL overlay: \(localPath)")
                return localURL
            }
        }
        // Fallback to original video
        print("🎬 [SummaryPage] Fallback to original video: \(delivery.videoURL?.lastPathComponent ?? "nil")")
        return delivery.videoURL
    }

    var body: some View {
        GeometryReader { geo in
            ZStack {
                // Video Background (overlay if available, else original)
                if let url = effectiveVideoURL {
                    PortraitVideoPlayer(url: url, player: $player)
                        .id(url) // Force player recreation when URL changes (original → overlay)
                        .ignoresSafeArea()
                        .onAppear {
                            print("🎬 [SummaryPage] Playing video: \(url.lastPathComponent)")
                        }
                }

                // Annotating indicator (shown while waiting for overlay)
                if !isOverlayReady {
                    VStack {
                        AnnotatingIndicator(text: "Annotating for interactive analysis")
                            .padding(.top, geo.safeAreaInsets.top + 60)
                        Spacer()
                    }
                }

                // Content Overlay — speed badge + bullets
                VStack {
                    Spacer()

                    // Speed Badge
                    SpeedBadge(speed: delivery.speed ?? "--")
                        .padding(.bottom, 20)

                    // 4 Bullet Points (2 green, 2 red)
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(goodPhases) { phase in
                            BulletPoint(text: phase.name, isPositive: true)
                        }
                        ForEach(badPhases) { phase in
                            BulletPoint(text: phase.name, isPositive: false)
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 16)
                    .background(Color.black.opacity(0.6))
                    .cornerRadius(16)
                    .padding(.horizontal, 20)
                    .padding(.bottom, 80) // Room for pinned swipe indicator
                }

                // PINNED: Swipe indicator at 95% from top (5% from bottom)
                SwipeIndicator()
                    .position(x: geo.size.width / 2, y: geo.size.height * 0.95)
            }
        }
    }
}
