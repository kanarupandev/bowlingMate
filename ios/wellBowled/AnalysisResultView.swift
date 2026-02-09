import SwiftUI
import AVKit

// MARK: - Chat Message Model
struct ChatMessage: Identifiable {
    let id = UUID()
    let text: String
    let isUser: Bool
    let videoAction: VideoAction?
}

// MARK: - Analysis Result View (3 Vertical Pages)
// Page 0: Original video (the actual clip) + speed badge + summary bullets
// Page 1: Expert Analysis (all phases - GOOD first, then WORK)
// Page 2: Annotated video + Chat
struct AnalysisResultView: View {
    @ObservedObject var viewModel: BowlViewModel
    var onDismiss: () -> Void

    @State private var scrollPosition: Int? = 0
    @State private var originalPlayer: AVPlayer?
    @State private var overlayPlayer: AVPlayer?

    // Live binding to selectedDelivery - updates when overlay arrives
    private var delivery: Delivery? { viewModel.selectedDelivery }
    private var phases: [AnalysisPhase] { delivery?.phases ?? [] }

    // Timeout state for overlay waiting (90 seconds max)
    @State private var overlayTimeout = false

    // Check if overlay has been downloaded locally (or no overlay expected)
    private var isOverlayReady: Bool {
        // Timeout exceeded - stop waiting
        if overlayTimeout { return true }
        // No overlay expected from backend — nothing to wait for
        if delivery?.overlayVideoURL == nil && delivery?.localOverlayPath == nil { return true }
        guard let localPath = delivery?.localOverlayPath else { return false }
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let localURL = documents.appendingPathComponent("overlays").appendingPathComponent(localPath)
        return FileManager.default.fileExists(atPath: localURL.path)
    }

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            if let delivery = delivery {
                // Vertical paging with ScrollView
                GeometryReader { geo in
                    ScrollView(.vertical, showsIndicators: false) {
                        LazyVStack(spacing: 0) {
                            // Page 0: ORIGINAL video + speed + bullets
                            OriginalVideoPage(
                                delivery: delivery,
                                phases: phases,
                                player: $originalPlayer
                            )
                            .frame(width: geo.size.width, height: geo.size.height)
                            .id(0)

                            // Page 1: Expert Analysis (all phases detailed)
                            ExpertAnalysisPage(phases: phases, isOverlayReady: isOverlayReady)
                                .frame(width: geo.size.width, height: geo.size.height)
                                .id(1)

                            // Page 2: ANNOTATED video + Chat
                            CoachChatPage(
                                viewModel: viewModel,
                                delivery: delivery,
                                player: $overlayPlayer
                            )
                            .frame(width: geo.size.width, height: geo.size.height)
                            .id(2)
                        }
                        .scrollTargetLayout()
                    }
                    .scrollTargetBehavior(.paging)
                    .scrollPosition(id: $scrollPosition)
                    .scrollDisabled(scrollPosition == 2)
                }

                // Close button
                VStack {
                    HStack {
                        Spacer()
                        Button(action: onDismiss) {
                            Image(systemName: "xmark")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(.white)
                                .padding(12)
                                .background(Color.black.opacity(0.4))
                                .clipShape(Circle())
                        }
                        .padding(.trailing, 20)
                        .padding(.top, 50)
                    }
                    Spacer()
                }
            }
        }
        .onAppear {
            // Reset to Page 0
            scrollPosition = 0
            print("📄 [AnalysisResult] View appeared")
            print("📄 [AnalysisResult] Delivery ID: \(delivery?.id.uuidString.prefix(8) ?? "nil")")
            print("📄 [AnalysisResult] localOverlayPath: \(delivery?.localOverlayPath ?? "nil")")
            print("📄 [AnalysisResult] isOverlayReady: \(isOverlayReady)")

            // Start 90-second timeout for overlay generation
            if !isOverlayReady {
                DispatchQueue.main.asyncAfter(deadline: .now() + 90) {
                    if !self.isOverlayReady {
                        print("⏱️ [AnalysisResult] Overlay timeout (90s) - stopping indicator")
                        self.overlayTimeout = true
                    }
                }
            }
        }
        .onDisappear {
            overlayPlayer?.pause()
            originalPlayer?.pause()
        }
        .onChange(of: scrollPosition) { _, newValue in
            if let page = newValue {
                print("📄 [AnalysisResult] Page changed to: \(page)")
            }
        }
        .onChange(of: delivery?.localOverlayPath) { oldValue, newValue in
            print("📄 [AnalysisResult] 🔄 localOverlayPath CHANGED: \(oldValue ?? "nil") → \(newValue ?? "nil")")
        }
    }
}
