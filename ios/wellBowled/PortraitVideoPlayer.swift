import SwiftUI
import AVKit

// MARK: - Portrait Video Player (No manual rotation — VideoPlayer handles preferredTransform)
struct PortraitVideoPlayer: View {
    let url: URL
    @Binding var player: AVPlayer?
    var isPlaying: Binding<Bool>?

    @State private var looper: AVPlayerLooper?

    init(url: URL, player: Binding<AVPlayer?>, isPlaying: Binding<Bool>? = nil) {
        self.url = url
        self._player = player
        self.isPlaying = isPlaying
    }

    var body: some View {
        GeometryReader { geo in
            ZStack {
                Color.black

                if let player = player {
                    VideoPlayer(player: player)
                        .aspectRatio(contentMode: .fit)
                        .clipped()
                }
            }
        }
        .onAppear { setupPlayer() }
        .onDisappear { cleanupPlayer() }
        .onChange(of: isPlaying?.wrappedValue) { _, playing in
            if let playing = playing {
                playing ? player?.play() : player?.pause()
            }
        }
    }

    private func setupPlayer() {
        guard player == nil else { return }

        let asset = AVAsset(url: url)
        let item = AVPlayerItem(asset: asset)
        let queuePlayer = AVQueuePlayer(playerItem: item)
        looper = AVPlayerLooper(player: queuePlayer, templateItem: item)
        queuePlayer.isMuted = true

        print("🎥 [PortraitPlayer] Setting up player for: \(url.lastPathComponent)")

        if isPlaying?.wrappedValue ?? true {
            queuePlayer.play()
        }
        player = queuePlayer
    }

    private func cleanupPlayer() {
        print("🎥 [PortraitPlayer] Cleaning up player for: \(url.lastPathComponent)")
        player?.pause()
        player = nil
        looper = nil
    }
}
