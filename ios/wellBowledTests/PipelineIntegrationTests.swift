import XCTest
import AVFoundation
@testable import wellBowled

@MainActor
final class PipelineIntegrationTests: XCTestCase {
    
    var viewModel: BowlViewModel!
    var mockNetwork: MockNetworkService!
    var mockDetector: MockVideoActionDetector!
    
    override func setUp() {
        super.setUp()
        mockNetwork = MockNetworkService()
        mockDetector = MockVideoActionDetector()
        viewModel = BowlViewModel(
            cameraManager: MockCameraManager(),
            detector: mockDetector,
            networkService: mockNetwork
        )
    }
    
    func testProcessVideoSourceCreatesDelivery() async {
        // Mock detector to return a found delivery at 5 seconds
        mockDetector.mockResult = 5.0
        
        let dummyURL = URL(fileURLWithPath: "/tmp/integration_test.mp4")
        
        // Trigger pipeline
        viewModel.processVideoSource(url: dummyURL, isSegment: false, timeOffset: 0)
        
        // Wait for async task to process (using a reasonably safe timeout)
        let expectation = XCTestExpectation(description: "Pipeline processes video and creates delivery")
        
        // Poll for delivery creation
        var found = false
        for _ in 1...20 {
            if self.viewModel.sessionDeliveries.count > 0 {
                found = true
                expectation.fulfill()
                break
            }
            try? await Task.sleep(nanoseconds: 200_000_000) // 0.2s poll
        }
        
        XCTAssertTrue(found, "Pipeline should have created at least one delivery card")
        XCTAssertEqual(viewModel.sessionDeliveries.count, 1)
        XCTAssertEqual(viewModel.sessionDeliveries.first?.sequence, 1)
    }
}

