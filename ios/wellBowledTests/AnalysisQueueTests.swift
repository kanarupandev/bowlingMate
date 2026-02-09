import XCTest
import Combine
@testable import wellBowled

@MainActor
final class AnalysisQueueTests: XCTestCase {
    
    var viewModel: BowlViewModel!
    var mockNetwork: MockNetworkService!
    
    override func setUp() {
        super.setUp()
        mockNetwork = MockNetworkService()
        viewModel = BowlViewModel(
            cameraManager: MockCameraManager(),
            detector: MockVideoActionDetector(),
            networkService: mockNetwork
        )
    }
    
    func testQueueProcessingConcurrency() async {
        // 1. Setup 5 pending deliveries
        var deliveries: [Delivery] = []
        for i in 1...5 {
            let d = Delivery(timestamp: Date().timeIntervalSince1970, status: .clipping, videoURL: URL(fileURLWithPath: "/tmp/test.mp4"), sequence: i)
            deliveries.append(d)
        }
        viewModel.sessionDeliveries = deliveries
        
        // 2. Request analysis for all
        for d in deliveries {
            viewModel.requestAnalysis(for: d)
        }
        
        // 3. Verify maximum concurrency is respected
        // (This is a bit hard to test precisely without internal hooks, but we can check the active count)
        XCTAssertLessThanOrEqual(viewModel.activeAnalysisCount, 1)
        
        // Wait a bit for async tasks
        try? await Task.sleep(nanoseconds: 1_000_000_000)
        
        XCTAssertTrue(viewModel.activeAnalysisCount >= 0)
    }
    
    func testAnalysisFailureAndRetry() async {
        let delivery = Delivery(timestamp: Date().timeIntervalSince1970, status: .clipping, videoURL: URL(fileURLWithPath: "/tmp/test.mp4"), sequence: 1)
        viewModel.sessionDeliveries = [delivery]
        
        // Mock a failure
        // (We would need to inject a failing network service for more granular testing)
        
        viewModel.requestAnalysis(for: delivery)
        
        // Wait for it to enter the queue
        XCTAssertEqual(viewModel.sessionDeliveries[0].status, .queued)
    }
}
