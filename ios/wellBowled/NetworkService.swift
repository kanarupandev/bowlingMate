import Foundation

struct AnalysisResult: Codable, Sendable {
    let report: String
    let speed_est: String
    let tips: [String]?
    let bowl_id: Int
    let release_timestamp: Double?
}

protocol NetworkServiceProtocol: Sendable {
    func analyzeVideo(fileURL: URL, config: String, language: String) async throws -> AnalysisResult
    func streamAnalysis(videoID: String?, videoURL: URL?, config: String, language: String, onEvent: @escaping (Result<String, Error>) -> Void)
    func detectAction(videoChunkURL: URL) async throws -> ActionDetectionResult
    func prefetchUpload(videoURL: URL, config: String, language: String) async throws -> String
    func uploadClip(fileURL: URL, delivery: Delivery) async throws -> (id: String, videoURL: URL, thumbURL: URL)
    func chat(message: String, deliveryId: String, phases: [AnalysisPhase]) async throws -> CoachChatResponse
}

struct ActionDetectionResult: Codable, Sendable {
    let found: Bool
    let deliveries_detected_at_time: [Double]
    let total_count: Int
}

// MARK: - Coach Chat Models

struct CoachChatRequest: Codable {
    let message: String
    let delivery_id: String
    let phases: [[String: Any]]

    enum CodingKeys: String, CodingKey {
        case message, delivery_id, phases
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(message, forKey: .message)
        try container.encode(delivery_id, forKey: .delivery_id)
        // Encode phases as JSON data
        let phasesData = try JSONSerialization.data(withJSONObject: phases)
        let phasesString = String(data: phasesData, encoding: .utf8) ?? "[]"
        try container.encode(phasesString, forKey: .phases)
    }

    init(from decoder: Decoder) throws {
        fatalError("Decoding not supported")
    }

    init(message: String, deliveryId: String, phases: [[String: Any]]) {
        self.message = message
        self.delivery_id = deliveryId
        self.phases = phases
    }
}

struct CoachChatResponse: Codable, Sendable {
    let text: String
    let video_action: VideoAction?
}

struct VideoAction: Codable, Sendable {
    let action: String  // "focus", "pause", "play"
    let timestamp: Double?
}

class RealNetworkService: NetworkServiceProtocol {
    // Hidden initializer for internal use
    fileprivate init() {}
    
    // Configurable endpoint
    var baseURL: String { 
        return AppConfig.baseURL
    }
    
    private let timeout: TimeInterval = 300.0 
    
    func analyzeVideo(fileURL: URL, config: String, language: String) async throws -> AnalysisResult {
        let url = URL(string: "\(baseURL)/analyze")!
        let (request, body) = createMultipartRequest(url: url, fileURL: fileURL, config: config, language: language)
        
        let (data, _) = try await URLSession.shared.upload(for: request, from: body)
        return try JSONDecoder().decode(AnalysisResult.self, from: data)
    }
    
    func detectAction(videoChunkURL: URL) async throws -> ActionDetectionResult {
        let url = URL(string: "\(baseURL)/detect-action")!
        var request = URLRequest(url: url, timeoutInterval: timeout) // 300s for longer videos
        request.httpMethod = "POST"
        request.setValue(AppConfig.bearerHeader, forHTTPHeaderField: "Authorization")
        
        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        let videoData = try Data(contentsOf: videoChunkURL)
        print("📡 [Network] Preparing upload for detection: \(videoChunkURL.lastPathComponent) (\(videoData.count) bytes)")
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"chunk.mp4\"\r\nContent-Type: video/mp4\r\n\r\n".data(using: .utf8)!)
        body.append(videoData)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        let (data, response) = try await URLSession.shared.upload(for: request, from: body)
        
        if let httpResponse = response as? HTTPURLResponse {
            print("TELEMETRY [Network]: Detection Response Code: \(httpResponse.statusCode)")
            if !(200...299).contains(httpResponse.statusCode) {
                let msg = "Server Error: \(httpResponse.statusCode)"
                throw NSError(domain: "ServerError", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: msg])
            }
        }
        
        return try JSONDecoder().decode(ActionDetectionResult.self, from: data)
    }
    
    func streamAnalysis(videoID: String?, videoURL: URL?, config: String, language: String, onEvent: @escaping (Result<String, Error>) -> Void) {
        if let videoID = videoID {
            self.connectToSSEStream(videoID: videoID, config: config, language: language, onEvent: onEvent)
            return
        }
        
        guard let videoURL = videoURL else {
            onEvent(.failure(NSError(domain: "Network", code: 400, userInfo: [NSLocalizedDescriptionKey: "No media available"])))
            return
        }
        
        // We use a Task here because this method is NOT async in the protocol (it uses SSE which is long-running and doesn't fit a simple return)
        Task {
            do {
                let videoID = try await prefetchUpload(videoURL: videoURL, config: config, language: language)
                self.connectToSSEStream(videoID: videoID, config: config, language: language, onEvent: onEvent)
            } catch {
                onEvent(.failure(error))
            }
        }
    }
    
    func prefetchUpload(videoURL: URL, config: String, language: String) async throws -> String {
        let uploadURL = URL(string: "\(baseURL)/analyze")!
        let (request, body) = createMultipartRequest(url: uploadURL, fileURL: videoURL, config: config, language: language)
        
        let (data, _) = try await URLSession.shared.upload(for: request, from: body)
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let videoID = json["video_id"] as? String else {
            throw NSError(domain: "UploadFailed", code: 0, userInfo: [NSLocalizedDescriptionKey: "Malformed server response"])
        }
        return videoID
    }
    
    func uploadClip(fileURL: URL, delivery: Delivery) async throws -> (id: String, videoURL: URL, thumbURL: URL) {
        let url = URL(string: "\(baseURL)/upload-clip")!
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = "POST"
        request.setValue(AppConfig.bearerHeader, forHTTPHeaderField: "Authorization")
        
        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        
        // Form Fields
        let fields: [String: String] = [
            "release_timestamp": String(delivery.releaseTimestamp ?? delivery.timestamp),
            "speed": delivery.speed ?? "",
            "report": delivery.report ?? "",
            "tips": (delivery.tips).joined(separator: "|")
        ]
        
        for (key, value) in fields {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(key)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        
        // Video File
        let videoData = try Data(contentsOf: fileURL)
        body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"delivery_\(delivery.id.uuidString).mp4\"\r\nContent-Type: video/mp4\r\n\r\n".data(using: .utf8)!)
        body.append(videoData)
        body.append("\r\n".data(using: .utf8)!)
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        
        let (data, response) = try await URLSession.shared.upload(for: request, from: body)
        
        if let httpResponse = response as? HTTPURLResponse, !(200...299).contains(httpResponse.statusCode) {
            throw NSError(domain: "UploadError", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: "Server returned \(httpResponse.statusCode)"])
        }
        
        let decoder = JSONDecoder()
        struct UploadResponse: Codable {
            let id: String
            let video_url: String
            let thumbnail_url: String
        }
        
        let decoded = try decoder.decode(UploadResponse.self, from: data)
        return (decoded.id, URL(string: decoded.video_url)!, URL(string: decoded.thumbnail_url)!)
    }
    
    // MARK: - Coach Chat

    func chat(message: String, deliveryId: String, phases: [AnalysisPhase]) async throws -> CoachChatResponse {
        print("💬 [Chat] Starting chat request")
        print("💬 [Chat] Message: \(message)")
        print("💬 [Chat] Delivery: \(deliveryId.prefix(8))...")
        print("💬 [Chat] Phases count: \(phases.count)")

        let url = URL(string: "\(baseURL)/chat")!
        var request = URLRequest(url: url, timeoutInterval: 60.0)
        request.httpMethod = "POST"
        request.setValue(AppConfig.bearerHeader, forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Convert phases to dictionary format with clip_ts
        let phasesDict: [[String: Any]] = phases.map { phase in
            var dict: [String: Any] = [
                "name": phase.name,
                "status": phase.status,
                "observation": phase.observation,
                "tip": phase.tip
            ]
            if let clipTs = phase.clipTimestamp {
                dict["clip_ts"] = clipTs
            }
            return dict
        }

        let body: [String: Any] = [
            "message": message,
            "delivery_id": deliveryId,
            "phases": phasesDict
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        print("💬 [Chat] Request body: \(String(data: request.httpBody!, encoding: .utf8)?.prefix(200) ?? "nil")...")

        let data: Data
        let response: URLResponse

        do {
            (data, response) = try await URLSession.shared.data(for: request)
        } catch {
            print("❌ [Chat] Network error: \(error)")
            print("❌ [Chat] Error domain: \((error as NSError).domain)")
            print("❌ [Chat] Error code: \((error as NSError).code)")
            throw error // Re-throw to preserve error type for UI handling
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            print("❌ [Chat] Invalid response type")
            throw NSError(domain: "ChatError", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid response"])
        }

        print("💬 [Chat] Response status: \(httpResponse.statusCode)")

        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMsg = String(data: data, encoding: .utf8) ?? "Unknown error"
            print("❌ [Chat] Server error \(httpResponse.statusCode): \(errorMsg)")
            throw NSError(domain: "ChatError", code: httpResponse.statusCode, userInfo: [NSLocalizedDescriptionKey: errorMsg])
        }

        let responseStr = String(data: data, encoding: .utf8) ?? ""
        print("💬 [Chat] Response body: \(responseStr.prefix(300))...")

        // Validate non-empty response
        guard !data.isEmpty else {
            print("❌ [Chat] Empty response body")
            throw NSError(domain: "ChatError", code: -2, userInfo: [NSLocalizedDescriptionKey: "Empty response"])
        }

        do {
            let decoded = try JSONDecoder().decode(CoachChatResponse.self, from: data)
            print("💬 [Chat] ✅ Decoded successfully")
            print("💬 [Chat] Text: \(decoded.text.prefix(50))...")
            print("💬 [Chat] Action: \(decoded.video_action?.action ?? "none") @ \(decoded.video_action?.timestamp ?? -1)s")
            return decoded
        } catch {
            print("❌ [Chat] JSON decode error: \(error)")
            print("❌ [Chat] Raw data: \(responseStr)")
            throw error
        }
    }

    // MARK: - Helper Methods

    private func createMultipartRequest(url: URL, fileURL: URL, config: String, language: String) -> (URLRequest, Data) {
        var request = URLRequest(url: url, timeoutInterval: timeout)
        request.httpMethod = "POST"
        
        // SECURITY: Inject API Secret
        request.setValue(AppConfig.bearerHeader, forHTTPHeaderField: "Authorization")
        
        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        var body = Data()
        let params = ["config": config, "language": language]
        for (key, value) in params {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(key)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!)
        }
        
        if let videoData = try? Data(contentsOf: fileURL) {
            body.append("--\(boundary)\r\nContent-Disposition: form-data; name=\"video\"; filename=\"clip.mov\"\r\nContent-Type: video/quicktime\r\n\r\n".data(using: .utf8)!)
            body.append(videoData)
            body.append("\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        return (request, body)
    }
    
    private var activeSessions: [String: URLSession] = [:]

    private func connectToSSEStream(videoID: String, config: String, language: String, onEvent: @escaping (Result<String, Error>) -> Void) {
        var components = URLComponents(string: "\(self.baseURL)/stream-analysis")!
        components.queryItems = [
            URLQueryItem(name: "video_id", value: videoID),
            URLQueryItem(name: "config", value: config),
            URLQueryItem(name: "language", value: language),
            URLQueryItem(name: "generate_overlay", value: "true")
        ]

        print("📡 [SSE] Connecting to: \(components.url?.absoluteString ?? "nil")")
        print("📡 [SSE] VideoID: \(videoID)")

        var request = URLRequest(url: components.url!)
        request.setValue(AppConfig.bearerHeader, forHTTPHeaderField: "Authorization")
        request.timeoutInterval = self.timeout

        let sessionConfig = URLSessionConfiguration.default
        sessionConfig.timeoutIntervalForRequest = self.timeout

        // Use a unique ID to track the session and prevent deallocation
        let sessionID = UUID().uuidString
        let delegate = SSEDelegate(videoID: videoID) { [weak self] result in
            onEvent(result)
            // Cleanup on completion or error
            if case .failure = result {
                self?.activeSessions.removeValue(forKey: sessionID)
            } else if case .success(let json) = result {
                if json.contains("\"status\":\"success\"") || json.contains("\"status\":\"error\"") {
                    self?.activeSessions.removeValue(forKey: sessionID)
                }
            }
        }

        let session = URLSession(configuration: sessionConfig, delegate: delegate, delegateQueue: .main)
        activeSessions[sessionID] = session
        let task = session.dataTask(with: request)
        print("📡 [SSE] Task created, resuming...")
        task.resume()
    }
}

class SSEDelegate: NSObject, URLSessionDataDelegate {
    let onEvent: (Result<String, Error>) -> Void
    let videoID: String

    // Buffer to accumulate data across chunks (SSE data can be split)
    private var buffer = ""

    init(videoID: String, onEvent: @escaping (Result<String, Error>) -> Void) {
        self.videoID = videoID
        self.onEvent = onEvent
        super.init()
        print("📡 [SSE] Delegate initialized for \(videoID)")
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse, completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        if let httpResponse = response as? HTTPURLResponse {
            print("📡 [SSE] HTTP Response: \(httpResponse.statusCode) for \(videoID)")
            if httpResponse.statusCode != 200 {
                print("⚠️ [SSE] Non-200 status: \(httpResponse.statusCode)")
            }
        }
        completionHandler(.allow)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        print("📡 [SSE] Received \(data.count) bytes for \(videoID)")
        guard let chunk = String(data: data, encoding: .utf8) else {
            print("⚠️ [SSE] Failed to decode chunk as UTF-8")
            return
        }

        // Append to buffer
        buffer += chunk
        print("📡 [SSE] Buffer size: \(buffer.count) chars")

        // Process complete events (SSE format: "data: {...}\n\n")
        // Split on double newline which marks end of SSE event
        while let eventEnd = buffer.range(of: "\n\n") {
            let eventData = String(buffer[..<eventEnd.lowerBound])
            buffer = String(buffer[eventEnd.upperBound...])

            // Parse SSE event lines
            let lines = eventData.components(separatedBy: "\n")
            for line in lines where line.hasPrefix("data: ") {
                let json = String(line.dropFirst(6)) // Remove "data: " prefix
                print("📡 [SSE] Complete event: \(json.prefix(100))...")

                // Validate JSON before emitting
                if let jsonData = json.data(using: .utf8),
                   (try? JSONSerialization.jsonObject(with: jsonData)) != nil {
                    print("✅ [SSE] Valid JSON, emitting event")
                    onEvent(.success(json))
                } else {
                    print("⚠️ [SSE] Invalid JSON in event: \(json.prefix(50))...")
                }
            }
        }

        // Log remaining buffer if any (incomplete event)
        if !buffer.isEmpty {
            print("📡 [SSE] Buffered (incomplete): \(buffer.count) chars")
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error {
            print("❌ [SSE] Connection failed for \(videoID): \(error.localizedDescription)")
            onEvent(.failure(error))
        } else {
            print("✅ [SSE] Connection completed for \(videoID)")

            // Process any remaining buffered data
            if !buffer.isEmpty {
                print("📡 [SSE] Processing final buffer: \(buffer.count) chars")
                let lines = buffer.components(separatedBy: "\n")
                for line in lines where line.hasPrefix("data: ") {
                    let json = String(line.dropFirst(6))
                    if let jsonData = json.data(using: .utf8),
                       (try? JSONSerialization.jsonObject(with: jsonData)) != nil {
                        print("✅ [SSE] Final event: \(json.prefix(100))...")
                        onEvent(.success(json))
                    }
                }
                buffer = ""
            }
        }
    }
}

// MARK: - MOCK SERVICE
class MockNetworkService: NetworkServiceProtocol {
    
    // Simulate latency
    private let latency: TimeInterval
    
    init(latency: TimeInterval = 2.0) {
        self.latency = latency
    }
    
    func analyzeVideo(fileURL: URL, config: String, language: String) async throws -> AnalysisResult {
        try await Task.sleep(nanoseconds: UInt64(latency * 1_000_000_000))
        return AnalysisResult(
            report: "Mock Analysis: Excellent seam position. Your wrist snap is generating good revolutions.",
            speed_est: "138.5 km/h",
            tips: ["Maintain high arm slot", "Follow through more to off-stump"],
            bowl_id: Int.random(in: 1000...9999),
            release_timestamp: nil
        )
    }
    
    func streamAnalysis(videoID: String?, videoURL: URL?, config: String, language: String, onEvent: @escaping (Result<String, Error>) -> Void) {
        print("🦄 [Mock] Starting Stream Analysis for \(videoID ?? videoURL?.lastPathComponent ?? "unknown")")
        
        DispatchQueue.global().async {
            // Event 1: Processing
            try? Thread.sleep(forTimeInterval: 1.0)
            let event1 = """
            {"status": "event", "type": "info", "message": "Analyzing trajectory..."}
            """
            onEvent(.success(event1))
            
            // Event 2: Biomechanics
            try? Thread.sleep(forTimeInterval: 1.5)
            let event2 = """
            {"status": "event", "type": "info", "message": "Measuring release angle..."}
            """
            onEvent(.success(event2))
            
            // Event 3: Success (~4.5s total delay)
            try? Thread.sleep(forTimeInterval: 2.0)
            
            // Use a random speed for variety
            let speed = String(format: "%.1f", Double.random(in: 130.0...145.0))
            
            let finalResult = """
            {
                "status": "success",
                "speed_est": "\(speed) km/h",
                "report": "Mock Report: Good release point detected. The arm cycle looks consistent. Try to increase your run-up speed for more momentum.",
                "tips": ["Good wrist position", "Stable landing", "Mock Tip #3"],
                "release_timestamp": 2.5
            }
            """
            onEvent(.success(finalResult))
        }
    }
    
    func detectAction(videoChunkURL: URL) async throws -> ActionDetectionResult {
         print("🦄 [Mock] Detect Action requested for \(videoChunkURL.lastPathComponent)")
         try await Task.sleep(nanoseconds: UInt64((latency / 2.0) * 1_000_000_000))
         
         // Simulate finding 1-3 deliveries in a 2-minute chunk
         let count = Int.random(in: 1...3)
         var times: [Double] = []
         for i in 0..<count {
             // Spread them out: e.g. at 15s, 45s, 90s
             times.append(Double(15 + (i * 40)))
         }
         
         return ActionDetectionResult(
            found: true, 
            deliveries_detected_at_time: times,
            total_count: times.count
         )
    }
    
    func prefetchUpload(videoURL: URL, config: String, language: String) async throws -> String {
        try await Task.sleep(nanoseconds: 1_000_000_000)
        return "mock-video-id-\(UUID().uuidString)"
    }
    
    func uploadClip(fileURL: URL, delivery: Delivery) async throws -> (id: String, videoURL: URL, thumbURL: URL) {
        try await Task.sleep(nanoseconds: 1_000_000_000)
        return (
            delivery.id.uuidString,
            URL(string: "https://storage.googleapis.com/wellbowled-clips/mock_\(delivery.id.uuidString).mp4")!,
            URL(string: "https://storage.googleapis.com/wellbowled-clips/mock_thumb_\(delivery.id.uuidString).jpg")!
        )
    }

    func chat(message: String, deliveryId: String, phases: [AnalysisPhase]) async throws -> CoachChatResponse {
        print("🦄 ========== MOCK CHAT START ==========")
        print("🦄 [Mock] Message: \"\(message)\"")
        print("🦄 [Mock] Delivery: \(deliveryId.prefix(8))...")
        print("🦄 [Mock] Phases: \(phases.count)")
        for phase in phases {
            print("🦄 [Mock]   - \(phase.name) @ \(phase.clipTimestamp ?? -1)s")
        }

        print("🦄 [Mock] Simulating 0.5s network delay...")
        try await Task.sleep(nanoseconds: 500_000_000) // 0.5s delay

        let lowerMessage = message.lowercased()
        print("🦄 [Mock] Checking keywords in: \"\(lowerMessage)\"")

        // Helper: Find phase by keywords in name
        func findPhase(_ keywords: [String]) -> AnalysisPhase? {
            for keyword in keywords {
                if let phase = phases.first(where: { $0.name.lowercased().contains(keyword) }) {
                    return phase
                }
            }
            return nil
        }

        // RELEASE: wrist, snap, release, arm
        if lowerMessage.contains("release") || lowerMessage.contains("wrist") || lowerMessage.contains("arm") {
            let phase = findPhase(["release", "wrist", "snap", "arm"])
            let timestamp = phase?.clipTimestamp ?? 2.0
            print("🦄 [Mock] ✓ MATCHED: release → focus@\(timestamp)s (phase: \(phase?.name ?? "default"))")
            return CoachChatResponse(
                text: "I can see your arm position at the release point. Notice how your elbow is positioned here - this is the key moment for a legal delivery.",
                video_action: VideoAction(action: "focus", timestamp: timestamp)
            )
        }

        // RUN-UP: runup, run, approach, stride
        if lowerMessage.contains("runup") || lowerMessage.contains("run") || lowerMessage.contains("approach") {
            let phase = findPhase(["run", "approach", "stride"])
            let timestamp = phase?.clipTimestamp ?? 0.5
            print("🦄 [Mock] ✓ MATCHED: runup → focus@\(timestamp)s (phase: \(phase?.name ?? "default"))")
            return CoachChatResponse(
                text: "Watch your approach rhythm here. Your momentum builds nicely, but let's check if your stride length is consistent.",
                video_action: VideoAction(action: "focus", timestamp: timestamp)
            )
        }

        // LOADING: load, coil, wind
        if lowerMessage.contains("load") || lowerMessage.contains("coil") || lowerMessage.contains("wind") {
            let phase = findPhase(["load", "coil", "wind"])
            let timestamp = phase?.clipTimestamp ?? 1.5
            print("🦄 [Mock] ✓ MATCHED: loading → focus@\(timestamp)s (phase: \(phase?.name ?? "default"))")
            return CoachChatResponse(
                text: "This is your loading phase - how you coil your body before delivery. Notice your shoulder rotation here.",
                video_action: VideoAction(action: "focus", timestamp: timestamp)
            )
        }

        // FOLLOW-THROUGH: follow, through, finish
        if lowerMessage.contains("follow") || lowerMessage.contains("through") || lowerMessage.contains("finish") {
            let phase = findPhase(["follow", "through", "finish"])
            let timestamp = phase?.clipTimestamp ?? 3.5
            print("🦄 [Mock] ✓ MATCHED: follow-through → focus@\(timestamp)s (phase: \(phase?.name ?? "default"))")
            return CoachChatResponse(
                text: "Your follow-through determines accuracy and protects your arm. See how your arm continues its path here.",
                video_action: VideoAction(action: "focus", timestamp: timestamp)
            )
        }

        // STOP/PAUSE
        if lowerMessage.contains("stop") || lowerMessage.contains("pause") || lowerMessage.contains("freeze") {
            print("🦄 [Mock] ✓ MATCHED: stop → pause")
            return CoachChatResponse(
                text: "Let me freeze this frame for you. Study your body position - notice the alignment of your shoulders and hips.",
                video_action: VideoAction(action: "pause", timestamp: nil)
            )
        }

        // PLAY/RESUME
        if lowerMessage.contains("play") || lowerMessage.contains("resume") || lowerMessage.contains("continue") {
            print("🦄 [Mock] ✓ MATCHED: play → resume")
            return CoachChatResponse(
                text: "Resuming video at normal speed. Let me know which phase you'd like to focus on.",
                video_action: VideoAction(action: "play", timestamp: nil)
            )
        }

        // DEFAULT: List available phases
        let phaseNames = phases.map { $0.name }.joined(separator: ", ")
        print("🦄 [Mock] ✗ No keyword matched → listing phases")
        return CoachChatResponse(
            text: "I can help analyze your: \(phaseNames). Ask about any phase, or say 'stop' to pause the video.",
            video_action: nil
        )
    }
}

// MARK: - COMPOSITE SERVICE (The Router)
class CompositeNetworkService: NetworkServiceProtocol {
    static let shared = CompositeNetworkService()
    
    private let real = RealNetworkService()
    private let mock = MockNetworkService()
    
    func detectAction(videoChunkURL: URL) async throws -> ActionDetectionResult {
        if AppConfig.useMockDetection {
            print("🦄 [Composite]: Routing detectAction to MOCK")
            return try await mock.detectAction(videoChunkURL: videoChunkURL)
        } else {
            print("🚀 [Composite]: Routing detectAction to REAL (\(AppConfig.baseURL))")
            return try await real.detectAction(videoChunkURL: videoChunkURL)
        }
    }
    
    func streamAnalysis(videoID: String?, videoURL: URL?, config: String, language: String, onEvent: @escaping (Result<String, Error>) -> Void) {
        if AppConfig.useMockAnalysis {
            print("🦄 [Composite]: Routing streamAnalysis to MOCK")
            mock.streamAnalysis(videoID: videoID, videoURL: videoURL, config: config, language: language, onEvent: onEvent)
        } else {
            print("🚀 [Composite]: Routing streamAnalysis to REAL (\(AppConfig.baseURL))")
            real.streamAnalysis(videoID: videoID, videoURL: videoURL, config: config, language: language, onEvent: onEvent)
        }
    }
    
    func analyzeVideo(fileURL: URL, config: String, language: String) async throws -> AnalysisResult {
        if AppConfig.useMockAnalysis {
            return try await mock.analyzeVideo(fileURL: fileURL, config: config, language: language)
        } else {
            return try await real.analyzeVideo(fileURL: fileURL, config: config, language: language)
        }
    }
    
    func prefetchUpload(videoURL: URL, config: String, language: String) async throws -> String {
        if AppConfig.useMockAnalysis {
            return try await mock.prefetchUpload(videoURL: videoURL, config: config, language: language)
        } else {
            return try await real.prefetchUpload(videoURL: videoURL, config: config, language: language)
        }
    }
    
    func uploadClip(fileURL: URL, delivery: Delivery) async throws -> (id: String, videoURL: URL, thumbURL: URL) {
        if AppConfig.useMockAnalysis {
             return try await mock.uploadClip(fileURL: fileURL, delivery: delivery)
        } else {
             return try await real.uploadClip(fileURL: fileURL, delivery: delivery)
        }
    }

    func chat(message: String, deliveryId: String, phases: [AnalysisPhase]) async throws -> CoachChatResponse {
        if AppConfig.useMockChat {
            print("🦄 [Composite]: Routing chat to MOCK (video control enabled)")
            return try await mock.chat(message: message, deliveryId: deliveryId, phases: phases)
        } else {
            print("🚀 [Composite]: Routing chat to REAL (\(AppConfig.baseURL))")
            return try await real.chat(message: message, deliveryId: deliveryId, phases: phases)
        }
    }
}
