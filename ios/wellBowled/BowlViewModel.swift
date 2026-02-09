import SwiftUI
import Combine
import AVFoundation

enum UIMode {
    case live
    case upload
    case history // New mode for viewing deliveries without blocking camera
    case favorites // New mode for persistent favorites
}

@MainActor
class BowlViewModel: ObservableObject {
    @Published var uiMode: UIMode = .live {
        didSet {
            L("uiMode changed: \(oldValue) → \(uiMode)", .debug)
            
            // POWER OPTIMIZATION: Stop camera sensor when not in use
            if uiMode == .live {
                cameraManager.startSession()
            } else {
                cameraManager.stopSession()
            }
        }
    }
    
    // Transient Session Data (Cleared on restart/new session)
    @Published var sessionDeliveries: [Delivery] = []
    
    // Persistent History Data (All past deliveries)
    @Published var historyDeliveries: [Delivery] = [] {
        didSet {
            PersistenceManager.shared.saveAll(historyDeliveries)
        }
    }
    
    // Persisted Favorites Data (Saved to disk)
    @Published var favoriteDeliveries: [Delivery] = [] {
        didSet {
            PersistenceManager.shared.save(favoriteDeliveries)
        }
    }
    
    @Published var streamingLogs: [StreamingEvent] = []
    @Published var selectedDelivery: Delivery? = nil
    @Published var isSessionSummaryVisible = false
    
    @Published var showingError = false
    @Published var errorMessage: String? = nil
    
    @Published var configLevel = "club"
    @Published var language = "en"
    
    // UI State
    @Published var isImporting = false
    @Published var scoutingStatus: String? = nil // Progress message during "The Scout" phase
    @Published var scoutingProgress: Double = 0.0 // 0.0 to 1.0
    @Published var connectionError: String? = nil // Displayed if backend is unreachable or dead
    @Published var isBackendOffline = false
    @Published var currentCarouselID: UUID? = nil // Track current carousel page

    // Configurable network settings
    private let timeout: TimeInterval = 300.0 
    
    private let cameraManager: CameraManagerProtocol
    private let detector: VisionEngine // Changed to the modular protocol
    private let networkService: NetworkServiceProtocol
    private let cloudStorageService: CloudStorageServiceProtocol
    private var cancellables = Set<AnyCancellable>()
    
    // Gemini Analysis Management
    private var analysisQueue: [UUID] = []
    @Published var activeAnalysisCount = 0 // Made public for UI if needed
    private let maxAnalysisConcurrency = 1
    private var activeAnalysisIDs = Set<UUID>() // Parallel safety
    
    var isAnyAnalysisRunning: Bool {
        activeAnalysisCount > 0
    }
    
    // State for Unified Pipeline
    private var currentUploadURL: URL?
    private var discoveryTask: Task<Void, Never>? // Main task for standalone imports
    private var pendingSegments = 0 // Track active segment processing
    private var acceptedTimestamps = Set<Double>() // Deduplication Registry
    
    /// Public accessor to check if discovery task is currently running
    var isDiscoveryTaskRunning: Bool {
        (discoveryTask != nil && !(discoveryTask?.isCancelled ?? true)) || pendingSegments > 0
    }
    
    init(
        cameraManager: CameraManagerProtocol,
        detector: VisionEngine,
        networkService: NetworkServiceProtocol? = nil,
        cloudStorageService: CloudStorageServiceProtocol = CloudStorageService.shared
    ) {
        self.cameraManager = cameraManager
        self.detector = detector
        
        // Granular Hybrid Service (Mock/Real routing handled inside Composite)
        if let service = networkService {
            self.networkService = service
        } else {
            print("🔀 [ViewModel]: Initialized with COMPOSITE Network Service")
            self.networkService = CompositeNetworkService.shared
        }
        
        self.cloudStorageService = cloudStorageService
        
        // Load persisted data
        let loadedFavorites = PersistenceManager.shared.load()
        let loadedHistory = PersistenceManager.shared.loadAll()

        self.favoriteDeliveries = loadedFavorites
        self.historyDeliveries = loadedHistory
        
        print("📂 [ViewModel]: History (\(historyDeliveries.count)) and Favorites (\(favoriteDeliveries.count)) restored.")
        
        // Initialize Session with Cloud History (Simulation of multi-device)
        self.loadCloudHistory()
        
        // Recover missing thumbnails for persistent history
        self.hydrateThumbnails()

        // Setup notification bindings
        setupBindings()
    }
    
    // MARK: - Session Management
    
    func startNewSession() {
        print("TELEMETRY [Session]: Starting new session. Clearing ephemeral local state.")

        withAnimation(.spring()) {
            sessionDeliveries = []
            streamingLogs = []
            isSessionSummaryVisible = false
            acceptedTimestamps = []
            analysisQueue = []
            activeAnalysisCount = 0
            activeAnalysisIDs = []
            scoutingStatus = nil
            scoutingProgress = 0.0
            currentCarouselID = nil
            pendingSegments = 0
            isImporting = false
            finalizingLiveSession = false
            accumulatedTime = 0
            timeRemaining = maxRecordingDuration
        }
    }
    
    private func loadCloudHistory() {
        L("Hydrating Session History from Remote...", .network)
        Task {
            do {
                let recent = try await cloudStorageService.listRecentDeliveries()
                await MainActor.run {
                    withAnimation {
                        // Merge recent items into history if they don't exist
                        for remote in recent {
                            if !self.historyDeliveries.contains(where: { $0.id == remote.id }) {
                                self.historyDeliveries.append(remote)
                            }
                        }
                        // Sync current session to cloud results if it's the first view
                        if self.sessionDeliveries.isEmpty {
                            self.sessionDeliveries = recent
                        }
                    }
                    print("✅ [Cloud]: Hydrated \(recent.count) items into Session/History.")
                    self.hydrateThumbnails()
                }
            } catch {
                print("❌ [Cloud]: Failed to hydrate history: \(error)")
            }
        }
    }
    
    private func hydrateThumbnails() {
        L("Checking for missing thumbnails in history...", .info)
        Task {
            // Process history items to see if they need thumbnails
            let deliveries = await MainActor.run { self.historyDeliveries }
            
            for delivery in deliveries {
                if delivery.thumbnail == nil {
                    // 1. Try to load from Disk cache first (Premium Sync)
                    if let savedPath = delivery.localThumbnailPath,
                       let savedThumb = PersistenceManager.shared.loadThumbnail(named: savedPath) {
                        await MainActor.run {
                            if let idx = self.historyDeliveries.firstIndex(where: { $0.id == delivery.id }) {
                                self.historyDeliveries[idx].thumbnail = savedThumb
                                print("✅ [Recover]: Thumbnail LOADED from DISK for \(delivery.id.uuidString.prefix(6))")
                            }
                            if let sIdx = self.sessionDeliveries.firstIndex(where: { $0.id == delivery.id }) {
                                self.sessionDeliveries[sIdx].thumbnail = savedThumb
                            }
                        }
                    }
                    // 2. Fallback to generating from local file if disk cache missing
                    else if let localURL = delivery.videoURL, FileManager.default.fileExists(atPath: localURL.path) {
                        if let thumb = self.generateThumbnail(for: localURL, at: 0.0) { 
                            await MainActor.run {
                                if let idx = self.historyDeliveries.firstIndex(where: { $0.id == delivery.id }) {
                                    self.historyDeliveries[idx].thumbnail = thumb
                                    self.historyDeliveries[idx].localThumbnailPath = PersistenceManager.shared.saveThumbnail(thumb, for: delivery.id)
                                    print("✅ [Recover]: Thumbnail REGENERATED for \(delivery.id.uuidString.prefix(6))")
                                }
                                if let sIdx = self.sessionDeliveries.firstIndex(where: { $0.id == delivery.id }) {
                                    self.sessionDeliveries[sIdx].thumbnail = thumb
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    // MARK: - Recording Management
    
    @Published var timeRemaining: TimeInterval = 300 // 5 minutes default
    private var recordingTimer: AnyCancellable?
    private let maxRecordingDuration: TimeInterval = 300 // 5 minutes
    private var isLiveSessionStarted = false
    private var finalizingLiveSession = false // True when processing final segment
    private var accumulatedTime: Double = 0
    
    func toggleRecording() {
        if isLiveSessionStarted {
            print("🛑 [Recording]: Manual Stop. Finishing session.")
            // Mark session as ending - final segment will trigger analysis page switch
            finalizingLiveSession = true // Track that we're ending a session (for notification handler)
            isLiveSessionStarted = false

            cameraManager.stopRecording()

            // Stop timer
            recordingTimer?.cancel()
            recordingTimer = nil

        } else {
            print("🎬 [Recording]: Starting Live Session...")
            // Clear analysis state for fresh recording
            startNewSession()
            isLiveSessionStarted = true
            accumulatedTime = 0

            // Start recording timer (5:00 countdown)
            timeRemaining = maxRecordingDuration
            recordingTimer = Timer.publish(every: 1.0, on: .main, in: .common)
                .autoconnect()
                .sink { [weak self] _ in
                    guard let self = self else { return }
                    self.timeRemaining -= 1

                    let elapsed = self.maxRecordingDuration - self.timeRemaining

                    // Segment Batching: Process based on chunkDuration (e.g., 120 seconds) while staying on camera
                    if Int(elapsed) % Int(ClipConfig.chunkDuration) == 0 && elapsed > 0 && self.isLiveSessionStarted {
                        print("📦 [Recording]: \(Int(ClipConfig.chunkDuration))s segment reached. Processing batch...")
                        self.cameraManager.stopRecording()
                        // Next segment will start in didFinishRecording handler
                    }

                    // Auto-stop at 0 and switch to analysis
                    if self.timeRemaining <= 0 {
                        print("⏱️ [Recording]: Countdown complete - switching to analysis")
                        self.toggleRecording()
                    }
                }

            cameraManager.startRecording()
        }
    }
    
    // ...
    
    private func setupBindings() {
        // Listen for CameraManager finishing a recording (either segment or final)
        NotificationCenter.default.publisher(for: .didFinishRecording)
            .compactMap { $0.userInfo?["videoURL"] as? URL }
            .receive(on: RunLoop.main)
            .sink { [weak self] url in
                guard let self = self else { return }
                Task { @MainActor in
                    print("DEBUG [ViewModel]: Capture Finished (\(url.lastPathComponent)).")
                    let isMidSession = self.isLiveSessionStarted
                    let isFinalSegment = self.finalizingLiveSession
                    let isSessionSegment = isMidSession || isFinalSegment

                    self.processVideoSource(url: url, isSegment: isSessionSegment, timeOffset: self.accumulatedTime)

                    let asset = AVAsset(url: url)
                    if let duration = try? await asset.load(.duration).seconds {
                        self.accumulatedTime += duration
                    }
                    // 3. Start next segment OR end session
                    if isMidSession && self.cameraManager.isRecording == false && self.uiMode == .live {
                        // This was a mid-session rotation - start next segment
                        print("🎬 [Recording]: Rotating to next segment...")
                        self.cameraManager.startRecording()
                    } else if isFinalSegment {
                        // This was the final segment - switch to analysis page
                        print("🏁 [Recording]: Final segment captured. Switching to analysis.")
                        self.finalizingLiveSession = false

                        withAnimation(.spring()) {
                            self.uiMode = .upload
                            self.scoutingStatus = self.sessionDeliveries.isEmpty ? "Looking for deliveries..." : "Processing..."
                        }
                    }
                }
            }
            .store(in: &cancellables)
    }

    // MARK: - Helper Methods
    
    /// Generates a thumbnail image from a video URL at a specific timestamp.
    /// Should be called from a background thread.
    private func generateThumbnail(for url: URL, at timestamp: Double) -> UIImage? {
        print("DEBUG [Thumbnail]: Generating for \(url.lastPathComponent) at \(timestamp)s")
        let sourceAsset = AVAsset(url: url)
        let imageGenerator = AVAssetImageGenerator(asset: sourceAsset)
        imageGenerator.appliesPreferredTrackTransform = true
        // Allow loose tolerance to ensure we get *a* frame quickly
        imageGenerator.requestedTimeToleranceBefore = .positiveInfinity
        imageGenerator.requestedTimeToleranceAfter = .positiveInfinity
        
        // Capture at T+0.0s (Action Start) - often clearer than T+0.3s if 0.3 is blurry
        let captureTime = timestamp
        let time = CMTime(seconds: captureTime, preferredTimescale: 600)
        
        do {
            let cgImage = try imageGenerator.copyCGImage(at: time, actualTime: nil)
            print("DEBUG [Thumbnail]: Success")
            return UIImage(cgImage: cgImage)
        } catch {
            print("DEBUG [Thumbnail]: FAILED - \(error.localizedDescription)")
            return nil
        }
    }

    /// Triggered when an arm roll/peak is detected.
    func handleActionDetected(at timestamp: Double, thumbnail: UIImage?) {
        print("DEBUG [Scout]: Peak detected at \(timestamp)s. Initiating pipeline...")
        
        // RACE CONDITION FIX: Guard against mutations 
        // Allow ONLY in .upload or .live (if recording is ongoing)
        guard uiMode == .upload || (uiMode == .live && isLiveSessionStarted) else {
            print("⚠️ [Scout]: Skipping delivery creation - invalid state (mode: \(uiMode), sessionActive: \(isLiveSessionStarted))")
            return
        }
        
        guard let url = (uiMode == .live ? cameraManager.currentRecordingURL : currentUploadURL) else {
            showAppError("Discovery Error", "No source video found for the detected action.")
            return
        }
        
        let sequence = sessionDeliveries.count + 1
        var newDelivery = Delivery(timestamp: timestamp, releaseTimestamp: timestamp, status: .clipping, sequence: sequence)
        
        // SAVE THUMB TO DISK
        if let thumb = thumbnail {
            newDelivery.thumbnail = thumb
            newDelivery.localThumbnailPath = PersistenceManager.shared.saveThumbnail(thumb, for: newDelivery.id)
        }
        
        let deliveryID = newDelivery.id
        
        print("➕ [MUTATION] Adding delivery #\(sequence)")
        print("   └─ Current uiMode: \(uiMode)")
        print("   └─ Current count: \(sessionDeliveries.count)")
        print("   └─ Thread: \(Thread.isMainThread ? "Main" : "Background")")

        // PERF LOGGING: Track first card creation
        if sessionDeliveries.count == 0 {
            print("🎯 [PERF] [T-CARD] FIRST CARD CREATED at \(Date())")
            print("   └─ Delivery #\(sequence) at timestamp \(timestamp)s")
        }

        self.objectWillChange.send()
        print("DEBUG [UI]: Spawning card for Delivery #\(sequence)")
        withAnimation(.spring()) {
            // Insert in chronological order by video timestamp
            let insertIndex = self.sessionDeliveries.firstIndex { $0.timestamp > newDelivery.timestamp }
                ?? self.sessionDeliveries.count
            self.sessionDeliveries.insert(newDelivery, at: insertIndex)

            // Also track in history immediately
            self.historyDeliveries.append(newDelivery)

            // FE-01 Fix: Only auto-navigate to the FIRST bowl found. 
            // Stay there during discovery to avoid jumpy UI.
            if self.sessionDeliveries.count == 1 {
                self.currentCarouselID = newDelivery.id
            }
        }

        print("   └─ New count: \(sessionDeliveries.count)")
            
        // Precision Clipping (T-3.0s to T+2.0s = 5s Total)
        Task {
            let clipRefStart = Date()
            do {
                let startTime = max(0, timestamp - ClipConfig.preRoll)
                    let duration: Double = ClipConfig.totalDuration
                    
                    await MainActor.run {
                        self.streamingLogs.append(StreamingEvent(message: "✂️ [Internal] Extracting High-Res Clip: [\(String(format: "%.2f", startTime))s - \(String(format: "%.2f", startTime+duration))s]", type: "info"))
                    }
                    
                    print("DEBUG [Clipper]: Extraction Request - Center: \(timestamp)s, Range: [\(startTime) - \(startTime + duration)]")
                    let hiResStart = CACurrentMediaTime()
                    // PERFORMANCE: Use Analysis/Passthrough preset for the final user clip (High Quality)
                    // Longer timeout (60s) for multi-delivery scenarios to avoid I/O contention timeouts
                    let trimmedURL = try await PassthroughClipper.clip(sourceURL: url, startTime: startTime, duration: duration, preset: ClipConfig.analysisExportPreset, timeoutSeconds: 60)
                    print("✅ [PERF] [T9] High-Res Clip \(sequence) Created. Elapsed: \(String(format: "%.3f", CACurrentMediaTime() - hiResStart))s")
                
                await MainActor.run {
                    self.objectWillChange.send()
                    if let idx = self.sessionDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                        withAnimation(.spring()) {
                            self.sessionDeliveries[idx].videoURL = trimmedURL
                            self.sessionDeliveries[idx].localVideoPath = trimmedURL.lastPathComponent
                            self.sessionDeliveries[idx].status = .queued // Transition status to ready for AI
                            self.sessionDeliveries[idx].releaseTimestamp = timestamp 
                        }
                        
                        // Sync to history
                        if let hIdx = self.historyDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                            self.historyDeliveries[hIdx].videoURL = trimmedURL
                            self.historyDeliveries[hIdx].localVideoPath = trimmedURL.lastPathComponent
                            self.historyDeliveries[hIdx].status = .queued
                        }

                        print("DEBUG [Pipeline]: Clip verified for Delivery #\(sequence) at \(trimmedURL.path)")
                        self.streamingLogs.append(StreamingEvent(message: "🎞️ 5.0s ACTION CLIP READY (Centered at \(String(format: "%.2fs", timestamp))s)", type: "success"))
                        
                        // 2. PREFETCH UPLOAD (Only for first delivery - others upload on-demand)
                        // This saves bandwidth when multiple deliveries detected but user only analyzes some
                        if sequence == 1 {
                            print("📡 [Prefetch]: Initializing background upload for Delivery #\(sequence) (first only)")
                            Task {
                                do {
                                    let videoID = try await networkService.prefetchUpload(videoURL: trimmedURL, config: configLevel, language: language)
                                    await MainActor.run {
                                        if let idx = self.sessionDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                                            self.sessionDeliveries[idx].videoID = videoID
                                            if let hIdx = self.historyDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                                                self.historyDeliveries[hIdx].videoID = videoID
                                            }
                                            print("✅ [Prefetch]: Media warmed on server for Delivery #\(sequence) (ID: \(videoID))")
                                        }
                                    }
                                } catch {
                                    print("⚠️ [Prefetch]: Failed to warm media: \(error)")
                                }
                            }
                        } else {
                            print("⏳ [Prefetch]: Skipping auto-prefetch for Delivery #\(sequence) (will upload on-demand)")
                        }

                        // 3. PERSISTENCE FALLBACK: Upload final clip to Google Storage
                        Task {
                            guard let delivery = self.sessionDeliveries.first(where: { $0.id == deliveryID }) else { return }
                            do {
                                let result = try await cloudStorageService.upload(fileURL: trimmedURL, delivery: delivery)
                                await MainActor.run {
                                    if let idx = self.sessionDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                                        self.sessionDeliveries[idx].cloudVideoURL = result.video
                                        self.sessionDeliveries[idx].cloudThumbnailURL = result.thumb
                                    }
                                    if let hIdx = self.historyDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                                        self.historyDeliveries[hIdx].cloudVideoURL = result.video
                                        self.historyDeliveries[hIdx].cloudThumbnailURL = result.thumb
                                    }
                                    print("☁️ [Cloud]: Persisted clip to GCS for \(deliveryID)")
                                }
                            } catch {
                                print("⚠️ [Cloud]: Failed to persist clip: \(error)")
                            }
                        }

                    }
                }
            } catch {
                print("DEBUG [Clipper]: CRITICAL ERROR - Delivery #\(sequence): \(error.localizedDescription)")
                await MainActor.run {
                    if let idx = self.sessionDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                        withAnimation { self.sessionDeliveries[idx].status = .failed }
                    }
                    self.streamingLogs.append(StreamingEvent(message: "❌ Clipping Failed: \(error.localizedDescription)", type: "error"))
                }
            }
            
            let clipEnd = Date()
            let clipDuration = clipEnd.timeIntervalSince(clipRefStart)
            await MainActor.run {
                 self.streamingLogs.append(StreamingEvent(message: "⏱️ Final Clip Generated & Prefetching in \(String(format: "%.2f", clipDuration))s", type: "info"))
            }
        }
    }

    
    // MARK: - On-Demand Analysis
    
    func requestAnalysis(for delivery: Delivery) {
        guard let idx = sessionDeliveries.firstIndex(where: { $0.id == delivery.id }) else {
            print("⚠️ [Analysis]: Delivery not found in session")
            return
        }

        // Guard: Cannot analyze without a video clip
        guard sessionDeliveries[idx].videoURL != nil else {
            print("⚠️ [Analysis]: Cannot analyze - clip still being extracted")
            streamingLogs.append(StreamingEvent(message: "⏳ Clip still extracting, please wait...", type: "info"))
            return
        }

        // Allow re-analysis if status is .success or .failed (Retry)
        if sessionDeliveries[idx].status == .success {
             print("ℹ️ [Analysis]: Re-analyzing existing delivery")
        }

        withAnimation {
            sessionDeliveries[idx].status = .queued
        }

        analysisQueue.append(delivery.id)
        processNextInQueue()
    }
    
    @MainActor
    private func processNextInQueue() {
        print("DEBUG [Prefetcher]: Evaluating queue. Count: \(analysisQueue.count), Active: \(activeAnalysisIDs.count)")
        
        while activeAnalysisIDs.count < maxAnalysisConcurrency && !analysisQueue.isEmpty {
            let deliveryID = analysisQueue.removeFirst()
            
            // Skip if already analyzing
            if activeAnalysisIDs.contains(deliveryID) { continue }
            
            guard let idx = sessionDeliveries.firstIndex(where: { $0.id == deliveryID }),
                  let clipURL = sessionDeliveries[idx].videoURL else {
                continue
            }
            
            activeAnalysisIDs.insert(deliveryID)
            activeAnalysisCount = activeAnalysisIDs.count
            let sequence = sessionDeliveries[idx].sequence
            
            self.streamingLogs.append(StreamingEvent(message: "🚀 Cloud Sync Started (Delivery #\(sequence))...", type: "info"))
            withAnimation { self.sessionDeliveries[idx].status = .analyzing }
            
            let auditStart = CACurrentMediaTime()
            print("🚀 [PERF] [T10] Technical Audit (Coach) STARTED for Delivery #\(sequence) | Prefetched: \(sessionDeliveries[idx].videoID != nil)")
            
            let delivery = sessionDeliveries[idx]
            
            networkService.streamAnalysis(videoID: delivery.videoID, videoURL: clipURL, config: configLevel, language: language) { [weak self] result in
                guard let self = self else { return }

                Task { @MainActor in
                    switch result {
                    case .success(let jsonString):
                        // Parse JSON with error handling
                        guard let data = jsonString.data(using: .utf8) else {
                            print("⚠️ [SSE] Failed to convert string to data for Delivery #\(sequence)")
                            return
                        }

                        guard let event = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                            print("⚠️ [SSE] Failed to parse JSON for Delivery #\(sequence): \(jsonString.prefix(100))...")
                            return
                        }

                        guard let status = event["status"] as? String else {
                            print("⚠️ [SSE] Missing 'status' field in event for Delivery #\(sequence)")
                            return
                        }

                        print("📨 [SSE] Event received: status='\(status)' for Delivery #\(sequence)")

                        switch status {
                        case "event":
                            self.handleStreamEvent(event, defaultID: deliveryID)

                        case "overlay":
                            if let urlString = event["overlay_url"] as? String, let url = URL(string: urlString) {
                                print("🎬 [Overlay] ===== OVERLAY URL RECEIVED =====")
                                print("🎬 [Overlay] Delivery #\(sequence), ID: \(deliveryID)")
                                print("🎬 [Overlay] URL: \(urlString)")

                                if let idx = self.sessionDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                                    self.sessionDeliveries[idx].overlayVideoURL = url
                                    print("🎬 [Overlay] Updated sessionDeliveries[\(idx)].overlayVideoURL")
                                }
                                if let hIdx = self.historyDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                                    self.historyDeliveries[hIdx].overlayVideoURL = url
                                    print("🎬 [Overlay] Updated historyDeliveries[\(hIdx)].overlayVideoURL")
                                }
                                // CRITICAL: Also update selectedDelivery (SwiftUI value type issue)
                                if self.selectedDelivery?.id == deliveryID {
                                    self.selectedDelivery?.overlayVideoURL = url
                                    print("🎬 [Overlay] Updated selectedDelivery.overlayVideoURL")
                                } else {
                                    print("🎬 [Overlay] selectedDelivery is nil or different (ID: \(self.selectedDelivery?.id.uuidString.prefix(8) ?? "nil"))")
                                }

                                self.streamingLogs.append(StreamingEvent(message: "🎬 Biomechanics overlay ready", type: "success"))
                                print("🎬 [Overlay] Starting async download task...")
                                Task { await self.downloadAndCacheOverlay(url: url, deliveryID: deliveryID) }
                            } else {
                                print("⚠️ [Overlay] Invalid or missing overlay_url for Delivery #\(sequence)")
                            }

                        case "success":
                            let elapsed = CACurrentMediaTime() - auditStart
                            print("✅ [PERF] [T10] Coach FINISHED for Delivery #\(sequence). Total: \(String(format: "%.2f", elapsed))s")
                            self.handleFinalResult(event, defaultID: deliveryID)
                            self.cleanupAnalysis(deliveryID)

                        case "error":
                            let errorMsg = event["message"] as? String ?? "Unknown AI Error"
                            print("❌ [SSE] Error event for Delivery #\(sequence): \(errorMsg)")
                            self.handleAnalysisError(deliveryID, message: errorMsg)

                        default:
                            print("⚠️ [SSE] Unknown status '\(status)' for Delivery #\(sequence)")
                        }

                    case .failure(let err):
                        print("❌ [SSE] Network failure for Delivery #\(sequence): \(err.localizedDescription)")
                        self.handleAnalysisError(deliveryID, message: "Network Error: \(err.localizedDescription)")
                    }
                }
            }
        }
    }
    
    @MainActor 
    private func cleanupAnalysis(_ id: UUID) {
        if activeAnalysisIDs.contains(id) {
            activeAnalysisIDs.remove(id)
            activeAnalysisCount = activeAnalysisIDs.count
            processNextInQueue()
        }
    }

    @MainActor
    private func handleAnalysisError(_ id: UUID, message: String) {
        print("DEBUG [Analysis]: ERROR - \(message)")
        
        if let idx = self.sessionDeliveries.firstIndex(where: { $0.id == id }) {
            // Only update UI if we are actually waiting for this
            guard [.analyzing, .queued].contains(self.sessionDeliveries[idx].status) else { return }
            
            withAnimation { self.sessionDeliveries[idx].status = .failed }
            self.streamingLogs.append(StreamingEvent(message: "❌ Delivery #\(self.sessionDeliveries[idx].sequence): \(message)", type: "error"))
            
            // Show non-blocking banner if connection issue
            if message.lowercased().contains("unreachable") || message.lowercased().contains("connection") {
                self.isBackendOffline = true
                self.connectionError = "Network error. Check connection."
            }
        }
        cleanupAnalysis(id)
    }

    private func showAppError(_ title: String, _ message: String) {
        DispatchQueue.main.async {
            self.errorMessage = "\(title): \(message)"
            self.showingError = true
            self.streamingLogs.append(StreamingEvent(message: "🚨 \(title): \(message)", type: "error"))
        }
    }
    
    // MARK: - Upload Orchestration (5s Blind Chunks)
    
    func prepareForUpload() {
        print("DEBUG [UI]: Transitioning to Upload Mode. Clearing state.")
        withAnimation(.spring()) {
            startNewSession()
            self.uiMode = .upload
            self.isImporting = true
            self.scoutingStatus = "Importing Media..."
            self.streamingLogs = [] // Start clean for transparency
        }
    }
    
    // MARK: - Unified Video Pipeline (Live & Upload)
    // This method handles ANY video source (Camera recording or Picker selection).
    // It applies the same 10s chunking logic ("The 10 Second Rule") to genericize detection.
    
    // MARK: - Unified Video Pipeline (Live & Upload)
    // This method handles ANY video source (Camera recording or Picker selection).
    // It applies the same 10s chunking logic ("The 10 Second Rule") to genericize detection.
    
    func processVideoSource(url: URL, isSegment: Bool = false, timeOffset: Double = 0) {
        print("DEBUG [Pipeline]: processing \(isSegment ? "segment" : "source") for action discovery: \(url.lastPathComponent) (offset: \(timeOffset)s)")
        
        if !isSegment {
            discoveryTask?.cancel()
            startNewSession()
            self.uiMode = .upload
            self.streamingLogs.append(StreamingEvent(message: "PROCESSING MEDIA", type: "info"))
        } else {
            self.pendingSegments += 1
        }
        
        self.currentUploadURL = url
        
        withAnimation(.spring()) {
              self.isSessionSummaryVisible = false
              self.scoutingStatus = isSegment ? "Processing live segment..." : "PROCESSING MEDIA..."
        }
        
        let task = Task(priority: .userInitiated) {
            let taskStartTime = CACurrentMediaTime()
            print("🚀 [PERF] [T4] Discovery Task STARTED at \(String(format: "%.3f", taskStartTime))")
            
            do {
                let asset = AVAsset(url: url)
                // Permission Check
                let keysStatus = asset.status(of: .duration)
                print("🔍 [PERF] Asset Duration status: \(keysStatus)")
                
                let loadStart = CACurrentMediaTime()
                let duration = try await asset.load(.duration).seconds
                print("✅ [PERF] [T5] Metadata Loaded. Duration: \(duration)s. Elapsed: \(String(format: "%.3f", CACurrentMediaTime() - loadStart))s")
                
                // Parallel Chunking Logic with Indexed Ordering
                try await withThrowingTaskGroup(of: (Int, [Double]).self) { group in
                    let groupStart = CACurrentMediaTime()
                    print("🚀 [PERF] [T6] TaskGroup Initialized at \(String(format: "%.3f", groupStart)). Offset: \(String(format: "%.3f", groupStart - taskStartTime))s from start.")
                    var currentTime: Double = 0
                    let maxConcurrentUploads = AppConfig.maxScoutingConcurrency
                    var activeUploads = 0
                    var currentChunkIndex = 0
                    
                    var chunkResults: [Int: [Double]] = [:]
                    var nextIndexToProcess = 0
                    
                    // PERFORMANCE LOOP: Decoupled Clipping & Uploading with Backpressure
                    while currentTime < duration || activeUploads > 0 {
                        // 1. FILL: Start a new upload if we have capacity and media
                        if currentTime < duration && activeUploads < maxConcurrentUploads && !Task.isCancelled {
                            let chunkDuration = min(ClipConfig.chunkDuration, duration - currentTime)
                            if chunkDuration >= 1.0 {
                                let windowStartTime = currentTime
                                let offset = timeOffset
                                let index = currentChunkIndex
                                
                                let clipperStart = CACurrentMediaTime()
                                do {
                                    if index == 0 {
                                        await MainActor.run {
                                            self.streamingLogs.append(StreamingEvent(message: "PREPARING MEDIA FOR DELIVERY DETECTION", type: "info"))
                                        }
                                    }
                                    
                                    // CLIP (Re-encode for small upload size)
                                    // Dynamic timeout: 60s base + 2s per second of video (re-encoding is slow)
                                    let clipTimeout = max(60, Int(60 + chunkDuration * 2))
                                    let chunkURL = try await PassthroughClipper.clip(sourceURL: url, startTime: windowStartTime, duration: chunkDuration, preset: ClipConfig.scoutExportPreset, timeoutSeconds: clipTimeout)
                                    print("✅ [PERF] [T7] Chunk \(index) Created [\(windowStartTime)s]. Elapsed: \(String(format: "%.3f", CACurrentMediaTime() - clipperStart))s")
                                    
                                    // 2. QUEUE UPLOAD (Parallel Network)
                                    activeUploads += 1
                                    group.addTask(priority: .userInitiated) {
                                        if index == 0 {
                                            await MainActor.run {
                                                self.streamingLogs.append(StreamingEvent(message: "LOOKING FOR DELIVERIES", type: "info"))
                                            }
                                        }
                                        
                                        let netStart = CACurrentMediaTime()
                                        do {
                                            // Dynamic timeout: 30s for short clips, 300s for longer videos (>30s)
                                            let timeoutNanos: UInt64 = chunkDuration > 30.0 ? 300_000_000_000 : 30_000_000_000
                                            let result = try await withThrowingTaskGroup(of: ActionDetectionResult.self) { timeoutGroup in
                                                timeoutGroup.addTask { try await self.networkService.detectAction(videoChunkURL: chunkURL) }
                                                timeoutGroup.addTask {
                                                    try await Task.sleep(nanoseconds: timeoutNanos)
                                                    throw NSError(domain: "Timeout", code: 408, userInfo: [NSLocalizedDescriptionKey: "Scouting Chunk Timeout"])
                                                }
                                                let first = try await timeoutGroup.next()!
                                                timeoutGroup.cancelAll()
                                                return first
                                            }
                                            let foundTimes: [Double] = await MainActor.run {
                                                self.isBackendOffline = false
                                                self.connectionError = nil
                                                if result.found {
                                                    let count = result.deliveries_detected_at_time.count
                                                    self.streamingLogs.append(StreamingEvent(message: "🎯 FOUND \(count) DELIVER\(count == 1 ? "Y" : "IES") IN SEGMENT", type: "success"))
                                                    return result.deliveries_detected_at_time.map { offset + windowStartTime + $0 }
                                                } else {
                                                    self.streamingLogs.append(StreamingEvent(message: "STILL LOOKING FOR DELIVERIES...", type: "info"))
                                                    return []
                                                }
                                            }
                                            try? FileManager.default.removeItem(at: chunkURL)
                                            print("✅ [PERF] [T8] Chunk \(index) Analysis FINISHED. Duration: \(String(format: "%.3f", CACurrentMediaTime() - netStart))s")
                                            return (index, foundTimes)
                                        } catch {
                                            await MainActor.run {
                                                let nsError = error as NSError
                                                let isOffline = (nsError.domain == NSURLErrorDomain && 
                                                                (nsError.code == NSURLErrorCannotConnectToHost || 
                                                                 nsError.code == NSURLErrorTimedOut || 
                                                                 nsError.code == NSURLErrorNotConnectedToInternet))
                                                
                                                self.isBackendOffline = isOffline
                                                if isOffline {
                                                    self.connectionError = "Delivery Engine reachable? Check connection."
                                                } else {
                                                    self.connectionError = "Vision Engine Error: \(error.localizedDescription)"
                                                }
                                            }
                                            try? FileManager.default.removeItem(at: chunkURL)
                                            return (index, [])
                                        }
                                    }
                                } catch {
                                    print("❌ [PERF] [T7.ERR] Serial Clipping Failed for index \(index): \(error.localizedDescription)")
                                }
                                
                                currentTime += ClipConfig.chunkStep
                                currentChunkIndex += 1
                            } else {
                                currentTime = duration
                            }
                        } else if activeUploads > 0 {
                            // 3. WAIT: If we are at capacity OR done clipping, wait for results
                            if let (idx, ts) = try await group.next() {
                                activeUploads -= 1
                                chunkResults[idx] = ts
                            }
                        }
                        
                        // 4. DRAIN: Reassemble results in order (STREAMS UI)
                        while let nextResult = chunkResults[nextIndexToProcess] {
                            let chunkCount = ceil(duration / ClipConfig.chunkStep)
                            let progress = Double(nextIndexToProcess + 1) / max(1, chunkCount)
                            
                            if let absoluteTimestamps = chunkResults[nextIndexToProcess] {
                                // 5. Temporal Deduplication & Card Spawning for MULTIPLE deliveries
                                let threshold = AppConfig.deduplicationThreshold
                                
                                for absoluteTimestamp in absoluteTimestamps {
                                    let isDuplicate = await MainActor.run {
                                        self.acceptedTimestamps.contains { existing in
                                            abs(existing - absoluteTimestamp) < threshold
                                        }
                                    }
                                    
                                    if !isDuplicate {
                                        let thumb = self.generateThumbnail(for: url, at: absoluteTimestamp - timeOffset)
                                        await MainActor.run {
                                            self.acceptedTimestamps.insert(absoluteTimestamp)
                                            if self.uiMode == .upload || (self.uiMode == .live && self.isLiveSessionStarted) {
                                                self.streamingLogs.append(StreamingEvent(message: "✅ ACTION CONFIRMED at \(String(format: "%.2f", absoluteTimestamp))s", type: "success"))
                                            }
                                            self.handleActionDetected(at: absoluteTimestamp, thumbnail: thumb)
                                        }
                                    }
                                }
                            }
                            
                            // Update granular progress and count AFTER potentials additions
                            await MainActor.run {
                                self.scoutingProgress = progress
                                let foundCount = self.sessionDeliveries.count
                                self.scoutingStatus = "Scanning: \(foundCount) Deliver\(foundCount == 1 ? "y" : "ies") Found (\(Int(self.scoutingProgress * 100))%)"
                            }
                            
                            chunkResults.removeValue(forKey: nextIndexToProcess)
                            nextIndexToProcess += 1
                        }
                    }
                    // Wait for remaining tasks
                    try await group.waitForAll()
                    let totalTime = CACurrentMediaTime() - taskStartTime
                    let efficiency = totalTime / duration
                    print("🏁 [PERF] [T11] All Scouting Chunks Finished.")
                    print("   └─ Total Discovery Time: \(String(format: "%.3f", totalTime))s")
                    print("   └─ Video Duration: \(String(format: "%.3f", duration))s")
                    print("   └─ Scouting Efficiency: \(String(format: "%.3fx real-time", efficiency))")
                }
            } catch {
                print("❌ [PERF] [FATAL] Asset Load or Group Failed: \(error.localizedDescription)")
                if let nsError = error as NSError? {
                    print("   └─ Domain: \(nsError.domain), Code: \(nsError.code)")
                    print("   └─ Info: \(nsError.userInfo)")
                }
            }
            
            // ... rest of the final state reset ...
            
            // FINAL STATE RESET (Guaranteed to run)
            await MainActor.run {
                if isSegment {
                    self.pendingSegments = max(0, self.pendingSegments - 1)
                }
                
                self.isImporting = false
                
                // Final Status Decision
                if self.uiMode == .upload {
                    // If this was the last pending task and no session is active
                    if self.pendingSegments == 0 && !self.isLiveSessionStarted {
                        if self.sessionDeliveries.isEmpty {
                            self.scoutingStatus = "No deliveries found"
                            if !self.streamingLogs.contains(where: { $0.message.contains("No actions detected") }) {
                                self.streamingLogs.append(StreamingEvent(message: "Session ended. No actions detected.", type: "info"))
                            }
                        } else {
                            let found = self.sessionDeliveries.count
                            self.scoutingStatus = "Complete: \(found) Deliver\(found == 1 ? "y" : "ies") Found"
                            self.scoutingProgress = 1.0
                            // Navigate to the first one for review
                            withAnimation(.spring()) {
                                self.currentCarouselID = self.sessionDeliveries.first?.id
                            }
                            self.streamingLogs.append(StreamingEvent(message: "✅ DISCOVERY COMPLETED. All clips ready for analysis.", type: "success"))
                            // Auto-dismiss banner after 5 seconds of visibility
                            Task {
                                try? await Task.sleep(nanoseconds: 5_000_000_000)
                                if self.scoutingStatus?.contains("Complete") ?? false {
                                     withAnimation { self.scoutingStatus = nil }
                                }
                            }
                        }
                    } else if isSegment {
                         // Still recording or other segments pending
                         if self.sessionDeliveries.isEmpty {
                             self.scoutingStatus = "Looking for deliveries..."
                         }
                    }
                }
                print("✅ [DISCOVERY] Task COMPLETED. Segment: \(isSegment), Pending: \(self.pendingSegments), Status: \(self.scoutingStatus ?? "nil")")
            }
        }
        
        if !isSegment {
            discoveryTask = task
        }
    }
    
    private func handleStreamEvent(_ event: [String: Any], defaultID: UUID) {
        let message = event["message"] as? String ?? ""
        let type = event["type"] as? String ?? "info"
        
        withAnimation {
            self.streamingLogs.append(StreamingEvent(message: "  ↳ \(message)", type: type))
        }
    }
    
    private func handleFinalResult(_ event: [String: Any], defaultID: UUID) {
        guard let idx = self.sessionDeliveries.firstIndex(where: { $0.id == defaultID }) else {
            print("⚠️ [Analysis] handleFinalResult: Delivery not found for ID \(defaultID)")
            return
        }

        let sequence = self.sessionDeliveries[idx].sequence
        print("📥 [Analysis] handleFinalResult ENTRY for Delivery #\(sequence)")

        // Extract all fields with logging
        let report = event["report"] as? String
        let speed = event["speed_est"] as? String
        let tips = event["tips"] as? [String] ?? []
        let releaseTimestamp = event["release_timestamp"] as? Double

        print("   └─ report: \(report?.prefix(50) ?? "nil")...")
        print("   └─ speed: \(speed ?? "nil")")
        print("   └─ tips: \(tips.count) items")

        // Parse phases from response
        var phases: [AnalysisPhase]? = nil
        if let phasesData = event["phases"] as? [[String: Any]] {
            phases = phasesData.compactMap { dict in
                guard let name = dict["name"] as? String,
                      let status = dict["status"] as? String else { return nil }
                let observation = dict["observation"] as? String ?? ""
                let tip = dict["tip"] as? String ?? ""
                return AnalysisPhase(name: name, status: status, observation: observation, tip: tip)
            }
            print("   └─ phases: \(phases?.count ?? 0) parsed from \(phasesData.count) raw")
        } else {
            print("   └─ phases: nil (no phases array in response)")
        }

        // Update session delivery
        let previousStatus = self.sessionDeliveries[idx].status
        withAnimation(.spring()) {
            self.sessionDeliveries[idx].report = report
            self.sessionDeliveries[idx].speed = speed
            self.sessionDeliveries[idx].tips = tips
            self.sessionDeliveries[idx].phases = phases
            self.sessionDeliveries[idx].releaseTimestamp = releaseTimestamp
            self.sessionDeliveries[idx].status = .success
        }
        print("✅ [Analysis] Delivery #\(sequence) status: \(previousStatus) → .success")

        // Sync to History
        if let hIdx = self.historyDeliveries.firstIndex(where: { $0.id == defaultID }) {
            self.historyDeliveries[hIdx].report = report
            self.historyDeliveries[hIdx].speed = speed
            self.historyDeliveries[hIdx].tips = tips
            self.historyDeliveries[hIdx].phases = phases
            self.historyDeliveries[hIdx].releaseTimestamp = releaseTimestamp
            self.historyDeliveries[hIdx].status = .success
            print("   └─ Synced to history at index \(hIdx)")
        }

        // Add success log to streaming logs
        self.streamingLogs.append(StreamingEvent(message: "✅ Analysis complete: \(speed ?? "--")", type: "success"))
        print("📤 [Analysis] handleFinalResult EXIT for Delivery #\(sequence)")
    }
    
    // MARK: - UI Interactions
    
    func selectDelivery(_ delivery: Delivery) {
        print("🔍 [SelectDelivery] ===== SELECTION =====")
        print("🔍 [SelectDelivery] Input delivery ID: \(delivery.id.uuidString.prefix(8))")
        print("🔍 [SelectDelivery] Input has phases: \(delivery.phases?.count ?? 0)")

        // CRITICAL: Always look up the FRESH version from the array
        // The passed delivery might be a stale snapshot captured at render time
        let fresh = sessionDeliveries.first { $0.id == delivery.id }
                 ?? historyDeliveries.first { $0.id == delivery.id }
                 ?? delivery

        print("🔍 [SelectDelivery] Fresh delivery #\(fresh.sequence)")
        print("🔍 [SelectDelivery] Fresh status: \(fresh.status)")
        print("🔍 [SelectDelivery] Fresh has overlayVideoURL: \(fresh.overlayVideoURL != nil)")
        print("🔍 [SelectDelivery] Fresh localOverlayPath: \(fresh.localOverlayPath ?? "nil")")
        print("🔍 [SelectDelivery] Fresh has phases: \(fresh.phases?.count ?? 0)")

        if fresh.status == .success {
            withAnimation(.spring()) { self.selectedDelivery = fresh }
            print("🔍 [SelectDelivery] Set selectedDelivery ✓ (using FRESH)")
        } else {
            print("🔍 [SelectDelivery] Skipped - status not .success")
        }
    }
    
    func dismissDetail() {
        withAnimation(.spring()) { self.selectedDelivery = nil }
    }
    
    func deleteDelivery(at offsets: IndexSet) {
        withAnimation {
            sessionDeliveries.remove(atOffsets: offsets)
        }
    }
    
    func deleteDelivery(_ delivery: Delivery) {
        withAnimation {
            sessionDeliveries.removeAll { $0.id == delivery.id }
            historyDeliveries.removeAll { $0.id == delivery.id }
            favoriteDeliveries.removeAll { $0.id == delivery.id }
        }
    }
    

    // MARK: - Overlay Video Persistence

    /// Downloads overlay video from cloud URL and caches locally for persistence
    private func downloadAndCacheOverlay(url: URL, deliveryID: UUID) async {
        print("📥 [Overlay] ╔══════════════════════════════════════╗")
        print("📥 [Overlay] ║      OVERLAY DOWNLOAD STARTING       ║")
        print("📥 [Overlay] ╚══════════════════════════════════════╝")
        print("📥 [Overlay] URL: \(url.absoluteString)")
        print("📥 [Overlay] DeliveryID: \(deliveryID)")
        print("📥 [Overlay] Timestamp: \(ISO8601DateFormatter().string(from: Date()))")

        do {
            // Create request with auth header (required for /media endpoint)
            var request = URLRequest(url: url)
            request.setValue(AppConfig.bearerHeader, forHTTPHeaderField: "Authorization")
            let tokenPreview = String(AppConfig.bearerHeader.prefix(20)) + "..."
            print("📥 [Overlay] Auth header set: \(tokenPreview)")
            print("📥 [Overlay] Request timeout: \(request.timeoutInterval)s")

            print("📥 [Overlay] 🌐 Initiating network request...")
            let startTime = CFAbsoluteTimeGetCurrent()
            let (data, response) = try await URLSession.shared.data(for: request)
            let downloadTime = CFAbsoluteTimeGetCurrent() - startTime
            print("📥 [Overlay] ⏱️ Download completed in \(String(format: "%.2f", downloadTime))s")

            if let httpResponse = response as? HTTPURLResponse {
                print("📥 [Overlay] ── HTTP Response ──")
                print("📥 [Overlay] Status: \(httpResponse.statusCode) \(HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode))")
                print("📥 [Overlay] Content-Type: \(httpResponse.value(forHTTPHeaderField: "Content-Type") ?? "unknown")")
                print("📥 [Overlay] Content-Length: \(httpResponse.value(forHTTPHeaderField: "Content-Length") ?? "unknown")")
                print("📥 [Overlay] Data received: \(data.count) bytes (\(String(format: "%.2f", Double(data.count) / 1024.0)) KB)")

                // Check for auth failure
                if httpResponse.statusCode == 401 {
                    print("❌ [Overlay] ══════════════════════════════════════")
                    print("❌ [Overlay] AUTHENTICATION FAILED (401)")
                    print("❌ [Overlay] Token may be invalid or expired")
                    print("❌ [Overlay] ══════════════════════════════════════")
                    return
                }

                if httpResponse.statusCode != 200 {
                    print("❌ [Overlay] Unexpected status code: \(httpResponse.statusCode)")
                    if let errorText = String(data: data, encoding: .utf8) {
                        print("❌ [Overlay] Response body: \(errorText.prefix(500))")
                    }
                    return
                }

                // Verify we got video content, not JSON error
                let contentType = httpResponse.value(forHTTPHeaderField: "Content-Type") ?? ""
                if contentType.contains("application/json") {
                    print("❌ [Overlay] Received JSON instead of video!")
                    if let errorText = String(data: data, encoding: .utf8) {
                        print("❌ [Overlay] JSON body: \(errorText)")
                    }
                    return
                }

                if data.count < 10000 {
                    print("⚠️ [Overlay] WARNING: Video file suspiciously small (\(data.count) bytes)")
                    print("⚠️ [Overlay] First 100 bytes: \(data.prefix(100).map { String(format: "%02x", $0) }.joined(separator: " "))")
                }

                // Validate MP4 magic bytes
                let mp4Magic = Data([0x00, 0x00, 0x00])  // MP4 starts with size + 'ftyp'
                if data.count > 8 {
                    let header = data.prefix(12)
                    let headerHex = header.map { String(format: "%02x", $0) }.joined(separator: " ")
                    print("📥 [Overlay] File header (hex): \(headerHex)")
                    if let ftypRange = String(data: data.prefix(12), encoding: .ascii), ftypRange.contains("ftyp") {
                        print("📥 [Overlay] ✓ Valid MP4 signature detected")
                    } else {
                        print("⚠️ [Overlay] MP4 signature not found in header")
                    }
                }
            }

            // Create overlays directory if needed
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let overlaysDir = documents.appendingPathComponent("overlays")
            try? FileManager.default.createDirectory(at: overlaysDir, withIntermediateDirectories: true)
            print("📥 [Overlay] ── File System ──")
            print("📥 [Overlay] Target directory: \(overlaysDir.path)")

            // Save with delivery ID as filename
            let fileName = "\(deliveryID.uuidString)_overlay.mp4"
            let localURL = overlaysDir.appendingPathComponent(fileName)

            print("📥 [Overlay] Writing \(data.count) bytes to disk...")
            try data.write(to: localURL)

            // Verify file was written correctly
            let fileExists = FileManager.default.fileExists(atPath: localURL.path)
            let attrs = try? FileManager.default.attributesOfItem(atPath: localURL.path)
            let fileSize = attrs?[.size] as? Int64 ?? 0
            let fileCreated = attrs?[.creationDate] as? Date

            print("📥 [Overlay] ── Write Verification ──")
            print("📥 [Overlay] File exists: \(fileExists)")
            print("📥 [Overlay] File size: \(fileSize) bytes")
            print("📥 [Overlay] Created: \(fileCreated?.description ?? "unknown")")
            print("📥 [Overlay] Full path: \(localURL.path)")

            await MainActor.run {
                print("📥 [Overlay] Updating model state on MainActor...")
                if let idx = self.sessionDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                    self.sessionDeliveries[idx].localOverlayPath = fileName
                    print("📥 [Overlay] Updated sessionDeliveries[\(idx)].localOverlayPath")
                } else {
                    print("⚠️ [Overlay] Delivery not found in sessionDeliveries")
                }
                if let hIdx = self.historyDeliveries.firstIndex(where: { $0.id == deliveryID }) {
                    self.historyDeliveries[hIdx].localOverlayPath = fileName
                    print("📥 [Overlay] Updated historyDeliveries[\(hIdx)].localOverlayPath")
                }
                // CRITICAL: Also update selectedDelivery if it's the same delivery (SwiftUI value type issue)
                if self.selectedDelivery?.id == deliveryID {
                    self.selectedDelivery?.localOverlayPath = fileName
                    print("✅ [Overlay] Updated selectedDelivery with local path: \(fileName)")
                } else {
                    print("📥 [Overlay] selectedDelivery is nil or different ID")
                }
                print("✅ [Overlay] ===== DOWNLOAD COMPLETE =====")
            }
        } catch {
            print("⚠️ [Overlay] ===== DOWNLOAD FAILED =====")
            print("⚠️ [Overlay] Error: \(error)")
            print("⚠️ [Overlay] DeliveryID: \(deliveryID)")
        }
    }

    /// Resolves the best available overlay URL (local cache first, then cloud)
    func resolveOverlayURL(for delivery: Delivery) -> URL? {
        // 1. Check local cache first
        if let localPath = delivery.localOverlayPath {
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let localURL = documents.appendingPathComponent("overlays").appendingPathComponent(localPath)
            if FileManager.default.fileExists(atPath: localURL.path) {
                return localURL
            }
        }
        // 2. Fallback to cloud URL
        return delivery.overlayVideoURL
    }

    func toggleFavorite(_ delivery: Delivery) {
        // Find the actual delivery state
        var isTargetFavorite = !delivery.isFavorite
        
        // 1. Sync Session UI
        if let idx = sessionDeliveries.firstIndex(where: { $0.id == delivery.id }) {
            withAnimation {
                sessionDeliveries[idx].isFavorite = isTargetFavorite
            }
        }
        
        // 2. Sync History List & Persistence
        if let hIdx = historyDeliveries.firstIndex(where: { $0.id == delivery.id }) {
            historyDeliveries[hIdx].isFavorite = isTargetFavorite
            // The didSet on historyDeliveries will trigger PersistenceManager saveAll
        }
        
        // 3. Sync Favorites List
        if isTargetFavorite {
            if !favoriteDeliveries.contains(where: { $0.id == delivery.id }) {
                var newFav = delivery
                newFav.isFavorite = true
                favoriteDeliveries.append(newFav)
                print("DEBUG [Fav]: Added \(delivery.sequence) to favorites")
            }
        } else {
            favoriteDeliveries.removeAll { $0.id == delivery.id }
            print("DEBUG [Fav]: Removed \(delivery.sequence) from favorites")
        }
    }
}
