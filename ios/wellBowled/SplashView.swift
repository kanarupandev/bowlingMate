import SwiftUI

struct SplashView: View {
    @State private var isAnimating = false
    @State private var showTagline = false
    @State private var pulseScale: CGFloat = 1.0
    
    var body: some View {
        ZStack {
            // Premium dark gradient background
            LinearGradient(
                colors: [
                    Color(red: 0.05, green: 0.05, blue: 0.08),
                    Color(red: 0.08, green: 0.06, blue: 0.12),
                    Color.black
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()
            
            // Subtle animated particles
            GeometryReader { geo in
                ForEach(0..<6, id: \.self) { i in
                    Circle()
                        .fill(
                            RadialGradient(
                                colors: [Color.blue.opacity(0.3), Color.clear],
                                center: .center,
                                startRadius: 0,
                                endRadius: 50
                            )
                        )
                        .frame(width: 100, height: 100)
                        .offset(
                            x: isAnimating ? geo.size.width * CGFloat.random(in: 0.1...0.9) : geo.size.width * 0.5,
                            y: isAnimating ? geo.size.height * CGFloat.random(in: 0.2...0.8) : geo.size.height * 0.5
                        )
                        .blur(radius: 30)
                        .opacity(isAnimating ? 0.6 : 0)
                }
            }
            
            VStack(spacing: 30) {
                // Logo with pulse animation
                ZStack {
                    // Outer glow ring
                    Circle()
                        .stroke(
                            LinearGradient(
                                colors: [Color.blue.opacity(0.5), Color.purple.opacity(0.3)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: 3
                        )
                        .frame(width: 140, height: 140)
                        .scaleEffect(pulseScale)
                        .opacity(2 - pulseScale)
                    
                    // Inner circle with icon
                    Circle()
                        .fill(
                            LinearGradient(
                                colors: [Color.blue, Color.purple],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 120, height: 120)
                        .shadow(color: Color.blue.opacity(0.5), radius: 20, x: 0, y: 10)
                    
                    // Cricket ball icon
                    Image("wellbowled_logo")
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 80, height: 80)
                        .clipShape(Circle())
                        .rotationEffect(.degrees(isAnimating ? 360 : 0))
                }
                .scaleEffect(isAnimating ? 1 : 0.5)
                .opacity(isAnimating ? 1 : 0)
                
                // App name
                VStack(spacing: 8) {
                    Text("WELL BOWLED")
                        .font(.system(size: 34, weight: .black, design: .rounded))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [.white, .white.opacity(0.8)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .tracking(4)
                        .opacity(isAnimating ? 1 : 0)
                        .offset(y: isAnimating ? 0 : 20)
                    
                    // Tagline
                    Text("AI-Powered Bowling Analysis")
                        .font(.system(size: 14, weight: .medium, design: .rounded))
                        .foregroundColor(.white.opacity(0.6))
                        .opacity(showTagline ? 1 : 0)
                        .offset(y: showTagline ? 0 : 10)
                }
                
                // Loading indicator
                VStack(spacing: 12) {
                    // Custom loading dots
                    HStack(spacing: 8) {
                        ForEach(0..<3, id: \.self) { i in
                            Circle()
                                .fill(Color.blue)
                                .frame(width: 8, height: 8)
                                .scaleEffect(isAnimating ? 1.2 : 0.8)
                                .animation(
                                    Animation.easeInOut(duration: 0.6)
                                        .repeatForever(autoreverses: true)
                                        .delay(Double(i) * 0.2),
                                    value: isAnimating
                                )
                        }
                    }
                    
                    Text("Initializing camera...")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(.white.opacity(0.4))
                }
                .padding(.top, 40)
                .opacity(showTagline ? 1 : 0)
            }
        }
        .onAppear {
            // Staggered animations
            withAnimation(.spring(response: 0.8, dampingFraction: 0.7)) {
                isAnimating = true
            }
            
            withAnimation(.easeOut(duration: 0.5).delay(0.4)) {
                showTagline = true
            }
            
            // Pulse animation
            withAnimation(.easeInOut(duration: 1.5).repeatForever(autoreverses: false)) {
                pulseScale = 1.8
            }
        }
    }
}

#Preview {
    SplashView()
}
