import Foundation
import AVFoundation

struct AppConfig {
    // Cloud Run (Production) - Use this for iPhone testing
    static let cloudRunURL = "https://wellbowled-506790672773.us-central1.run.app"
    
    // Local Dev (Optional) - For when running backend locally
    static let localBackendHost = "192.168.1.102"
    static let localBackendPort = "8000"
    
    // Toggle: true = Cloud Run, false = Local
    static let useCloudRun = true
    
    static var baseURL: String {
        if useCloudRun {
            return cloudRunURL
        } else {
            return "http://\(localBackendHost):\(localBackendPort)"
        }
    }
    
    // UI Feature Flags
    static let showEngineTelemetry = false // Disabled for production
    
    // Security - Bearer Token Authentication
    // In production, this would come from secure storage (Keychain) after login
    static let apiSecret = "wellbowled-hackathon-secret"
    static var authToken: String { apiSecret }  // Alias for clarity
    static var bearerHeader: String { "Bearer \(authToken)" }
    
    // MOCKING (Granular Toggles)
    static let useMockDetection = false // Set to FALSE for REAL scouting
    static let useMockAnalysis = false  // Set to FALSE for REAL coaching
    static let useMockChat = true       // TRUE for demo (mock has video control)
    
    // Detection Accuracy
    static let deduplicationThreshold: Double = 2.0 // Seconds to ignore nearby detections
    
    // Performance Tuning (2026 Fleet)
    // NOTE: Primary goal of optimization is reducing "Time to First Card"
    static let maxScoutingConcurrency = 5 // Parallel chunk processing
}

struct ClipConfig {
    // Chunk size: 120s for bulk processing (File API handles large files)
    static let chunkDuration: Double = 120.0  // 2 minutes for bulk processing
    static let preRoll: Double = 3.0  // -3 seconds
    static let postRoll: Double = 2.0 // +2 seconds

    static var totalDuration: Double {
        return preRoll + postRoll
    }

    static let chunkOverlap: Double = 2.5  // Overlap to catch bowling actions at boundaries
    static var chunkStep: Double {
        return chunkDuration - chunkOverlap
    }

    // MARK: - Export Presets (Performance Tweak Knobs)

    // 1. Scout Phase (Detection): 640x480 hardware accelerated (~3MB per 120s chunk)
    // Compresses heavily - only needs to SEE action, not HD quality
    // Keeps under Cloud Run 32MB limit while staying small for fast upload
    static let scoutExportPreset: String = AVAssetExportPreset640x480

    // 2. Analysis Phase (Coach): 640x480 compressed for fast upload/analysis.
    // Passthrough was too slow (20-50MB for 5s 4K clip).
    // 640x480 keeps visual essence (~1-2MB) while enabling fast Coach analysis.
    static let analysisExportPreset: String = AVAssetExportPreset640x480
}
