import SwiftUI

struct DesignSystem {
    struct Colors {
        // Deep Obsidian Base
        static let background = Color(hex: "050510")
        static let surface = Color(hex: "1C1C2D").opacity(0.8)
        
        // Electric Accents
        static let primary = Color(hex: "00E5FF") // Electric Cyan
        static let secondary = Color(hex: "BD00FF") // Plasma Purple
        static let accent = Color(hex: "39FF14") // Neon Green
        
        // Semantic
        static let error = Color(hex: "FF3B30")
        static let warning = Color(hex: "FFCC00")
        static let success = Color(hex: "34C759")
        
        static let glassBackground = Color.white.opacity(0.12)
        static let glassBorder = Color.white.opacity(0.18)
    }
    
    struct Gradients {
        static let main = LinearGradient(
            colors: [Colors.primary, Colors.secondary],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        
        static let darkOverlay = LinearGradient(
            colors: [.black.opacity(0.8), .clear],
            startPoint: .top,
            endPoint: .bottom
        )
    }
    
    struct Layout {
        static let standardPadding: CGFloat = 20
        static let compactPadding: CGFloat = 12
        static let detailPadding: CGFloat = 24
        
        static let cornerRadius: CGFloat = 24
        static let innerRadius: CGFloat = 16
        
        static let headerHeight: CGFloat = 120
    }
    
    struct Modifiers {
        struct PremiumGlass: ViewModifier {
            func body(content: Content) -> some View {
                content
                    .background(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 24)
                            .stroke(Colors.glassBorder, lineWidth: 1)
                    )
                    .cornerRadius(24)
                    .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
            }
        }
    }
}

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3: // RGB (12-bit)
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6: // RGB (24-bit)
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8: // ARGB (32-bit)
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (1, 1, 1, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

extension View {
    func premiumGlass() -> some View {
        self.modifier(DesignSystem.Modifiers.PremiumGlass())
    }
}
