import Foundation
import AVFoundation
import UIKit
@testable import wellBowled

class MockCameraManager: CameraManagerProtocol {
    var session = AVCaptureSession()
    var isRecording = false
    var currentPosition: AVCaptureDevice.Position = .front
    var currentRecordingURL: URL? = URL(fileURLWithPath: "/tmp/mock.mov")
    
    var startRecordingCalled = false
    var stopRecordingCalled = false
    
    func startSession() {}
    func stopSession() {}
    func startRecording() {
        startRecordingCalled = true
        isRecording = true
    }
    func stopRecording() {
        stopRecordingCalled = true
        isRecording = false
        
        // Simulate notification for tests
        NotificationCenter.default.post(
            name: .didFinishRecording,
            object: nil,
            userInfo: ["videoURL": currentRecordingURL!]
        )
    }
    func flipCamera() {}
}

class MockVideoActionDetector: VisionEngine {
    private static var _mockResult: Double?
    var mockResult: Double? {
        get { return MockVideoActionDetector._mockResult }
        set { MockVideoActionDetector._mockResult = newValue }
    }
    
    func findBowlingPeak(in asset: AVAsset, startTime: Double) async -> Double? {
        return mockResult
    }
}
