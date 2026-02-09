import SwiftUI
import AVKit

struct CoachingFeedView: View {
    @ObservedObject var viewModel: BowlViewModel
    @Binding var selectedDeliveryID: UUID?
    
    // Sort deliveries by sequence (most recent last, or first? usually feeds act like TikTok)
    // Let's assume we want to scroll through them all.
    
    var body: some View {
        ZStack {
            // Background
            Color.black.ignoresSafeArea()
            
            GeometryReader { geometry in
                if let selectedID = selectedDeliveryID,
                   let startIndex = viewModel.sessionDeliveries.firstIndex(where: { $0.id == selectedID }) {

                    TabView(selection: $selectedDeliveryID) {
                        ForEach(viewModel.sessionDeliveries) { delivery in
                            DeliveryReelItem(delivery: delivery, onClose: {
                                withAnimation {
                                    selectedDeliveryID = nil
                                }
                            }, onHome: {
                                withAnimation {
                                    selectedDeliveryID = nil
                                    viewModel.uiMode = .live
                                }
                            }, onAnalyze: {
                                viewModel.requestAnalysis(for: delivery)
                            })
                            .tag(Optional(delivery.id))
                            .rotationEffect(.degrees(-90)) // Counter-rotate the content
                            .frame(width: geometry.size.width, height: geometry.size.height)
                        }
                    }
                    .rotationEffect(.degrees(90)) // Rotate the TabView to be vertical
                    // A vertical TabView requires rotation trick or iOS 17 .scrollTargetBehavior(.paging) in ScrollView.
                    // Let's use the Rotation Trick for compatibility and snap feel.
                    .frame(width: geometry.size.height, height: geometry.size.width)
                    .tabViewStyle(PageTabViewStyle(indexDisplayMode: .never))
                    .ignoresSafeArea()
                }
            }
        }
    }
}

struct DeliveryReelItem: View {
    let delivery: Delivery
    var onClose: () -> Void
    var onHome: () -> Void
    var onAnalyze: () -> Void

    @State private var showFeedback = false

    var body: some View {
        GeometryReader { geometry in
            let topSafeArea = geometry.safeAreaInsets.top
            let bottomSafeArea = geometry.safeAreaInsets.bottom

            ZStack(alignment: .bottom) {
                // Layer 0: Full Screen Video
                if let url = delivery.videoURL {
                    FullScreenLoopPlayer(url: url)
                        .ignoresSafeArea()
                } else if let thumb = delivery.thumbnail {
                    Image(uiImage: thumb)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .ignoresSafeArea()
                } else {
                    Color.black.ignoresSafeArea()
                }

                // Layer 1: Overlays (Ready for Drawing)
                VisualOverlayView(delivery: delivery)
                    .allowsHitTesting(false) // Let touches pass to gestures

                // Layer 2: HUD
                VStack {
                    // Top HUD - Navigation
                    HStack(alignment: .top) {
                        // Back (Close)
                        Button(action: onClose) {
                            Image(systemName: "chevron.left")
                                .font(.system(size: 20, weight: .bold))
                                .foregroundColor(.white)
                                .padding(12)
                                .background(Color.black.opacity(0.4))
                                .clipShape(Circle())
                        }

                        Spacer()

                        // Home
                        Button(action: onHome) {
                            Image(systemName: "house.fill")
                                .font(.system(size: 18, weight: .bold))
                                .foregroundColor(.white)
                                .padding(12)
                                .background(Color.black.opacity(0.4))
                                .clipShape(Circle())
                        }
                    }
                    .padding(.top, max(topSafeArea + 10, 50)) // Respects Dynamic Island/notch
                    .padding(.horizontal, 20)
                
                // Bowl Info Badge (Float below Nav)
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("BOWL #\(delivery.sequence)")
                            .font(.system(size: 16, weight: .black, design: .monospaced))
                            .foregroundColor(.white)
                            .shadow(color: .black.opacity(0.5), radius: 2, x: 0, y: 1)
                        
                        // Show speed here only if NOT yet analyzed fully or if customized
                        // But user wants results to replace button.
                    }
                    Spacer()
                }
                .padding(.horizontal, 20)
                .padding(.top, 10)
                
                Spacer()
                
                // MAIN INTERACTION AREA
                VStack(alignment: .leading, spacing: 12) {
                    
                    if delivery.status == .success && delivery.speed == nil {
                        // STATE: READY TO ANALYZE
                        // Show Analyze Button Overlay (Bottom Right)
                        HStack {
                            Spacer()
                            Button(action: onAnalyze) {
                                Image(systemName: "wand.and.stars")
                                    .font(.system(size: 24, weight: .bold))
                                    .foregroundColor(.black) 
                                    .padding(20)
                                    .background(DesignSystem.Colors.primary)
                                    .clipShape(Circle())
                                    .shadow(color: DesignSystem.Colors.primary.opacity(0.6), radius: 12, x: 0, y: 0)
                                    .overlay(
                                        Circle()
                                            .stroke(Color.white.opacity(0.5), lineWidth: 2)
                                    )
                            }
                            .padding(.bottom, 20)
                            .padding(.trailing, 20)
                            .help("Analyze Bowling")
                            .accessibilityLabel("Analyze Bowling")
                        }
                    } else if [.queued, .analyzing, .uploading, .processing].contains(delivery.status) {
                         // STATE: ANALYZING
                         HStack(spacing: 12) {
                             ProgressView().tint(.white)
                             Text("ANALYZING...")
                                 .font(.system(size: 14, weight: .bold, design: .monospaced))
                                 .foregroundColor(.white)
                         }
                         .padding()
                         .background(.ultraThinMaterial)
                         .cornerRadius(12)
                         .padding(.bottom, 40)
                         .frame(maxWidth: .infinity)
                         
                    } else if let speed = delivery.speed {
                        // STATE: RESULTS (Replaces Analyze Button)
                        // This uses the space where the button was (or bottom drawer style)
                        VStack(alignment: .leading, spacing: 12) {
                             HStack {
                                Text(speed)
                                    .font(.system(size: 32, weight: .black, design: .rounded))
                                    .foregroundColor(DesignSystem.Colors.primary)
                                    .shadow(color: .black, radius: 2)
                                Spacer()
                             }
                             
                             if let topTip = delivery.tips.first {
                                 HStack(alignment: .top, spacing: 10) {
                                     Image(systemName: "sparkles")
                                         .foregroundColor(DesignSystem.Colors.primary)
                                         .padding(.top, 2)
                                     Text(topTip)
                                         .font(.system(size: 16, weight: .bold))
                                         .foregroundColor(.white)
                                         .lineLimit(3)
                                 }
                             }
                             
                             Button(action: { showFeedback.toggle() }) {
                                 HStack {
                                     Text("View Full Breakdown")
                                     Image(systemName: "chevron.up")
                                 }
                                 .font(.system(size: 14, weight: .bold))
                                 .foregroundColor(.white.opacity(0.8))
                                 .padding(.top, 8)
                             }
                        }
                        .padding(24)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            LinearGradient(
                                colors: [.black.opacity(0.9), .black.opacity(0.0)],
                                startPoint: .bottom,
                                endPoint: .top
                            )
                        )
                    }
                }
                }
            }
        }
        .sheet(isPresented: $showFeedback) {
            CoachingFeedbackSheet(delivery: delivery)
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
    }
}

struct FullScreenLoopPlayer: View {
    let url: URL
    @State private var looper: AVPlayerLooper?
    @State private var player: AVQueuePlayer?
    
    var body: some View {
        VideoPlayerView(player: player)
            .onAppear {
                let asset = AVAsset(url: url)
                let playerItem = AVPlayerItem(asset: asset)
                let queuePlayer = AVQueuePlayer(playerItem: playerItem)
                looper = AVPlayerLooper(player: queuePlayer, templateItem: playerItem)
                queuePlayer.play()
                self.player = queuePlayer
            }
            .onDisappear {
                player?.pause()
                player = nil
                looper = nil
            }
    }
}

// UIKit wrapper for AVPlayerLayer to get ASPECT FILL
struct VideoPlayerView: UIViewRepresentable {
    let player: AVPlayer?
    
    func makeUIView(context: Context) -> UIView {
        let view = PlayerUIView(player: player)
        return view
    }
    
    func updateUIView(_ uiView: UIView, context: Context) {
        if let playerView = uiView as? PlayerUIView {
            playerView.playerLayer.player = player
        }
    }
    
    // Internal UIView subclass to handle layout properly
    private class PlayerUIView: UIView {
        let playerLayer = AVPlayerLayer()
        
        init(player: AVPlayer?) {
            super.init(frame: .zero)
            playerLayer.player = player
            playerLayer.videoGravity = .resizeAspectFill
            layer.addSublayer(playerLayer)
        }
        
        required init?(coder: NSCoder) {
            fatalError("init(coder:) has not been implemented")
        }
        
        override func layoutSubviews() {
            super.layoutSubviews()
            playerLayer.frame = bounds
        }
    }
}

struct VisualOverlayView: View {
    let delivery: Delivery
    
    // Future: Use Path to draw lines based on [VNHumanBodyPoseObservation] data if stored
    
    var body: some View {
        GeometryReader { _ in
            ZStack {
                // Example: Central Focus Reticle (Static for now)
                
                // If we had joint data, we would draw it here. 
                // For now, we leave it clear so the video is visible.
                Color.clear
            }
        }
    }
}

struct CoachingFeedbackSheet: View {
    let delivery: Delivery
    
    var body: some View {
        ZStack {
            DesignSystem.Colors.background.ignoresSafeArea()
            
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Text("Coach's Breakdown")
                        .font(.system(size: 20, weight: .black))
                        .foregroundColor(.white)
                        .tracking(1)
                    
                    if delivery.status == .queued || delivery.status == .processing || delivery.status == .analyzing {
                        VStack(spacing: 16) {
                            ProgressView().tint(DesignSystem.Colors.accent)
                            Text("Analyzing biomechanics...")
                                .font(.system(size: 14, weight: .medium, design: .monospaced))
                                .foregroundColor(.white.opacity(0.6))
                        }
                        .frame(maxWidth: .infinity) // Center loading state
                        .allowsHitTesting(false)
                        .padding(.top, 40)
                    } else if delivery.report == nil && delivery.tips.isEmpty {
                         Text("No specific feedback generated for this delivery.")
                            .font(.system(size: 14))
                            .foregroundColor(.white.opacity(0.4))
                            .padding(.top, 20)
                    } else {
                        if let report = delivery.report {
                            VStack(alignment: .leading, spacing: 8) {
                                Text("SUMMARY")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundColor(.white.opacity(0.4))
                                Text(report)
                                    .font(.system(size: 14))
                                    .foregroundColor(.white.opacity(0.8))
                                    .lineSpacing(4)
                            }
                        }
                        
                        if !delivery.tips.isEmpty {
                            VStack(alignment: .leading, spacing: 12) {
                                Text("KEY ADJUSTMENTS")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundColor(.white.opacity(0.4))
                                
                                ForEach(delivery.tips, id: \.self) { tip in
                                    HStack(alignment: .top, spacing: 10) {
                                        Circle()
                                            .fill(DesignSystem.Colors.primary)
                                            .frame(width: 8, height: 8)
                                            .padding(.top, 5)
                                        Text(tip)
                                            .font(.system(size: 14, weight: .medium))
                                            .foregroundColor(.white)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                    .padding(.horizontal, 16)
                                    .padding(.vertical, 14)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.white.opacity(0.05))
                                    .cornerRadius(10)
                                }
                            }
                        }
                    }
                    
                    Spacer()
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 24)
            }
        }
    }
}
