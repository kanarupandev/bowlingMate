import SwiftUI
import AVKit
import Combine

struct CustomVideoPlayer: UIViewRepresentable {
    let player: AVPlayer

    func makeUIView(context: Context) -> PlayerUIView {
        let view = PlayerUIView()
        view.player = player
        return view
    }

    func updateUIView(_ uiView: PlayerUIView, context: Context) {
        uiView.player = player
    }
}

class PlayerUIView: UIView {
    private var playerLayer: AVPlayerLayer?

    var player: AVPlayer? {
        didSet {
            if playerLayer == nil {
                let layer = AVPlayerLayer()
                layer.videoGravity = .resizeAspect
                self.layer.addSublayer(layer)
                playerLayer = layer
            }
            playerLayer?.player = player
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        playerLayer?.frame = bounds
    }
}

struct MetricBadge: View {
    let title: String; let value: String; let unit: String
    var body: some View {
        VStack(spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .black))
                .foregroundColor(.white.opacity(0.4))
                .tracking(1.5)
            HStack(alignment: .lastTextBaseline, spacing: 2) {
                Text(value)
                    .font(.system(size: 28, weight: .black, design: .rounded))
                    .foregroundColor(DesignSystem.Colors.primary)
                Text(unit)
                    .font(.system(size: 12, weight: .bold))
                    .foregroundColor(DesignSystem.Colors.primary.opacity(0.6))
            }
        }
        .padding(12)
        .background(DesignSystem.Colors.surface)
        .cornerRadius(16)
    }
}

struct ScrubberView: View {
    let player: AVPlayer?; let startTime: Double; let endTime: Double
    @State private var progress: Double = 0
    var body: some View {
        VStack(spacing: 8) {
            Slider(value: $progress, in: startTime...endTime) { _ in player?.seek(to: CMTime(seconds: progress, preferredTimescale: 600)) }.accentColor(.blue)
            HStack { Text(String(format: "%.1fs", startTime)).font(.caption2).foregroundColor(.gray); Spacer(); Text(String(format: "%.1fs", endTime)).font(.caption2).foregroundColor(.gray) }
        }.onReceive(Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()) { _ in if let currentTime = player?.currentTime().seconds { self.progress = currentTime } }
    }
}

struct DeliveryCard: View {
    let delivery: Delivery
    let onTap: () -> Void
    let onAnalyze: () -> Void
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("DELIVERY #\(delivery.sequence)")
                    .font(.system(size: 10, weight: .black, design: .rounded))
                    .foregroundColor(.white.opacity(0.5))
                    .tracking(1)
                Spacer()
                if delivery.status == .success { 
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(DesignSystem.Colors.accent) 
                }
                else if delivery.status == .failed { 
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(DesignSystem.Colors.error) 
                }
                else if delivery.status == .queued {
                    Image(systemName: "sparkles")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundColor(DesignSystem.Colors.primary)
                }
                else { 
                    ProgressView()
                        .tint(DesignSystem.Colors.primary)
                        .scaleEffect(0.6) 
                }
            }
            if delivery.status == .success, let speed = delivery.speed {
                VStack(alignment: .leading, spacing: 2) {
                    Text(speed)
                        .font(.system(size: 32, weight: .black, design: .rounded))
                        .foregroundStyle(DesignSystem.Gradients.main)
                        .minimumScaleFactor(0.5)
                    Text(delivery.report?.components(separatedBy: "\n").first ?? "")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.7))
                        .lineLimit(2)
                        .minimumScaleFactor(0.8)
                }
            } else { 
                Text(delivery.status.rawValue.uppercased())
                    .font(.system(size: 12, weight: .black, design: .rounded))
                    .foregroundColor(.white.opacity(0.3))
                    .frame(maxWidth: .infinity, maxHeight: .infinity) 
            }
            if let url = delivery.videoURL { 
                InteractiveClipPlayer(url: url, thumbnail: delivery.thumbnail, isActive: false)
                    .frame(height: 60)
                    .cornerRadius(12) 
                    .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.1), lineWidth: 1))
            }
        }
        .padding(16)
        .frame(width: 170, height: 180)
        .premiumGlass()
        .onTapGesture {
            onTap()
        }
        .overlay(alignment: .bottomTrailing) {
            // Show analyze button when clip is ready (.queued) or needs retry (.failed)
            // Status flow: .clipping → .queued → .analyzing → .success
            let needsAnalysis = delivery.status == .queued || delivery.status == .failed ||
                                [.analyzing, .uploading, .processing].contains(delivery.status)
            if needsAnalysis && delivery.videoURL != nil {
                Button(action: onAnalyze) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.white)
                        .padding(8)
                        .background(DesignSystem.Colors.primary)
                        .clipShape(Circle())
                }
                .padding(8)
            }
        }
    }
}

struct TechnicalLoopPlayer: View {
    let url: URL
    @Binding var isMuted: Bool
    @State private var player: AVPlayer?
    @State private var looper: AVPlayerLooper?
    
    var body: some View {
        VideoPlayer(player: player)
            .onAppear {
                let asset = AVAsset(url: url)
                let playerItem = AVPlayerItem(asset: asset)
                let queuePlayer = AVQueuePlayer(playerItem: playerItem)
                
                // Zero-gap seamless looping
                looper = AVPlayerLooper(player: queuePlayer, templateItem: playerItem)
                
                queuePlayer.isMuted = isMuted
                queuePlayer.play()
                self.player = queuePlayer
            }
            .onChange(of: isMuted) { oldValue, muted in
                player?.isMuted = muted
            }
            .onDisappear {
                player?.pause()
                player = nil
                looper = nil
            }
            .disabled(true) // No manual controls
    }
}

struct UploadDeliveryCard: View {
    let delivery: Delivery
    let isActive: Bool
    var onAnalyze: () -> Void
    var onDelete: () -> Void
    var onFavorite: () -> Void
    var onSelect: (() -> Void)? = nil
    var isAnyAnalysisRunning: Bool
    var resolveOverlayURL: ((Delivery) -> URL?)? = nil

    @State private var showFeedback = false
    @State private var showAnalysisView = true // Default to Analysis view (shows overlay when ready)
    @State private var currentPage: Int = 0 // 0=Summary, 1=Expert, 2=Chat
    @State private var chatPlayer: AVPlayer? = nil // Player for chat page video

    // Computed: has analysis completed with phases?
    private var hasAnalysisResults: Bool {
        delivery.status == .success && !(delivery.phases ?? []).isEmpty
    }

    // Summary bullets from phases
    private var goodPhases: [AnalysisPhase] {
        (delivery.phases ?? []).filter { $0.isGood }.prefix(2).map { $0 }
    }
    private var needsWorkPhases: [AnalysisPhase] {
        (delivery.phases ?? []).filter { !$0.isGood }.prefix(2).map { $0 }
    }

    private var effectiveVideoURL: URL? {
        // 1. Check localVideoPath (FILENAME ONLY)
        if let fileName = delivery.localVideoPath {
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let localURL = documents.appendingPathComponent(fileName)
            if FileManager.default.fileExists(atPath: localURL.path) {
                return localURL
            }
        }
        // 2. Fallback to absolute videoURL (Legacy / In-session)
        if let legacyURL = delivery.videoURL, FileManager.default.fileExists(atPath: legacyURL.path) {
            return legacyURL
        }
        // 3. Last Resort: Cloud URL
        return delivery.cloudVideoURL
    }

    private var effectiveOverlayURL: URL? {
        // Use resolver if provided, otherwise direct access
        if let resolver = resolveOverlayURL {
            return resolver(delivery)
        }
        // Fallback: Check local first, then cloud
        if let localPath = delivery.localOverlayPath {
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let localURL = documents.appendingPathComponent("overlays").appendingPathComponent(localPath)
            if FileManager.default.fileExists(atPath: localURL.path) {
                return localURL
            }
        }
        return delivery.overlayVideoURL
    }

    private var hasOverlay: Bool {
        effectiveOverlayURL != nil
    }

    var body: some View {
        GeometryReader { geometry in
            // When analysis complete: show 3-page vertical swipe
            if hasAnalysisResults {
                ScrollView(.vertical, showsIndicators: false) {
                    LazyVStack(spacing: 0) {
                        // Page 0: Original video + Summary overlay
                        summaryPage(geometry: geometry)
                            .frame(width: geometry.size.width, height: geometry.size.height)
                            .id(0)

                        // Page 1: Expert Analysis
                        ExpertAnalysisPage(phases: delivery.phases ?? [])
                            .frame(width: geometry.size.width, height: geometry.size.height)
                            .id(1)

                        // Page 2: Annotated + Chat
                        AnnotatedChatPage(
                            delivery: delivery,
                            phases: delivery.phases ?? [],
                            player: $chatPlayer
                        )
                        .frame(width: geometry.size.width, height: geometry.size.height)
                        .id(2)
                    }
                    .scrollTargetLayout()
                }
                .scrollTargetBehavior(.paging)
            } else {
                // Before analysis: show card with Analyze button
                cardBeforeAnalysis(geometry: geometry)
            }
        }
    }

    // MARK: - Summary Page (Video + Speed + Bullets)
    @ViewBuilder
    private func summaryPage(geometry: GeometryProxy) -> some View {
        ZStack(alignment: .bottom) {
            // Video background
            if let url = effectiveVideoURL {
                InteractiveClipPlayer(url: url, thumbnail: delivery.thumbnail, isActive: isActive)
                    .id(url) // Force recreation when URL changes (original → overlay)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()
            } else if let thumb = delivery.thumbnail {
                Image(uiImage: thumb)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: geometry.size.width, height: geometry.size.height)
                    .clipped()
            }

            // Gradient scrim — pass taps through to video player
            LinearGradient(
                gradient: Gradient(colors: [.clear, .black.opacity(0.8)]),
                startPoint: .center,
                endPoint: .bottom
            )
            .allowsHitTesting(false)

            // Summary overlay (centered above buttons) — pass taps through to video player
            VStack {
                Spacer()

                // Speed badge
                if let speed = delivery.speed {
                    Text("~\(speed)")
                        .font(.system(size: 14, weight: .black))
                        .foregroundStyle(DesignSystem.Gradients.main)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(Color.black.opacity(0.6))
                        .cornerRadius(12)
                        .padding(.bottom, 10)
                }

                // Bullet points
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(goodPhases) { phase in
                        HStack(spacing: 8) {
                            Circle()
                                .fill(DesignSystem.Colors.success)
                                .frame(width: 6, height: 6)
                            Text(phase.name)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(.white)
                        }
                    }
                    ForEach(needsWorkPhases) { phase in
                        HStack(spacing: 8) {
                            Circle()
                                .fill(DesignSystem.Colors.error)
                                .frame(width: 6, height: 6)
                            Text(phase.name)
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(.white)
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(Color.black.opacity(0.6))
                .cornerRadius(12)

                // Swipe indicator
                SwipeIndicator()
                    .padding(.top, 12)
                    .padding(.bottom, 100) // Space for bottom buttons
            }
            .allowsHitTesting(false)

            // BOTTOM ACTIONS - Same as original card (delete left, favorite right)
            HStack(alignment: .bottom) {
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundColor(.white.opacity(0.8))
                        .frame(width: 40, height: 40)
                        .background(Color.red.opacity(0.3))
                        .clipShape(Circle())
                        .overlay(Circle().stroke(Color.white.opacity(0.1), lineWidth: 0.5))
                }

                Spacer()

                Button(action: onFavorite) {
                    Image(systemName: delivery.isFavorite ? "heart.fill" : "heart")
                        .font(.system(size: 16))
                        .foregroundColor(delivery.isFavorite ? DesignSystem.Colors.secondary : .white)
                        .frame(width: 40, height: 40)
                        .background(Color.white.opacity(0.1))
                        .clipShape(Circle())
                        .overlay(Circle().stroke(Color.white.opacity(0.1), lineWidth: 0.5))
                }
            }
            .padding(.horizontal, 32)
            .padding(.bottom, 50)
        }
        .onAppear {
            print("📺 [SummaryPage] Card summary appeared, videoURL: \(effectiveVideoURL?.lastPathComponent ?? "nil"), isActive: \(isActive)")
        }
    }

    // MARK: - Card Before Analysis
    @ViewBuilder
    private func cardBeforeAnalysis(geometry: GeometryProxy) -> some View {
        // Pre-compute values to help type checker
        let mediaHeight: CGFloat = showFeedback ? geometry.size.height * 0.45 : geometry.size.height
        let shouldShowOverlay: Bool = showFeedback && showAnalysisView && hasOverlay
        let displayURL: URL? = shouldShowOverlay ? effectiveOverlayURL : effectiveVideoURL

        ZStack(alignment: .bottom) {
            // 1. IMMERSIVE MEDIA BACKGROUND
            ZStack {
                if let url = displayURL {
                    InteractiveClipPlayer(url: url, thumbnail: delivery.thumbnail, isActive: isActive || showFeedback)
                        .aspectRatio(contentMode: .fill)
                        .frame(width: geometry.size.width, height: mediaHeight)
                        .clipped()
                } else if let thumb = delivery.thumbnail {
                    Image(uiImage: thumb)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: geometry.size.width, height: mediaHeight)
                        .clipped()
                } else {
                    // PREMIUM PLACEHOLDER
                    ZStack {
                        Rectangle()
                            .fill(DesignSystem.Gradients.main.opacity(0.05))
                            .background(.ultraThinMaterial)

                        VStack(spacing: 16) {
                            Image(systemName: "video.slash.fill")
                                .font(.system(size: 32))
                                .foregroundColor(.white.opacity(0.15))

                            Text("CLIPPING IN PROGRESS")
                                .font(.system(size: 10, weight: .black))
                                .foregroundColor(.white.opacity(0.3))
                                .tracking(2)

                            ProgressView()
                                .tint(DesignSystem.Colors.primary.opacity(0.5))
                                .scaleEffect(0.8)
                        }
                    }
                    .frame(height: mediaHeight)
                }

                    // Overlay generation status badge (floating, non-intrusive)
                    if showFeedback && delivery.status == .success {
                        VStack {
                            HStack {
                                Spacer()
                                if !hasOverlay {
                                    // Generating state
                                    HStack(spacing: 6) {
                                        ProgressView()
                                            .scaleEffect(0.6)
                                            .tint(.white)
                                        Text("Generating analysis...")
                                            .font(.system(size: 10, weight: .medium))
                                    }
                                    .foregroundColor(.white.opacity(0.9))
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 6)
                                    .background(.ultraThinMaterial)
                                    .cornerRadius(16)
                                    .padding(12)
                                }
                            }
                            Spacer()
                        }
                        .frame(height: geometry.size.height * 0.45)
                    }
                }
                .frame(maxHeight: .infinity, alignment: .top)

                // Scrim for readability (only when NOT showing feedback)
                if !showFeedback {
                    LinearGradient(
                        gradient: Gradient(colors: [.black.opacity(0.0), .black.opacity(0.8)]),
                        startPoint: .center,
                        endPoint: .bottom
                    )
                    .allowsHitTesting(false)
                }

                // 2. TOP ACTIONS (Analyze & Feedback toggle)
                if !showFeedback {
                    VStack {
                        HStack {
                            Spacer()
                            VStack(alignment: .trailing, spacing: 10) {
                                // Result/Speed Badge - Opens full AnalysisResultView
                                if let speed = delivery.speed {
                                    Button(action: {
                                        // Open new 3-page AnalysisResultView (not old FeedbackOverlay)
                                        if let onSelect = onSelect {
                                            onSelect()
                                        }
                                    }) {
                                        HStack(spacing: 6) {
                                            Image(systemName: "bolt.fill")
                                                .font(.system(size: 10))
                                            Text(speed)
                                                .font(.system(size: 14, weight: .black))
                                        }
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 6)
                                        .background(.ultraThinMaterial)
                                        .cornerRadius(10)
                                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(DesignSystem.Colors.primary.opacity(0.3), lineWidth: 0.5))
                                    }
                                }

                                // Analyze Button - Show when:
                                // 1. Clip ready for analysis (.queued)
                                // 2. Analysis in progress (.analyzing/.processing/.uploading)
                                // 3. Analysis failed - retry (.failed)
                                // Status flow: .clipping → .queued → .analyzing → .success
                                let needsAnalysis = delivery.status == .queued || delivery.status == .failed ||
                                                    [.analyzing, .uploading, .processing].contains(delivery.status)
                                if needsAnalysis && (delivery.videoURL != nil || delivery.cloudVideoURL != nil) {
                                    VStack(alignment: .trailing, spacing: 6) {
                                        let isInProgress = [DeliveryStatus.analyzing, .uploading, .processing].contains(delivery.status)
                                        let hasNoVideo = delivery.videoURL == nil && delivery.cloudVideoURL == nil
                                        let buttonBgColor: Color = hasNoVideo ? .gray : (delivery.status == .failed ? DesignSystem.Colors.error : DesignSystem.Colors.primary)
                                        let buttonOpacity: Double = (isAnyAnalysisRunning && !isInProgress) ? 0.3 : 1.0

                                        Button(action: onAnalyze) {
                                            Group {
                                                if isInProgress {
                                                    ProgressView()
                                                        .tint(.white)
                                                        .scaleEffect(0.6)
                                                } else {
                                                    Image(systemName: delivery.status == .failed ? "arrow.clockwise" : "wand.and.stars")
                                                        .font(.system(size: 16, weight: .bold))
                                                        .foregroundColor(delivery.status == .failed ? .white : .black)
                                                }
                                            }
                                            .frame(width: 44, height: 44)
                                            .background(buttonBgColor)
                                            .opacity(buttonOpacity)
                                            .clipShape(Circle())
                                            .shadow(color: Color.black.opacity(0.3), radius: 5)
                                        }
                                        .disabled(isAnyAnalysisRunning || (delivery.videoURL == nil && delivery.cloudVideoURL == nil))

                                        if delivery.status == .failed {
                                            Text("Failed. Tap to retry.")
                                                .font(.caption2)
                                                .foregroundColor(.white.opacity(0.8))
                                                .padding(.horizontal, 8)
                                                .padding(.vertical, 4)
                                                .background(Color.red.opacity(0.6))
                                                .cornerRadius(4)
                                        }
                                    }
                                }
                            }
                        }
                        Spacer()
                    }
                    .padding(32)
                }

                // BOTTOM ACTIONS (Utility) - Only when NOT showing feedback
                if !showFeedback {
                    HStack(alignment: .bottom) {
                        Button(action: onDelete) {
                            Image(systemName: "trash")
                                .font(.system(size: 14, weight: .bold))
                                .foregroundColor(.white.opacity(0.8))
                                .frame(width: 40, height: 40)
                                .background(Color.red.opacity(0.3))
                                .clipShape(Circle())
                                .overlay(Circle().stroke(Color.white.opacity(0.1), lineWidth: 0.5))
                        }

                        Spacer()

                        Button(action: onFavorite) {
                            Image(systemName: delivery.isFavorite ? "heart.fill" : "heart")
                                .font(.system(size: 16))
                                .foregroundColor(delivery.isFavorite ? DesignSystem.Colors.secondary : .white)
                                .frame(width: 40, height: 40)
                                .background(Color.white.opacity(0.1))
                                .clipShape(Circle())
                                .overlay(Circle().stroke(Color.white.opacity(0.1), lineWidth: 0.5))
                        }
                    }
                    .padding(.horizontal, 32)
                    .padding(.bottom, 50)
                }

                // 3. FEEDBACK PANEL (Bottom half when active)
                if showFeedback && delivery.status == .success {
                    VStack(spacing: 0) {
                        // Video takes top ~45%
                        Spacer()
                            .frame(height: geometry.size.height * 0.45)

                        // Feedback panel takes remaining space
                        VStack(alignment: .leading, spacing: 12) {
                            // Header with toggle and close
                            HStack(spacing: 8) {
                                // Original/Analysis Toggle - Always show
                                HStack(spacing: 0) {
                                    Button(action: { showAnalysisView = false }) {
                                        Text("Original")
                                            .font(.system(size: 10, weight: .bold))
                                            .foregroundColor(showAnalysisView ? .white.opacity(0.5) : .black)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 6)
                                            .background(showAnalysisView ? Color.clear : DesignSystem.Colors.primary)
                                    }
                                    Button(action: {
                                        if hasOverlay { showAnalysisView = true }
                                    }) {
                                        HStack(spacing: 4) {
                                            Text("Analysis")
                                                .font(.system(size: 10, weight: .bold))
                                            if !hasOverlay {
                                                ProgressView()
                                                    .scaleEffect(0.5)
                                                    .tint(.white.opacity(0.5))
                                            }
                                        }
                                        .foregroundColor(showAnalysisView && hasOverlay ? .black : .white.opacity(hasOverlay ? 0.5 : 0.3))
                                        .padding(.horizontal, 10)
                                        .padding(.vertical, 6)
                                        .background(showAnalysisView && hasOverlay ? DesignSystem.Colors.primary : Color.clear)
                                    }
                                    .disabled(!hasOverlay)
                                }
                                .background(Color.white.opacity(0.1))
                                .cornerRadius(8)

                                Spacer()

                                // Close button
                                Button(action: { showFeedback = false }) {
                                    Image(systemName: "xmark.circle.fill")
                                        .font(.system(size: 24))
                                        .foregroundColor(.white.opacity(0.6))
                                }
                            }

                            // Scrollable content
                            ScrollView(.vertical, showsIndicators: false) {
                                VStack(alignment: .leading, spacing: 12) {
                                    // Speed
                                    if let speed = delivery.speed {
                                        HStack(spacing: 6) {
                                            Image(systemName: "bolt.fill")
                                                .font(.system(size: 14))
                                                .foregroundColor(DesignSystem.Colors.primary)
                                            Text(speed)
                                                .font(.system(size: 24, weight: .black, design: .rounded))
                                                .foregroundColor(.white)
                                        }
                                    }

                                    // Report
                                    if let report = delivery.report, !report.isEmpty {
                                        Text(report)
                                            .font(.system(size: 13, weight: .medium))
                                            .foregroundColor(.white.opacity(0.85))
                                            .lineSpacing(3)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }

                                    // Tips
                                    if !delivery.tips.isEmpty {
                                        VStack(alignment: .leading, spacing: 6) {
                                            Text("TIPS")
                                                .font(.system(size: 9, weight: .black))
                                                .foregroundColor(.white.opacity(0.4))
                                                .tracking(1)

                                            ForEach(delivery.tips, id: \.self) { tip in
                                                HStack(alignment: .top, spacing: 6) {
                                                    Image(systemName: "lightbulb.fill")
                                                        .font(.system(size: 10))
                                                        .foregroundColor(DesignSystem.Colors.secondary)
                                                    Text(tip)
                                                        .font(.system(size: 12))
                                                        .foregroundColor(.white.opacity(0.8))
                                                        .fixedSize(horizontal: false, vertical: true)
                                                }
                                            }
                                        }
                                    }
                                }
                                .padding(.bottom, 60)
                            }
                        }
                        .padding(.horizontal, 28) // Safe margin for all iPhone models
                        .padding(.top, 16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            LinearGradient(
                                gradient: Gradient(colors: [Color.black.opacity(0.95), Color.black]),
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                    }
                }
        }
        .background(Color.black)
        .cornerRadius(24)
        .overlay(
            RoundedRectangle(cornerRadius: 24)
                .stroke(Color.white.opacity(0.1), lineWidth: 0.5)
        )
        .shadow(color: Color.black.opacity(0.3), radius: 10, x: 0, y: 5)
        .animation(.easeInOut(duration: 0.25), value: showFeedback)
        .animation(.easeInOut(duration: 0.15), value: showAnalysisView)
        .onChange(of: hasOverlay) { _, overlayReady in
            if overlayReady {
                showAnalysisView = true
            }
        }
    }
}

struct ActivityIndicatorStrip: View {
    @State private var offset: CGFloat = -100
    
    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(Color.white.opacity(0.1))
                    .frame(height: 2)
                
                RoundedRectangle(cornerRadius: 1)
                    .fill(DesignSystem.Colors.primary)
                    .frame(width: 40, height: 2)
                    .offset(x: offset)
            }
            .onAppear {
                withAnimation(.linear(duration: 1.5).repeatForever(autoreverses: false)) {
                    offset = geometry.size.width
                }
            }
        }
        .frame(height: 2)
    }
}

struct InteractiveClipPlayer: View {
    let url: URL
    let thumbnail: UIImage?
    let isActive: Bool

    @State private var player: AVQueuePlayer?
    @State private var looper: AVPlayerLooper?
    @State private var isPlaying = false
    @State private var isBuffering = false
    @State private var cancellables = Set<AnyCancellable>()

    var body: some View {
        ZStack {
            // 0. GLASS BACKGROUND (Eliminates pure black if thumb is missing)
            Rectangle()
                .fill(Color.white.opacity(0.05))
                .background(.ultraThinMaterial)

            // 1. STATIC THUMBNAIL 
            if let thumb = thumbnail {
                Image(uiImage: thumb)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .opacity(isPlaying && !isBuffering ? 0 : 1)
                    .animation(.easeInOut, value: isPlaying)
            }

            // 2. VIDEO PLAYER
            if let player = player, isPlaying {
                CustomVideoPlayer(player: player)
                    .opacity(isBuffering ? 0 : 1)
            }

            // 3. LOADING/BUFFERING OVERLAY
            if isPlaying && (isBuffering || player == nil) {
                VStack(spacing: 12) {
                    ProgressView()
                        .tint(.white)
                    Text("LOADING CLOUD CLIP...")
                        .font(.system(size: 8, weight: .black))
                        .foregroundColor(.white.opacity(0.5))
                        .tracking(1)
                }
            }

            // 4. TAP GESTURE (Video Area)
            // Only active when playing to allow pause. 
            // When not playing, we let taps fall through to the Card for selection.
            if isPlaying {
                Color.clear
                    .contentShape(Rectangle())
                    .onTapGesture {
                        togglePlayback()
                    }
            }

            // 5. PLAY ICON (When not playing)
            if !isPlaying && !isBuffering {
                Button(action: {
                    if player == nil {
                        setupPlayer()
                    } else {
                        togglePlayback()
                    }
                }) {
                    Image(systemName: "play.fill")
                        .font(.system(size: 44))
                        .foregroundColor(.white.opacity(0.8))
                        .shadow(color: .black.opacity(0.5), radius: 10)
                }
            }
        }
        .allowsHitTesting(true) // Ensure it can be tapped
        .onDisappear { teardownPlayer() }
        .onChange(of: isActive) { _, active in
            if !active { teardownPlayer() }
        }
    }

    private func setupPlayer() {
        let asset = AVAsset(url: url)
        // Ensure the asset is actually playable before showing black
        let item = AVPlayerItem(asset: asset)
        
        let p = AVQueuePlayer(playerItem: item)
        looper = AVPlayerLooper(player: p, templateItem: item)
        p.isMuted = true
        player = p
        
        L("AVQueuePlayer created for \(url.lastPathComponent)", .network)
        
        // Monitor buffering
        item.publisher(for: \.isPlaybackBufferEmpty)
            .receive(on: DispatchQueue.main)
            .sink { empty in
                isBuffering = empty
            }
            .store(in: &cancellables)
            
        item.publisher(for: \.isPlaybackLikelyToKeepUp)
            .receive(on: DispatchQueue.main)
            .sink { ready in
                if ready { isBuffering = false }
            }
            .store(in: &cancellables)

        // Robust Error Handling: Monitor if loading fails
        item.publisher(for: \.status)
            .receive(on: DispatchQueue.main)
            .sink { [weak item] status in
                if status == .failed {
                    print("⚠️ [Player] Failed to load clip: \(url.lastPathComponent)")
                    print("   └─ Error: \(String(describing: item?.error))")
                    isPlaying = false 
                    isBuffering = false
                    player = nil
                }
            }
            .store(in: &cancellables)

        p.play()
        isPlaying = true
    }

    private func togglePlayback() {
        if isPlaying {
            player?.pause()
        } else {
            if player?.status == .failed {
                setupPlayer()
            } else {
                player?.play()
            }
        }
        isPlaying.toggle()
    }

    private func teardownPlayer() {
        player?.pause()
        player = nil
        looper = nil
        cancellables.removeAll()
        isPlaying = false
    }
}

struct ControlCenterView: View {
    let isRecording: Bool
    let onToggle: () -> Void
    let onFlip: () -> Void
    @State private var pulse: CGFloat = 1.0
    
    var body: some View {
        VStack(spacing: 24) {
            if !isRecording { 
                Text("TAP TO START SESSION")
                    .font(.system(size: 11, weight: .black))
                    .foregroundColor(.white.opacity(0.7))
                    .tracking(3)
                    .transition(.opacity)
            }
            
            HStack(spacing: 32) {
                if !isRecording {
                    Button(action: onFlip) {
                        Image(systemName: "camera.rotate.fill")
                            .font(.system(size: 24))
                            .foregroundColor(.white)
                            .padding(20)
                            .background(DesignSystem.Colors.glassBackground)
                            .clipShape(Circle())
                            .overlay(Circle().stroke(DesignSystem.Colors.glassBorder, lineWidth: 1))
                    }
                    .transition(.scale.combined(with: .opacity))
                }

                Button(action: onToggle) {
                    ZStack {
                        Circle()
                            .stroke(Color.white.opacity(0.2), lineWidth: 4)
                            .frame(width: 90, height: 90)
                        
                        if isRecording {
                            Circle()
                                .stroke(DesignSystem.Colors.error.opacity(0.3), lineWidth: pulse * 10)
                                .frame(width: 90, height: 90)
                                .scaleEffect(pulse)
                                .onAppear {
                                    withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                                        pulse = 1.2
                                    }
                                }
                        }
                        
                        Circle()
                            .fill(isRecording ? DesignSystem.Colors.error : Color.white)
                            .frame(width: isRecording ? 40 : 75, height: isRecording ? 40 : 75)
                            .cornerRadius(isRecording ? 8 : 40)
                            .animation(.spring(response: 0.4, dampingFraction: 0.6), value: isRecording)
                    }
                }
                .contentShape(Circle()) // Ensure the entire circle area receives taps
                .buttonStyle(PlainButtonStyle())
                
                if !isRecording {
                    // Spacer for symmetry
                    Color.clear.frame(width: 64, height: 64)
                }
            }
        }
        .padding(.bottom, UIDevice.current.userInterfaceIdiom == .pad ? 60 : 30)
        .safeAreaPadding(.bottom)
    }
}

struct DeliveryStripView: View {
    let deliveries: [Delivery]; let onSelect: (Delivery) -> Void
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 16) { ForEach(deliveries) { delivery in DeliveryCard(delivery: delivery, onTap: { onSelect(delivery) }, onAnalyze: {}).id(delivery.id) } }.padding(.horizontal, 24).padding(.vertical, 12)
            }
            .frame(height: 200)
            .onChange(of: deliveries.count) { oldValue, newValue in withAnimation { proxy.scrollTo(deliveries.last?.id, anchor: .center) } }
        }
    }
}

struct SessionSummaryView: View {
    let deliveries: [Delivery]
    let onReset: () -> Void
    
    var body: some View {
        ZStack {
            Color.black.opacity(0.95).ignoresSafeArea()
            VStack(spacing: 30) {
                VStack(spacing: 8) {
                    Text("SESSION SUMMARY")
                        .font(.system(size: 14, weight: .black))
                        .foregroundColor(.blue)
                        .tracking(3)
                    Text("\(deliveries.count) Deliveries Analyzed")
                        .font(.system(size: 28, weight: .black, design: .rounded))
                        .foregroundColor(.white)
                        .lineLimit(1)
                        .minimumScaleFactor(0.5)
                }
                .padding(.top, 60)
                
                ScrollView(.vertical, showsIndicators: false) {
                    VStack(spacing: 20) {
                        ForEach(deliveries) { delivery in
                            HStack(spacing: 20) {
                                if let url = delivery.videoURL {
                                    InteractiveClipPlayer(url: url, thumbnail: delivery.thumbnail, isActive: false)
                                        .frame(width: 100, height: 100)
                                        .cornerRadius(16)
                                }
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("DELIVERY #\(delivery.sequence)")
                                        .font(.caption)
                                        .bold()
                                        .foregroundColor(.gray)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.7)
                                    Text(delivery.speed ?? "Calculating...")
                                        .font(.title2)
                                        .bold()
                                        .foregroundColor(.blue)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.7)
                                }
                                Spacer()
                                Image(systemName: "chevron.right")
                                    .foregroundColor(.gray)
                            }
                            .padding(16)
                            .background(Color.white.opacity(0.05))
                            .cornerRadius(24)
                        }
                    }
                    .padding(.horizontal, 24)
                }
                
                Button(action: onReset) {
                    Text("START NEW SESSION")
                        .font(.system(size: 16, weight: .black))
                        .foregroundColor(.black)
                        .frame(maxWidth: UIDevice.current.userInterfaceIdiom == .pad ? 400 : .infinity)
                        .padding(.vertical, 20)
                        .background(Color.white)
                        .cornerRadius(20)
                }
                .padding(.horizontal, UIDevice.current.userInterfaceIdiom == .pad ? 60 : 40)
                .padding(.bottom, 40)
            }
            .frame(maxWidth: UIDevice.current.userInterfaceIdiom == .pad ? 600 : .infinity)
        }
    }
}

extension View { func cornerRadius(_ radius: CGFloat, corners: UIRectCorner) -> some View { clipShape( RoundedCorner(radius: radius, corners: corners) ) } }
struct RoundedCorner: Shape {
    var radius: CGFloat = .infinity; var corners: UIRectCorner = .allCorners
    func path(in rect: CGRect) -> Path { let path = UIBezierPath(roundedRect: rect, byRoundingCorners: corners, cornerRadii: CGSize(width: radius, height: radius)); return Path(path.cgPath) }
}

// MARK: - Analysis Hub Components

struct StreamingLogView: View {
    let logs: [StreamingEvent]
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Circle().fill(DesignSystem.Colors.primary).frame(width: 6, height: 6)
                Text("LIVE ENGINE TELEMETRY")
                    .font(.system(size: 10, weight: .black))
                    .foregroundColor(DesignSystem.Colors.primary)
                    .tracking(2)
                Spacer()
                if !logs.isEmpty {
                    Text("ACTIVE FEED")
                        .font(.system(size: 8, weight: .black))
                        .foregroundColor(DesignSystem.Colors.accent)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(DesignSystem.Colors.accent.opacity(0.1))
                        .cornerRadius(4)
                }
            }
            
            if logs.isEmpty {
                Text("WAITING FOR CORE SYSTEM SYNC...")
                    .font(.system(size: 10, weight: .bold, design: .monospaced))
                    .foregroundColor(.white.opacity(0.2))
                    .padding(.bottom, 12)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: 6) {
                            ForEach(logs) { log in
                                HStack(alignment: .top, spacing: 10) {
                                    Text("\(log.timestamp.formatted(.dateTime.hour().minute().second()))")
                                        .font(.system(size: 8, design: .monospaced))
                                        .foregroundColor(.white.opacity(0.3))
                                    
                                    Text(log.message.uppercased())
                                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                                        .foregroundColor(log.type == "error" ? .red.opacity(0.8) : .white.opacity(0.7))
                                }
                                .id(log.id)
                            }
                        }
                        .padding(.bottom, 12)
                    }
                    .frame(height: 80)
                    .onChange(of: logs.count) { oldValue, newValue in
                        withAnimation { proxy.scrollTo(logs.last?.id) }
                    }
                }
            }
        }
        .padding(16)
        // Advanced Glassmorphism
        .background(.ultraThinMaterial.opacity(0.5))
        .cornerRadius(20)
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.white.opacity(0.1), lineWidth: 0.5))
    }
}

struct UploadBackgroundView: View {
    @State private var animate = false
    
    var body: some View {
        ZStack {
            DesignSystem.Colors.background.ignoresSafeArea()
            
            // Dynamic Floating Orbs with Premium Colors
            ZStack {
                OrbitingOrb(color: DesignSystem.Colors.primary.opacity(0.2), size: 450, offset: animate ? 120 : -120)
                OrbitingOrb(color: DesignSystem.Colors.secondary.opacity(0.15), size: 350, offset: animate ? -180 : 180)
                
                // Add a third subtle orb for more depth
                Circle()
                    .fill(DesignSystem.Colors.accent.opacity(0.05))
                    .frame(width: 300, height: 300)
                    .offset(x: animate ? 50 : -50, y: animate ? -200 : 200)
            }
            .blur(radius: 90)
            .onAppear {
                withAnimation(.easeInOut(duration: 10).repeatForever(autoreverses: true)) {
                    animate.toggle()
                }
            }
            
            // Subtle Grid Overlay
            VStack {
                ForEach(0..<20) { _ in
                    HStack {
                        ForEach(0..<10) { _ in
                            Circle().fill(Color.white.opacity(0.02)).frame(width: 1, height: 1)
                            Spacer()
                        }
                    }
                    Spacer()
                }
            }
            .padding(40)
            .ignoresSafeArea()
        }
    }
}
struct OrbitingOrb: View {
    let color: Color; let size: CGFloat; let offset: CGFloat
    var body: some View {
        Circle()
        .fill(color)
        .frame(width: size, height: size)
        .offset(x: offset, y: -offset * 0.5)
    }
}

struct RecordingIndicatorView: View {
    let duration: TimeInterval
    @State private var pulse = false
    
    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(DesignSystem.Colors.error)
                .frame(width: 8, height: 8)
                .opacity(pulse ? 0.3 : 1.0)
                .onAppear {
                    withAnimation(.easeInOut(duration: 1).repeatForever(autoreverses: true)) {
                        pulse = true
                    }
                }
            
            Text(formatDuration(duration))
                .font(.system(size: 14, weight: .bold, design: .monospaced))
                .foregroundColor(.white)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.4))
        .clipShape(Capsule())
        .overlay(Capsule().stroke(Color.white.opacity(0.1), lineWidth: 1))
    }
    
    private func formatDuration(_ duration: TimeInterval) -> String {
        let mins = Int(duration) / 60
        let secs = Int(duration) % 60
        return String(format: "%02d:%02d", mins, secs)
    }
}

