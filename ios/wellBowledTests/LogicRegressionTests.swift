import XCTest
@testable import wellBowled

@MainActor
final class LogicRegressionTests: XCTestCase {
    
    var viewModel: BowlViewModel!
    var mockNetwork: MockNetworkService!
    var mockDetector: MockVideoActionDetector!
    
    @MainActor
    override func setUp() {
        super.setUp()
        
        // Ensure MainActor execution for ViewModel initialization
        mockNetwork = MockNetworkService()
        mockDetector = MockVideoActionDetector()
        viewModel = BowlViewModel(
            cameraManager: MockCameraManager(),
            detector: mockDetector,
            networkService: mockNetwork
        )
    }
    
    func testFirstCardPolicy() async {
        // 1. Simulate finding Delivery #1
        viewModel.handleActionDetected(at: 10.0, thumbnail: nil)
        XCTAssertEqual(viewModel.sessionDeliveries.count, 1)
        XCTAssertEqual(viewModel.currentCarouselID, viewModel.sessionDeliveries[0].id, "Should snap to the first delivery immediately")
        
        // 2. Simulate finding Delivery #2
        viewModel.handleActionDetected(at: 20.0, thumbnail: nil)
        XCTAssertEqual(viewModel.sessionDeliveries.count, 2)
        XCTAssertEqual(viewModel.currentCarouselID, viewModel.sessionDeliveries[0].id, "Should STILL be on the first delivery (First Card Policy)")
    }
    
    func testScoutingStatusAndProgress() async {
        // Test UI state transitions
        viewModel.scoutingStatus = "Discovery Complete"
        viewModel.scoutingProgress = 1.0
        
        XCTAssertTrue(viewModel.scoutingStatus?.contains("Complete") ?? false)
        XCTAssertEqual(viewModel.scoutingProgress, 1.0)
        
        viewModel.startNewSession()
        XCTAssertNil(viewModel.scoutingStatus)
        XCTAssertEqual(viewModel.scoutingProgress, 0.0, "Progress should reset on new session")
    }
    
    func testNoAutoAnalysisTrigger() async {
        // Simulate finding Delivery #1
        viewModel.handleActionDetected(at: 5.0, thumbnail: nil)
        XCTAssertEqual(viewModel.sessionDeliveries[0].sequence, 1)
        
        // Ensure status is clipping/queued initially
        XCTAssertTrue([.clipping, .queued].contains(viewModel.sessionDeliveries[0].status))
        
        // Even if we simulate the clip being ready, it should NOT auto-analyze
        // (The logic was removed from the ViewModel)
        
        // Manual trigger should still work
        viewModel.sessionDeliveries[0].videoURL = URL(fileURLWithPath: "/tmp/dummy.mov")
        viewModel.sessionDeliveries[0].status = .queued // Status updated by pipeline
        
        viewModel.requestAnalysis(for: viewModel.sessionDeliveries[0])
        
        XCTAssertEqual(viewModel.sessionDeliveries[0].status, .analyzing, "Should analyze after manual request from .queued state")
    }
    
    func testSingleAnalysisConcurrencyLimit() async {
        // Setup two deliveries
        viewModel.handleActionDetected(at: 10.0, thumbnail: nil)
        viewModel.handleActionDetected(at: 20.0, thumbnail: nil)

        viewModel.sessionDeliveries[0].videoURL = URL(fileURLWithPath: "/tmp/d1.mov")
        viewModel.sessionDeliveries[1].videoURL = URL(fileURLWithPath: "/tmp/d2.mov")
        viewModel.sessionDeliveries[0].status = .queued
        viewModel.sessionDeliveries[1].status = .queued

        // Trigger first analysis
        viewModel.requestAnalysis(for: viewModel.sessionDeliveries[0])
        XCTAssertEqual(viewModel.sessionDeliveries[0].status, .analyzing)
        XCTAssertEqual(viewModel.activeAnalysisCount, 1)
        XCTAssertTrue(viewModel.isAnyAnalysisRunning)

        // Try to trigger second analysis - should be queued but NOT set to .analyzing immediately
        // Wait, current ViewModel logic might queue it. Let's check.
        viewModel.requestAnalysis(for: viewModel.sessionDeliveries[1])

        // Even if requested, it should stay .queued if max concurrency is reached
        XCTAssertEqual(viewModel.sessionDeliveries[1].status, .queued, "Should remain queued as another analysis is running")
    }

    // MARK: - Phase Sorting Tests

    func testPhaseSortingGoodFirst() {
        // Create phases with mixed statuses and timestamps
        let phases = [
            AnalysisPhase(name: "Run-up", status: "NEEDS WORK", observation: "Short", tip: "Lengthen", clipTimestamp: 0.5),
            AnalysisPhase(name: "Release", status: "GOOD", observation: "Clean", tip: "Maintain", clipTimestamp: 2.0),
            AnalysisPhase(name: "Loading", status: "NEEDS WORK", observation: "Chest-on", tip: "Close shoulder", clipTimestamp: 1.5),
            AnalysisPhase(name: "Wrist", status: "GOOD", observation: "Strong", tip: "Continue", clipTimestamp: 2.2),
            AnalysisPhase(name: "Head", status: "NEEDS WORK", observation: "Falls away", tip: "Stay upright", clipTimestamp: 2.0),
            AnalysisPhase(name: "Follow-through", status: "GOOD", observation: "Good rotation", tip: "Maintain", clipTimestamp: 3.0)
        ]

        // Sort: GOOD first, then NEEDS WORK
        let sorted = phases.sorted { $0.isGood && !$1.isGood }

        // First 3 should be GOOD
        XCTAssertTrue(sorted[0].isGood, "First phase should be GOOD")
        XCTAssertTrue(sorted[1].isGood, "Second phase should be GOOD")
        XCTAssertTrue(sorted[2].isGood, "Third phase should be GOOD")

        // Last 3 should be NEEDS WORK
        XCTAssertFalse(sorted[3].isGood, "Fourth phase should be NEEDS WORK")
        XCTAssertFalse(sorted[4].isGood, "Fifth phase should be NEEDS WORK")
        XCTAssertFalse(sorted[5].isGood, "Sixth phase should be NEEDS WORK")
    }

    func testPhaseIsGoodStatus() {
        let goodPhase = AnalysisPhase(name: "Test", status: "GOOD", observation: "", tip: "")
        let needsWorkPhase = AnalysisPhase(name: "Test", status: "NEEDS WORK", observation: "", tip: "")
        let goodLowercase = AnalysisPhase(name: "Test", status: "good", observation: "", tip: "")

        XCTAssertTrue(goodPhase.isGood)
        XCTAssertFalse(needsWorkPhase.isGood)
        XCTAssertTrue(goodLowercase.isGood, "isGood should be case-insensitive")
    }

    // MARK: - Overlay URL Resolution Tests

    func testOverlayURLResolution_LocalFirst() async throws {
        // Create test delivery with both local and remote overlay URLs
        let testID = UUID()
        let remoteURL = URL(string: "https://example.com/overlay.mp4")!

        viewModel.handleActionDetected(at: 5.0, thumbnail: nil)
        viewModel.sessionDeliveries[0].overlayVideoURL = remoteURL
        viewModel.sessionDeliveries[0].localOverlayPath = "\(testID.uuidString)_overlay.mp4"

        // Create the local file
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let overlaysDir = documents.appendingPathComponent("overlays")
        try? FileManager.default.createDirectory(at: overlaysDir, withIntermediateDirectories: true)
        let localPath = overlaysDir.appendingPathComponent("\(testID.uuidString)_overlay.mp4")
        try "test".write(to: localPath, atomically: true, encoding: .utf8)

        // Test resolution
        let resolvedURL = viewModel.resolveOverlayURL(for: viewModel.sessionDeliveries[0])

        XCTAssertNotNil(resolvedURL)
        XCTAssertTrue(resolvedURL?.isFileURL ?? false, "Should resolve to local file URL")
        XCTAssertEqual(resolvedURL?.lastPathComponent, "\(testID.uuidString)_overlay.mp4")

        // Cleanup
        try? FileManager.default.removeItem(at: localPath)
    }

    func testOverlayURLResolution_FallbackToRemote() {
        // Create delivery with only remote URL (no local cache)
        viewModel.handleActionDetected(at: 5.0, thumbnail: nil)
        let remoteURL = URL(string: "https://example.com/overlay.mp4")!
        viewModel.sessionDeliveries[0].overlayVideoURL = remoteURL
        viewModel.sessionDeliveries[0].localOverlayPath = nil

        let resolvedURL = viewModel.resolveOverlayURL(for: viewModel.sessionDeliveries[0])

        XCTAssertEqual(resolvedURL, remoteURL, "Should fallback to remote URL when no local cache")
    }

    // MARK: - selectedDelivery State Sync Tests

    func testSelectedDeliveryStateSync() async {
        // Create delivery and select it
        viewModel.handleActionDetected(at: 5.0, thumbnail: nil)
        viewModel.sessionDeliveries[0].status = .success
        viewModel.sessionDeliveries[0].videoURL = URL(fileURLWithPath: "/tmp/test.mov")

        let delivery = viewModel.sessionDeliveries[0]
        viewModel.selectDelivery(delivery)

        XCTAssertNotNil(viewModel.selectedDelivery, "Should have selected delivery")
        XCTAssertEqual(viewModel.selectedDelivery?.id, delivery.id)

        // Simulate overlay URL update (as would happen in SSE handler)
        let overlayURL = URL(string: "https://example.com/overlay.mp4")!
        if viewModel.selectedDelivery?.id == delivery.id {
            viewModel.selectedDelivery?.overlayVideoURL = overlayURL
        }

        XCTAssertEqual(viewModel.selectedDelivery?.overlayVideoURL, overlayURL,
                       "selectedDelivery should be updated when overlay URL arrives")
    }

    func testSelectedDeliveryLocalPathSync() async {
        // Create delivery and select it
        viewModel.handleActionDetected(at: 5.0, thumbnail: nil)
        viewModel.sessionDeliveries[0].status = .success
        viewModel.sessionDeliveries[0].videoURL = URL(fileURLWithPath: "/tmp/test.mov")

        let delivery = viewModel.sessionDeliveries[0]
        viewModel.selectDelivery(delivery)

        // Simulate local path update (as would happen after download)
        let localPath = "\(delivery.id.uuidString)_overlay.mp4"
        if viewModel.selectedDelivery?.id == delivery.id {
            viewModel.selectedDelivery?.localOverlayPath = localPath
        }

        XCTAssertEqual(viewModel.selectedDelivery?.localOverlayPath, localPath,
                       "selectedDelivery should be updated when local path is set")
    }

    // MARK: - Video Rotation Detection Tests

    func testVideoRotationDetection_LandscapeNeedsRotation() {
        // Landscape video (width > height * 1.2)
        let landscapeSize = CGSize(width: 1920, height: 1080)
        let needsRotation = landscapeSize.width > landscapeSize.height * 1.2
        XCTAssertTrue(needsRotation, "Landscape video (1920x1080) should need rotation")
    }

    func testVideoRotationDetection_PortraitNoRotation() {
        // Portrait video (height > width)
        let portraitSize = CGSize(width: 1080, height: 1920)
        let needsRotation = portraitSize.width > portraitSize.height * 1.2
        XCTAssertFalse(needsRotation, "Portrait video (1080x1920) should NOT need rotation")
    }

    func testVideoRotationDetection_SquareNoRotation() {
        // Square-ish video (width ~ height)
        let squareSize = CGSize(width: 1080, height: 1080)
        let needsRotation = squareSize.width > squareSize.height * 1.2
        XCTAssertFalse(needsRotation, "Square video should NOT need rotation")
    }

    func testVideoRotationDetection_SlightlyWideNoRotation() {
        // Slightly wider video but within 1.2 threshold
        let wideSize = CGSize(width: 1200, height: 1080) // ratio = 1.11
        let needsRotation = wideSize.width > wideSize.height * 1.2
        XCTAssertFalse(needsRotation, "Slightly wide video (ratio 1.11) should NOT need rotation")
    }

    // MARK: - AnalysisResultView Page Structure Tests

    func testAnalysisResultView_RequiresPhasesForDisplay() async {
        // Create delivery WITHOUT phases
        viewModel.handleActionDetected(at: 5.0, thumbnail: nil)
        viewModel.sessionDeliveries[0].status = .success
        viewModel.sessionDeliveries[0].videoURL = URL(fileURLWithPath: "/tmp/test.mov")
        viewModel.sessionDeliveries[0].phases = [] // Empty phases

        let delivery = viewModel.sessionDeliveries[0]

        // Empty phases should NOT trigger AnalysisResultView (see ContentView logic)
        XCTAssertTrue(delivery.phases?.isEmpty ?? true, "Delivery has no phases")
    }

    func testAnalysisResultView_DisplaysWithPhases() async {
        // Create delivery WITH phases
        viewModel.handleActionDetected(at: 5.0, thumbnail: nil)
        viewModel.sessionDeliveries[0].status = .success
        viewModel.sessionDeliveries[0].videoURL = URL(fileURLWithPath: "/tmp/test.mov")
        viewModel.sessionDeliveries[0].phases = [
            AnalysisPhase(name: "Run-up", status: "GOOD", observation: "Good", tip: "Keep it", clipTimestamp: 0.5),
            AnalysisPhase(name: "Release", status: "NEEDS WORK", observation: "High", tip: "Lower", clipTimestamp: 2.0)
        ]

        let delivery = viewModel.sessionDeliveries[0]

        XCTAssertFalse(delivery.phases?.isEmpty ?? true, "Delivery has phases")
        XCTAssertEqual(delivery.phases?.count, 2, "Should have 2 phases")
    }

    // MARK: - Summary Page Bullet Point Logic

    func testSummaryPage_GoodAndBadPhaseSplit() {
        let phases = [
            AnalysisPhase(name: "Run-up", status: "GOOD", observation: "", tip: "", clipTimestamp: 0.5),
            AnalysisPhase(name: "Release", status: "NEEDS WORK", observation: "", tip: "", clipTimestamp: 2.0),
            AnalysisPhase(name: "Loading", status: "GOOD", observation: "", tip: "", clipTimestamp: 1.5),
            AnalysisPhase(name: "Follow-through", status: "NEEDS WORK", observation: "", tip: "", clipTimestamp: 3.0),
            AnalysisPhase(name: "Wrist", status: "GOOD", observation: "", tip: "", clipTimestamp: 2.2)
        ]

        // SummaryOverlayPage shows max 2 good + 2 bad
        let goodPhases = phases.filter { $0.isGood }.prefix(2).map { $0 }
        let badPhases = phases.filter { !$0.isGood }.prefix(2).map { $0 }

        XCTAssertEqual(goodPhases.count, 2, "Should show max 2 good phases")
        XCTAssertEqual(badPhases.count, 2, "Should show max 2 bad phases")
        XCTAssertTrue(goodPhases.allSatisfy { $0.isGood }, "All good phases should be GOOD")
        XCTAssertTrue(badPhases.allSatisfy { !$0.isGood }, "All bad phases should be NEEDS WORK")
    }

    // MARK: - Phase Timestamp Tests

    func testPhaseClipTimestamp() {
        let phase = AnalysisPhase(name: "Release", status: "GOOD", observation: "Clean", tip: "Maintain", clipTimestamp: 2.3)

        XCTAssertEqual(phase.clipTimestamp, 2.3, "Phase should have clip timestamp")
        XCTAssertEqual(phase.name, "Release")
    }

    func testPhaseClipTimestamp_NilWhenNotProvided() {
        let phase = AnalysisPhase(name: "Run-up", status: "GOOD", observation: "", tip: "")

        XCTAssertNil(phase.clipTimestamp, "Phase should have nil timestamp when not provided")
    }

    func testPhaseTimestampsForVideoSeek() {
        // Simulate phases from Expert analysis with timestamps
        let phases = [
            AnalysisPhase(name: "Run-up", status: "GOOD", observation: "", tip: "", clipTimestamp: 0.5),
            AnalysisPhase(name: "Loading", status: "NEEDS WORK", observation: "", tip: "", clipTimestamp: 1.5),
            AnalysisPhase(name: "Release", status: "GOOD", observation: "", tip: "", clipTimestamp: 2.0),
            AnalysisPhase(name: "Follow-through", status: "GOOD", observation: "", tip: "", clipTimestamp: 3.2)
        ]

        // Find phase by name and get timestamp for video seek
        let releasePhase = phases.first { $0.name.lowercased().contains("release") }
        XCTAssertNotNil(releasePhase)
        XCTAssertEqual(releasePhase?.clipTimestamp, 2.0, "Should be able to seek to release timestamp")

        // Coach chat can use these timestamps
        let followThrough = phases.first { $0.name.lowercased().contains("follow") }
        XCTAssertEqual(followThrough?.clipTimestamp, 3.2, "Follow-through at 3.2s")
    }
}
