import SwiftUI
import AVFoundation
import Combine

private let appLaunchTime = CACurrentMediaTime()

@main
struct wellBowledApp: App {
    @State private var isLoading = true
    @StateObject private var appState = AppLaunchState()
    
    var body: some Scene {
        WindowGroup {
            ZStack {
                if isLoading {
                    SplashView()
                        .transition(.opacity)
                } else {
                    ContentView()
                        .transition(.opacity)
                }
            }
            .animation(.easeInOut(duration: 0.5), value: isLoading)
            .onAppear {
                print("🚀 [PERF] [T0] App Launched at \(Date()). Reference time: \(appLaunchTime)")
                Task {
                    await appState.initialize()
                    try? await Task.sleep(nanoseconds: 800_000_000)
                    await MainActor.run {
                        isLoading = false
                    }
                }
            }
        }
    }
}

@MainActor
class AppLaunchState: ObservableObject {
    @Published var isReady = false
    
    func initialize() async {
        await AVCaptureDevice.requestAccess(for: .video)
        isReady = true
    }
}
