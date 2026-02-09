import XCTest
@testable import wellBowled

final class NetworkServiceTests: XCTestCase {
    
    var mockService: MockNetworkService!
    
    override func setUp() {
        super.setUp()
        mockService = MockNetworkService()
    }
    
    func testDetectActionMockSuccess() async throws {
        let dummyURL = URL(fileURLWithPath: "/tmp/chunk.mp4")
        let result = try await mockService.detectAction(videoChunkURL: dummyURL)
        
        XCTAssertTrue(result.found)
        XCTAssertGreaterThan(result.deliveries_detected_at_time.count, 0)
        XCTAssertEqual(result.total_count, result.deliveries_detected_at_time.count)
    }
    
    func testAnalyzeVideoMockSuccess() async throws {
        let dummyURL = URL(fileURLWithPath: "/tmp/delivery.mp4")
        let result = try await mockService.analyzeVideo(fileURL: dummyURL, config: "balanced", language: "en")
        
        XCTAssertEqual(result.speed_est, "138.5 km/h")
        XCTAssertTrue(result.report.contains("Excellent seam position"))
    }
    
    func testPrefetchUploadMockSuccess() async throws {
        let dummyURL = URL(fileURLWithPath: "/tmp/delivery.mp4")
        let videoID = try await mockService.prefetchUpload(videoURL: dummyURL, config: "balanced", language: "en")
        
        XCTAssertTrue(videoID.contains("mock-video-id"))
    }
}
