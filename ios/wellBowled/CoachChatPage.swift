import SwiftUI
import AVKit

// MARK: - Page 2: Coach Chat (Simplified with minimize/expand)
struct CoachChatPage: View {
    var viewModel: BowlViewModel? = nil  // Optional for live updates
    let delivery: Delivery  // Initial snapshot - use liveDelivery for updates
    @Binding var player: AVPlayer?

    // Video state management
    enum VideoState: Equatable {
        case loading
        case playingOriginal(URL)
        case playingAnnotated(URL)
    }

    @State var videoState: VideoState = .loading
    @State var isVideoPlaying = true
    @State var looper: AVPlayerLooper? = nil // Must retain to keep video looping

    // Chat state
    @State var chatMessages: [ChatMessage] = []
    @State var isLoading = false
    @State var isChatExpanded = false // Minimize/expand chat

    // Focus loop state
    @State var focusLoopTimer: Timer? = nil

    // MARK: - Computed Properties (Derived State)

    // Live delivery from viewModel (updates when overlay arrives)
    var liveDelivery: Delivery {
        viewModel?.selectedDelivery ?? delivery
    }

    var phases: [AnalysisPhase] {
        liveDelivery.phases ?? []
    }

    var originalVideoURL: URL? {
        liveDelivery.videoURL
    }

    var overlayURL: URL? {
        if let localPath = liveDelivery.localOverlayPath {
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let localURL = documents.appendingPathComponent("overlays").appendingPathComponent(localPath)
            if FileManager.default.fileExists(atPath: localURL.path) {
                return localURL
            }
        }
        return nil
    }

    var isAnnotationReady: Bool {
        if case .playingAnnotated = videoState {
            return true
        }
        return false
    }

    var shouldShowChat: Bool {
        return isAnnotationReady && isChatExpanded
    }

    var shouldShowLoadingSpinner: Bool {
        if case .playingAnnotated = videoState {
            return false
        }
        return !phases.isEmpty
    }

    // MARK: - Body

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color.black.ignoresSafeArea()

                if !isAnnotationReady {
                    // STATE 1: Before annotation ready - Full screen video + spinner
                    fullScreenVideoArea
                        .frame(width: geo.size.width, height: geo.size.height)
                } else if !isChatExpanded {
                    // STATE 2: Annotation ready, chat minimized
                    ZStack {
                        fullScreenVideoArea
                            .frame(width: geo.size.width, height: geo.size.height)
                        VStack {
                            Spacer()
                            HStack {
                                Spacer()
                                expandButton
                                    .padding(.trailing, 32)
                                    .padding(.bottom, 24)
                            }
                        }
                    }
                } else {
                    // STATE 3: Chat expanded - Vertical (Video 60% | Chat 40%)
                    ZStack {
                        VStack(spacing: 0) {
                            // TOP: Video Section (60% height)
                            ZStack {
                                Color.black
                                if let p = player {
                                    VideoPlayer(player: p)
                                        .aspectRatio(contentMode: .fit)
                                }
                                if player != nil && !isVideoPlaying {
                                    Color.black.opacity(0.3)
                                    Image(systemName: "play.fill")
                                        .font(.system(size: 32))
                                        .foregroundColor(.white.opacity(0.9))
                                }
                                VStack {
                                    Spacer()
                                    OverlayColorLegend()
                                        .padding(.bottom, 8)
                                }
                            }
                            .frame(height: geo.size.height * 0.60)
                            .padding(12)
                            .onTapGesture {
                                if player != nil {
                                    isVideoPlaying.toggle()
                                    if isVideoPlaying { player?.play() } else { player?.pause() }
                                }
                            }

                            // BOTTOM: Chat Section (40% height)
                            VStack(spacing: 8) {
                                HStack(spacing: 6) {
                                    QuickChip(text: "Release") { _ in sendDemoMessage("Focus on Release") }
                                    QuickChip(text: "Follow") { _ in sendDemoMessage("Show Follow-Through") }
                                    QuickChip(text: "Pause") { _ in sendDemoMessage("Pause & Explain") }
                                }
                                .padding(.top, 8)

                                ScrollViewReader { proxy in
                                    ScrollView(showsIndicators: false) {
                                        LazyVStack(spacing: 8) {
                                            ForEach(chatMessages) { msg in
                                                ChatBubble(message: msg)
                                                    .padding(.horizontal, 16)
                                            }
                                            Color.clear.frame(height: 1).id("chatBottom")
                                        }
                                    }
                                    .onChange(of: chatMessages.count) { _, _ in
                                        withAnimation(.easeOut(duration: 0.3)) {
                                            proxy.scrollTo("chatBottom", anchor: .bottom)
                                        }
                                    }
                                }
                                .frame(maxHeight: .infinity)
                            }
                            .frame(width: geo.size.width * 0.90, height: geo.size.height * 0.40)
                            .background(Color.black.opacity(0.3))
                        }

                        VStack {
                            Spacer()
                            HStack {
                                Spacer()
                                collapseButton
                                    .padding(.trailing, 32)
                                    .padding(.bottom, 24)
                            }
                        }
                    }
                }
            }
            .frame(width: geo.size.width, height: geo.size.height)
        }
        .animation(.easeInOut(duration: 0.3), value: isChatExpanded)
        .background(Color.clear)
        .onChange(of: isChatExpanded) { oldValue, newValue in
            print("💬 [CoachPage] isChatExpanded: \(oldValue) → \(newValue)")
        }
        .onChange(of: videoState) { oldValue, newValue in
            print("🎬 [CoachPage] videoState changed")
            print("   Old: \(String(describing: oldValue))")
            print("   New: \(String(describing: newValue))")
            print("   isAnnotationReady: \(isAnnotationReady)")
        }
        .task {
            print("🎬 [CoachPage] ========== PAGE APPEARS ==========")
            await setupInitialVideo()
        }
        .onChange(of: overlayURL) { oldURL, newURL in
            handleOverlayReady(oldURL: oldURL, newURL: newURL)
        }
        .onDisappear {
            print("🎬 [CoachPage] ========== PAGE DISAPPEARS ==========")
            stopFocusLoop()
            player?.pause()
        }
    }
}

// MARK: - Annotated Video + Chat (Alias wrapper for UIComponents.swift)
struct AnnotatedChatPage: View {
    var viewModel: BowlViewModel? = nil
    var delivery: Delivery? = nil
    var phases: [AnalysisPhase] = []
    @Binding var player: AVPlayer?

    var body: some View {
        if let vm = viewModel, let del = vm.selectedDelivery {
            CoachChatPage(viewModel: vm, delivery: del, player: $player)
        } else if let del = delivery {
            CoachChatPage(viewModel: nil, delivery: del, player: $player)
        } else {
            Color.black
        }
    }
}
