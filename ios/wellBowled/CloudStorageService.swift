import Foundation

protocol CloudStorageServiceProtocol: Sendable {
    /// Uploads a local file to GCS via the backend and returns the public/signed URL.
    func upload(fileURL: URL, delivery: Delivery) async throws -> (video: URL, thumb: URL)
    
    /// Lists recent deliveries from the 'wellbowled-clips' bucket.
    func listRecentDeliveries() async throws -> [Delivery]
}

actor CloudStorageService: CloudStorageServiceProtocol {
    nonisolated static let shared = CloudStorageService()
    
    // Simulate latency for mock paths
    private let latency: TimeInterval = 0.5
    
    func upload(fileURL: URL, delivery: Delivery) async throws -> (video: URL, thumb: URL) {
        print("☁️ [Cloud] Initiating real upload to backend for GCS storage...")
        let result = try await CompositeNetworkService.shared.uploadClip(fileURL: fileURL, delivery: delivery)
        return (result.videoURL, result.thumbURL)
    }
    
    func listRecentDeliveries() async throws -> [Delivery] {
        // This would typically hit a GET /deliveries endpoint on the backend
        try await Task.sleep(nanoseconds: UInt64(latency * 1_000_000_000))
        return []
    }
}
