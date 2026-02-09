import SwiftUI
import AVKit

struct DeliveryDetailView: View {
    let delivery: Delivery
    var onDismiss: () -> Void
    var onFavorite: (Delivery) -> Void
    
    @State private var player: AVPlayer?
    @State private var looper: AVPlayerLooper?
    @State private var isMuted = true
    
    var body: some View {
        ZStack {
            // 1. Full Screen Video Layer
            Color.black.ignoresSafeArea()
            
            if let url = delivery.videoURL {
                Group {
                    if let p = player {
                        CustomVideoPlayer(player: p)
                            .ignoresSafeArea()
                    } else {
                        Color.black.ignoresSafeArea()
                    }
                }
                .onAppear { setupPlayer(url: url) }
                .onDisappear { cleanupPlayer() }
            }
            
            // 2. Gradient Overlay for Readability
            VStack {
                LinearGradient(
                    colors: [.black.opacity(0.6), .clear],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 120)
                
                Spacer()
                
                LinearGradient(
                    colors: [.clear, .black.opacity(0.8)],
                    startPoint: .top,
                    endPoint: .bottom
                )
                .frame(height: 300)
            }
            .ignoresSafeArea()
            .allowsHitTesting(false)
            
            // 3. UI Controls & Data Layer
            GeometryReader { geometry in
                let topSafeArea = geometry.safeAreaInsets.top
                let bottomSafeArea = geometry.safeAreaInsets.bottom

                VStack(alignment: .leading) {
                    // Top Bar
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("DELIVERY #\(delivery.sequence)")
                                .font(.system(size: 14, weight: .black, design: .rounded))
                                .foregroundColor(.white)
                            if let date = delivery.timestamp as TimeInterval? {
                                Text("Captured at T+\(String(format: "%.1f", date))s")
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundColor(.white.opacity(0.6))
                            }
                        }

                        Spacer()

                        Button(action: {
                            onFavorite(delivery)
                        }) {
                             Image(systemName: delivery.isFavorite ? "heart.fill" : "heart")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(delivery.isFavorite ? DesignSystem.Colors.error : .white)
                                .padding(12)
                                .background(Color.black.opacity(0.4).blur(radius: 10))
                                .clipShape(Circle())
                                .overlay(Circle().stroke(Color.white.opacity(0.2), lineWidth: 1))
                        }


                        Button(action: onDismiss) {
                            Image(systemName: "xmark")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(.white)
                                .padding(12)
                                .background(Color.black.opacity(0.4).blur(radius: 10))
                                .clipShape(Circle())
                                .overlay(Circle().stroke(Color.white.opacity(0.2), lineWidth: 1))
                        }
                    }
                    .padding(.horizontal, 20)
                    .padding(.top, max(topSafeArea + 10, 50)) // Respects Dynamic Island/notch
                
                Spacer()
                
                // Bottom Info Panel
                VStack(alignment: .leading, spacing: 16) {
                    
                    // Metrics Grid
                    HStack(spacing: 24) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("SPEED")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(.white.opacity(0.6))
                            Text(delivery.speed ?? "--")
                                .font(.system(size: 32, weight: .black, design: .rounded))
                                .foregroundStyle(DesignSystem.Gradients.main)
                                .minimumScaleFactor(0.6)
                                .lineLimit(1)
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            Text("RELEASE")
                                .font(.system(size: 10, weight: .bold))
                                .foregroundColor(.white.opacity(0.6))
                            Text(String(format: "%.2fs", delivery.releaseTimestamp ?? 0.0))
                                .font(.system(size: 32, weight: .black, design: .rounded))
                                .foregroundColor(.white)
                                .minimumScaleFactor(0.6)
                                .lineLimit(1)
                        }
                        
                        Spacer()
                        
                        // Mute Toggle
                        Button(action: {
                            isMuted.toggle()
                            player?.isMuted = isMuted
                        }) {
                            Image(systemName: isMuted ? "speaker.slash.fill" : "speaker.wave.2.fill")
                                .font(.system(size: 16))
                                .foregroundColor(.white)
                                .padding(12)
                                .background(Color.white.opacity(0.1))
                                .clipShape(Circle())
                        }
                    }
                    
                    // Coach's Feedback
                    if !delivery.tips.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Image(systemName: "sparkles")
                                    .font(.system(size: 12))
                                    .foregroundColor(DesignSystem.Colors.accent)
                                Text("COACH'S ANALYSIS")
                                    .font(.system(size: 10, weight: .heavy))
                                    .foregroundColor(DesignSystem.Colors.accent)
                                    .tracking(1)
                            }
                            
                            ForEach(delivery.tips.prefix(2), id: \.self) { tip in
                                Text("• " + tip)
                                    .font(.system(size: 14, weight: .medium, design: .rounded))
                                    .foregroundColor(.white.opacity(0.9))
                                    .lineSpacing(4)
                            }
                        }
                        .padding(16)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(Color.white.opacity(0.08))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 16)
                                .stroke(Color.white.opacity(0.1), lineWidth: 1)
                        )
                    } else if let report = delivery.report {
                        // Fallback to report text if tips aren't parsed as list
                        Text(report)
                             .font(.system(size: 13))
                             .foregroundColor(.white.opacity(0.8))
                             .lineLimit(3)
                    }
                }
                .padding(.horizontal, 20)
                .padding(.bottom, max(bottomSafeArea + 16, 34)) // Respects home indicator
                }
            }
        }
        .edgesIgnoringSafeArea(.all)
    }
    
    private func setupPlayer(url: URL) {
        let asset = AVAsset(url: url)
        let playerItem = AVPlayerItem(asset: asset)
        let queuePlayer = AVQueuePlayer(playerItem: playerItem)
        
        // Zero-gap looping
        looper = AVPlayerLooper(player: queuePlayer, templateItem: playerItem)
        
        queuePlayer.isMuted = isMuted 
        queuePlayer.play()
        self.player = queuePlayer
    }
    
    private func cleanupPlayer() { 
        player?.pause()
        player = nil
        looper = nil 
    }
}

