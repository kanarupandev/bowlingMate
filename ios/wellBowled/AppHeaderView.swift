import SwiftUI
import PhotosUI

struct HeaderView: View {
    let isRecording: Bool
    let uiMode: UIMode
    let hasActiveSession: Bool
    @Binding var selectedItem: PhotosPickerItem?
    var onBackTap: () -> Void
    var onHistoryTap: () -> Void
    var onFavoritesTap: () -> Void
    var onResumeSession: () -> Void
    let onSettingsTap: () -> Void
    
    @State private var heartbeatScale: CGFloat = 1.0
    
    var body: some View {
        HStack(spacing: 12) {
            // LEFT SIDE: BACK OR LOGO
            if uiMode != .live {
                Button(action: onBackTap) {
                    HeaderIcon(systemName: "chevron.left")
                }
                .transition(.move(edge: .leading).combined(with: .opacity))
            }
            
            VStack(alignment: .leading, spacing: 2) {
                Text(uiMode == .live ? "wellBowled" : (uiMode == .history ? "All Clips" : (uiMode == .favorites ? "Favorites" : "Analysis")))
                    .font(.system(size: 21, weight: .black, design: .rounded))
                    .foregroundStyle(DesignSystem.Gradients.main)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                
                HStack(spacing: 6) {
                    if uiMode == .live {
                        Circle()
                            .fill(isRecording ? DesignSystem.Colors.error : Color.white.opacity(0.3))
                            .frame(width: 6, height: 6)
                            .shadow(color: isRecording ? DesignSystem.Colors.error : .clear, radius: 4)
                        
                        Text(isRecording ? "SESSION LIVE" : "READY TO RECORD")
                            .font(.system(size: 9, weight: .black))
                            .foregroundColor(.white.opacity(0.6))
                            .tracking(1)
                    } else if uiMode == .history {
                        Image(systemName: "chart.line.uptrend.xyaxis")
                            .font(.system(size: 10))
                            .foregroundColor(DesignSystem.Colors.primary)
                        
                        Text("TRACK PROGRESS")
                            .font(.system(size: 9, weight: .black))
                            .foregroundColor(.white.opacity(0.6))
                            .tracking(1)
                    } else {
                        Image(systemName: "cpu.fill")
                            .font(.system(size: 10))
                            .foregroundColor(DesignSystem.Colors.primary)
                        
                        Text("FEEDBACK ON DEMAND")
                            .font(.system(size: 9, weight: .black))
                            .foregroundColor(.white.opacity(0.6))
                            .tracking(1)
                    }
                }
            }
            
            Spacer()
            
            // RIGHT SIDE: ACTION BUTTONS
            HStack(spacing: 12) {
                // Video Picker
                PhotosPicker(selection: $selectedItem, matching: .videos) {
                    HeaderIcon(systemName: "plus.viewfinder")
                }
                
                // Saved Clips
                if uiMode != .history {
                    Button(action: onHistoryTap) {
                        HeaderIcon(systemName: "clock.arrow.circlepath")
                    }
                    .transition(.scale.combined(with: .opacity))
                }
                
                // Analysis Heartbeat (Pulsing Sparkles)
                if hasActiveSession && uiMode != .upload {
                    Button(action: onResumeSession) {
                        HeaderIcon(systemName: "sparkles", isActive: true, color: DesignSystem.Colors.primary)
                            .scaleEffect(heartbeatScale)
                            .shadow(color: DesignSystem.Colors.primary.opacity(0.5), radius: heartbeatScale * 5)
                    }
                    .transition(.scale.combined(with: .opacity))
                    .onAppear {
                        withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) {
                            heartbeatScale = 1.2
                        }
                    }
                }
                
                // Favorites (NEW)
                if uiMode != .favorites {
                    Button(action: onFavoritesTap) {
                        HeaderIcon(systemName: "heart.fill", color: DesignSystem.Colors.secondary)
                    }
                    .transition(.scale.combined(with: .opacity))
                }
                
                // Settings
                Button(action: onSettingsTap) {
                    HeaderIcon(systemName: "terminal.fill")
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 24)
        .padding(.vertical, 14)
        .background(
            Color.black.opacity(0.4)
                .background(.ultraThinMaterial)
                .ignoresSafeArea()
        )
    }
}

// Helper for consistent header icons
struct HeaderIcon: View {
    let systemName: String
    var isActive: Bool = false
    var color: Color = .white // Added for thematic consistency (Favorites = Purple)
    
    var body: some View {
        Image(systemName: systemName)
            .font(.system(size: 16, weight: .bold))
            .foregroundColor(isActive ? DesignSystem.Colors.primary : color)
            .padding(10)
            .background(DesignSystem.Colors.glassBackground)
            .clipShape(Circle())
            .overlay(Circle().stroke(isActive ? DesignSystem.Colors.primary.opacity(0.5) : DesignSystem.Colors.glassBorder, lineWidth: 1))
    }
}
