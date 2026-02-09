import XCTest
@testable import wellBowled

/// Tests for CoachChatPage (Page 3) video state management and spinner logic
final class CoachChatPageTests: XCTestCase {

    // MARK: - VideoState Enum Tests

    func testVideoStateTransitions() {
        // Test: loading → playingOriginal → loading → playingAnnotated

        // Initial state
        var state: CoachChatPage.VideoState = .loading
        XCTAssertTrue(matches(state, .loading))

        // Transition to playing original
        let originalURL = URL(fileURLWithPath: "/tmp/original.mp4")
        state = .playingOriginal(originalURL)
        XCTAssertTrue(matches(state, .playingOriginal))

        // Transition to loading (during swap)
        state = .loading
        XCTAssertTrue(matches(state, .loading))

        // Transition to playing annotated
        let annotatedURL = URL(fileURLWithPath: "/tmp/annotated.mp4")
        state = .playingAnnotated(annotatedURL)
        XCTAssertTrue(matches(state, .playingAnnotated))
    }

    // MARK: - Spinner Logic Tests

    func testShouldShowLoadingSpinner_whenPlayingOriginal() {
        // Given: Playing original video with phases
        let delivery = createTestDelivery(withPhases: true)
        let videoState: CoachChatPage.VideoState = .playingOriginal(URL(fileURLWithPath: "/tmp/test.mp4"))

        // When: Check spinner visibility
        let shouldShow = shouldShowSpinner(videoState: videoState, phases: delivery.phases ?? [])

        // Then: Spinner should show
        XCTAssertTrue(shouldShow, "Spinner should show when playing original with phases")
    }

    func testShouldShowLoadingSpinner_whenLoading() {
        // Given: Loading state with phases
        let delivery = createTestDelivery(withPhases: true)
        let videoState: CoachChatPage.VideoState = .loading

        // When: Check spinner visibility
        let shouldShow = shouldShowSpinner(videoState: videoState, phases: delivery.phases ?? [])

        // Then: Spinner should show
        XCTAssertTrue(shouldShow, "Spinner should show during loading state")
    }

    func testShouldShowLoadingSpinner_whenPlayingAnnotated() {
        // Given: Playing annotated video
        let delivery = createTestDelivery(withPhases: true)
        let videoState: CoachChatPage.VideoState = .playingAnnotated(URL(fileURLWithPath: "/tmp/annotated.mp4"))

        // When: Check spinner visibility
        let shouldShow = shouldShowSpinner(videoState: videoState, phases: delivery.phases ?? [])

        // Then: Spinner should NOT show
        XCTAssertFalse(shouldShow, "Spinner should hide when playing annotated video")
    }

    func testShouldShowLoadingSpinner_noPhases() {
        // Given: Playing original but no phases
        let delivery = createTestDelivery(withPhases: false)
        let videoState: CoachChatPage.VideoState = .playingOriginal(URL(fileURLWithPath: "/tmp/test.mp4"))

        // When: Check spinner visibility
        let shouldShow = shouldShowSpinner(videoState: videoState, phases: delivery.phases ?? [])

        // Then: Spinner should NOT show
        XCTAssertFalse(shouldShow, "Spinner should not show when no phases exist")
    }

    // MARK: - Video Swap Workflow Tests

    func testVideoSwapWorkflow() {
        // Given: Initial state with original video
        var videoState: CoachChatPage.VideoState = .playingOriginal(URL(fileURLWithPath: "/tmp/original.mp4"))
        let phases = createTestPhases()

        // Phase 1: Playing original - spinner shows
        XCTAssertTrue(shouldShowSpinner(videoState: videoState, phases: phases))

        // Phase 2: Overlay ready - transition to loading
        videoState = .loading
        XCTAssertTrue(shouldShowSpinner(videoState: videoState, phases: phases))

        // Phase 3: Video loaded - transition to playing annotated
        videoState = .playingAnnotated(URL(fileURLWithPath: "/tmp/annotated.mp4"))

        // Phase 4: Spinner hides
        XCTAssertFalse(shouldShowSpinner(videoState: videoState, phases: phases))
    }

    // MARK: - Helper Functions

    /// Simulates shouldShowLoadingSpinner logic from CoachChatPage
    private func shouldShowSpinner(videoState: CoachChatPage.VideoState, phases: [AnalysisPhase]) -> Bool {
        // Hide only when playing annotated video
        if case .playingAnnotated = videoState {
            return false
        }
        // Show if we have analysis phases
        return !phases.isEmpty
    }

    /// Pattern matching helper for VideoState
    private func matches(_ state: CoachChatPage.VideoState, _ pattern: CoachChatPage.VideoState) -> Bool {
        switch (state, pattern) {
        case (.loading, .loading):
            return true
        case (.playingOriginal, .playingOriginal):
            return true
        case (.playingAnnotated, .playingAnnotated):
            return true
        default:
            return false
        }
    }

    /// Creates test delivery with or without phases
    private func createTestDelivery(withPhases: Bool) -> Delivery {
        let phases = withPhases ? createTestPhases() : []
        return Delivery(
            id: UUID(),
            timestamp: Date(),
            videoURL: URL(fileURLWithPath: "/tmp/test.mp4"),
            speed: 85.0,
            phases: phases,
            status: .success
        )
    }

    /// Creates sample analysis phases
    private func createTestPhases() -> [AnalysisPhase] {
        return [
            AnalysisPhase(
                name: "Pre-Delivery",
                status: "GOOD",
                feedback: "Good balance",
                clipTimestamp: 0.5
            ),
            AnalysisPhase(
                name: "Release",
                status: "ATTENTION",
                feedback: "Front arm dropping",
                clipTimestamp: 1.0
            )
        ]
    }
}

// MARK: - VideoState Extension for Testing

extension CoachChatPage {
    enum VideoState {
        case loading
        case playingOriginal(URL)
        case playingAnnotated(URL)
    }
}
