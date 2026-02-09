import Foundation
import AVFoundation
import Combine


protocol CameraManagerProtocol: AnyObject {
    var isRecording: Bool { get }
    var currentRecordingURL: URL? { get }
    func startRecording()
    func stopRecording()
    func flipCamera()
    func startSession()
    func stopSession()
}

class CameraManager: NSObject, ObservableObject, CameraManagerProtocol {
    var session = AVCaptureSession()
    @MainActor @Published var isRecording = false
    @MainActor @Published var currentPosition: AVCaptureDevice.Position = .back
    @MainActor var currentRecordingURL: URL?
    
    private let videoOutput = AVCaptureVideoDataOutput()
    private let movieOutput = AVCaptureMovieFileOutput()
    
    weak var delegate: AVCaptureVideoDataOutputSampleBufferDelegate?
    
    private let sessionQueue = DispatchQueue(label: "camera.session.queue")
    private var isConfigured = false
    
    override init() {
        super.init()
        checkPermissions()
    }
    
    func checkPermissions() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            break
        case .notDetermined:
            sessionQueue.suspend()
            AVCaptureDevice.requestAccess(for: .video) { granted in
                if granted { self.sessionQueue.resume() }
            }
        default:
            break
        }
    }
    
    func configureSession() {
        guard !isConfigured else { return }
        
        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            
            self.session.beginConfiguration()
            self.session.sessionPreset = .hd1280x720
            
            // Camera Input - Default to BACK camera for high-quality analysis
            let discoverySession = AVCaptureDevice.DiscoverySession(deviceTypes: [.builtInWideAngleCamera], mediaType: .video, position: .back)
            let camera = discoverySession.devices.first ?? AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .front)
            
            guard let camera = camera,
                  let input = try? AVCaptureDeviceInput(device: camera),
                  self.session.canAddInput(input) else {
                self.session.commitConfiguration()
                return
            }
            self.session.addInput(input)
            
            // Set initial position state based on the actual camera used
            let actualPosition = camera.position
            Task { @MainActor in
                self.currentPosition = actualPosition
            }
            
            // Movie Output
            if self.session.canAddOutput(self.movieOutput) {
                self.session.addOutput(self.movieOutput)
            }
            
            self.session.commitConfiguration()
            
            self.isConfigured = true
        }
    }
    
    func startSession() {
        sessionQueue.async { [weak self] in
            guard let self = self else { return }
            if !self.isConfigured {
                self.configureSession()
            }
            if !self.session.isRunning {
                self.session.startRunning()
            }
        }
    }
    
    func stopSession() {
        sessionQueue.async { [weak self] in
            guard let self = self, self.session.isRunning else { return }
            self.session.stopRunning()
        }
    }
    
    func setDelegate(_ delegate: AVCaptureVideoDataOutputSampleBufferDelegate) {
        sessionQueue.async {
            self.videoOutput.setSampleBufferDelegate(delegate, queue: DispatchQueue(label: "videoQueue"))
        }
    }
    
    func startRecording() {
        sessionQueue.async {
            // Check for real camera connection
            if let connection = self.movieOutput.connection(with: .video), connection.isActive {
                if !self.movieOutput.isRecording {
                    let outputFilePath = (NSTemporaryDirectory() as NSString).appendingPathComponent(UUID().uuidString + ".mov")
                    let url = URL(fileURLWithPath: outputFilePath)
                    Task { @MainActor in 
                        self.currentRecordingURL = url
                        self.isRecording = true
                    }
                    self.movieOutput.startRecording(to: url, recordingDelegate: self)
                }
            } else {
                // SIMULATOR / NO CAMERA MODE
                print("⚠️ [CameraManager]: Simulation Mode (No Camera). Mocking recording state.")
                Task { @MainActor in self.isRecording = true }
            }
        }
    }
    
    func stopRecording() {
        sessionQueue.async {
            if self.movieOutput.isRecording {
                self.movieOutput.stopRecording()
                Task { @MainActor in self.isRecording = false }
            } else {
                 // SIMULATOR MODE STOP
                 print("⚠️ [CameraManager]: Simulation Mode. Stopping mock recording.")
                 Task { @MainActor in 
                     self.isRecording = false
                     // ✅ FIX: Post notification for simulator testing
                     if let url = self.currentRecordingURL {
                         NotificationCenter.default.post(
                             name: .didFinishRecording,
                             object: nil,
                             userInfo: ["videoURL": url]
                         )
                     }
                 }
            }
        }
    }
    
    /// Flip between front and back camera
    func flipCamera() {
        sessionQueue.async { [weak self] in
            guard let self = self, !self.movieOutput.isRecording else { 
                print("⚠️ [CameraManager]: Cannot flip camera while recording")
                return 
            }
            
            self.session.beginConfiguration()
            
            // Remove existing input
            if let currentInput = self.session.inputs.first as? AVCaptureDeviceInput {
                self.session.removeInput(currentInput)
            }
            
            // Toggle position
            let newPosition: AVCaptureDevice.Position = (self.currentPosition == .front) ? .back : .front
            
            // Add new input
            if let camera = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: newPosition),
               let input = try? AVCaptureDeviceInput(device: camera),
               self.session.canAddInput(input) {
                self.session.addInput(input)
                Task { @MainActor in
                    self.currentPosition = newPosition
                    print("🔄 [CameraManager]: Flipped to \(newPosition == .front ? "front" : "back") camera")
                }
            }
            
            self.session.commitConfiguration()
        }
    }
}

extension CameraManager: AVCaptureFileOutputRecordingDelegate {
    nonisolated func fileOutput(_ output: AVCaptureFileOutput, didFinishRecordingTo outputFileURL: URL, from connections: [AVCaptureConnection], error: Error?) {
        Task { @MainActor in
            NotificationCenter.default.post(name: .didFinishRecording, object: nil, userInfo: ["videoURL": outputFileURL])
        }
    }
}

extension Notification.Name {
    static let didFinishRecording = Notification.Name("didFinishRecording")
}
