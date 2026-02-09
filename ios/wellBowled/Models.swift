import Foundation
import CoreTransferable
import UniformTypeIdentifiers
import UIKit

struct MovieFile: Transferable {
    let url: URL
    
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let startTime = CACurrentMediaTime()
            print("📦 [PERF] MovieFile: Import initiated at \(received.file.lastPathComponent)")
            
            let fileName = "upload_\(UUID().uuidString).mov"
            let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            let destinationURL = documents.appendingPathComponent(fileName)
            
            do {
                // Strategic Move: Much faster than Copy on the same volume
                // PhotoPicker usually provides a temporary file we can 'claim'
                try FileManager.default.moveItem(at: received.file, to: destinationURL)
                let elapsed = CACurrentMediaTime() - startTime
                print("✅ [PERF] MovieFile: Import Complete (Move). Elapsed: \(String(format: "%.3f", elapsed))s")
                return Self(url: destinationURL)
            } catch {
                print("⚠️ [PERF] MovieFile: Move failed (\(error.localizedDescription)). Retrying with Copy...")
                try? FileManager.default.copyItem(at: received.file, to: destinationURL)
                let elapsed = CACurrentMediaTime() - startTime
                print("✅ [PERF] MovieFile: Import Complete (Copy Fallback). Elapsed: \(String(format: "%.3f", elapsed))s")
                return Self(url: destinationURL)
            }
        }
    }
}

enum DeliveryStatus: String, Codable {
    case detecting = "LOCAL VISION SCAN"  // Native On-Device Vision
    case clipping = "TRIMMING CLIP"        // Local trimming of the 5s action
    case queued = "QUEUED FOR AI"         // Waiting in the prefetcher queue
    case uploading = "AI SYNC"            // Sending to Gemini
    case processing = "REASONING (AI)"    // Gemini scanning the frames
    case analyzing = "TECHNICAL AUDIT"     // AI calculating speed/form
    case success = "QUALIFIED"
    case failed = "REJECTED"
}

struct Delivery: Identifiable, Equatable, Codable {
    let id: UUID
    let timestamp: Double
    var report: String?
    var speed: String?
    var tips: [String]
    var phases: [AnalysisPhase]? // Detailed phase breakdown from Coach
    var releaseTimestamp: Double?
    var status: DeliveryStatus
    var videoURL: URL?
    var thumbnail: UIImage?
    var sequence: Int

    // Cloud/Analysis Handshakes
    var videoID: String?
    var cloudVideoURL: URL?
    var cloudThumbnailURL: URL?
    var overlayVideoURL: URL? // MediaPipe biomechanics overlay (cloud)
    var localOverlayPath: String? // Filename in Documents/overlays/ (persisted)
    var isFavorite: Bool
    var localThumbnailPath: String? // Filename in Documents/thumbnails/
    var localVideoPath: String?     // Filename in Documents/

    enum CodingKeys: String, CodingKey {
        case id, timestamp, report, speed, tips, phases, releaseTimestamp, status, videoURL, sequence, videoID, cloudVideoURL, cloudThumbnailURL, overlayVideoURL, localOverlayPath, isFavorite, localThumbnailPath, localVideoPath
    }
    
    init(id: UUID = UUID(),
         timestamp: Double,
         report: String? = nil,
         speed: String? = nil,
         tips: [String] = [],
         phases: [AnalysisPhase]? = nil,
         releaseTimestamp: Double? = nil,
         status: DeliveryStatus = .detecting,
         videoURL: URL? = nil,
         thumbnail: UIImage? = nil,
         sequence: Int,
         videoID: String? = nil,
         cloudVideoURL: URL? = nil,
         cloudThumbnailURL: URL? = nil,
         overlayVideoURL: URL? = nil,
         localOverlayPath: String? = nil,
         isFavorite: Bool = false,
         localThumbnailPath: String? = nil,
         localVideoPath: String? = nil) {
        self.id = id
        self.timestamp = timestamp
        self.report = report
        self.speed = speed
        self.tips = tips
        self.phases = phases
        self.releaseTimestamp = releaseTimestamp
        self.status = status
        self.videoURL = videoURL
        self.thumbnail = thumbnail
        self.sequence = sequence
        self.videoID = videoID
        self.cloudVideoURL = cloudVideoURL
        self.cloudThumbnailURL = cloudThumbnailURL
        self.overlayVideoURL = overlayVideoURL
        self.localOverlayPath = localOverlayPath
        self.isFavorite = isFavorite
        self.localThumbnailPath = localThumbnailPath
        self.localVideoPath = localVideoPath
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(UUID.self, forKey: .id)
        timestamp = try container.decode(Double.self, forKey: .timestamp)
        report = try container.decodeIfPresent(String.self, forKey: .report)
        speed = try container.decodeIfPresent(String.self, forKey: .speed)
        tips = try container.decode([String].self, forKey: .tips)
        phases = try container.decodeIfPresent([AnalysisPhase].self, forKey: .phases)
        releaseTimestamp = try container.decodeIfPresent(Double.self, forKey: .releaseTimestamp)
        status = try container.decode(DeliveryStatus.self, forKey: .status)
        videoURL = try container.decodeIfPresent(URL.self, forKey: .videoURL)
        sequence = try container.decode(Int.self, forKey: .sequence)
        videoID = try container.decodeIfPresent(String.self, forKey: .videoID)
        cloudVideoURL = try container.decodeIfPresent(URL.self, forKey: .cloudVideoURL)
        cloudThumbnailURL = try container.decodeIfPresent(URL.self, forKey: .cloudThumbnailURL)
        overlayVideoURL = try container.decodeIfPresent(URL.self, forKey: .overlayVideoURL)
        localOverlayPath = try container.decodeIfPresent(String.self, forKey: .localOverlayPath)
        isFavorite = try container.decode(Bool.self, forKey: .isFavorite)
        localThumbnailPath = try container.decodeIfPresent(String.self, forKey: .localThumbnailPath)
        localVideoPath = try container.decodeIfPresent(String.self, forKey: .localVideoPath)
        thumbnail = nil // UIImage must be loaded from Disk via localThumbnailPath
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(timestamp, forKey: .timestamp)
        try container.encode(report, forKey: .report)
        try container.encode(speed, forKey: .speed)
        try container.encode(tips, forKey: .tips)
        try container.encode(phases, forKey: .phases)
        try container.encode(releaseTimestamp, forKey: .releaseTimestamp)
        try container.encode(status, forKey: .status)
        try container.encode(videoURL, forKey: .videoURL)
        try container.encode(sequence, forKey: .sequence)
        try container.encode(videoID, forKey: .videoID)
        try container.encode(cloudVideoURL, forKey: .cloudVideoURL)
        try container.encode(cloudThumbnailURL, forKey: .cloudThumbnailURL)
        try container.encode(overlayVideoURL, forKey: .overlayVideoURL)
        try container.encode(localOverlayPath, forKey: .localOverlayPath)
        try container.encode(isFavorite, forKey: .isFavorite)
        try container.encode(localThumbnailPath, forKey: .localThumbnailPath)
        try container.encode(localVideoPath, forKey: .localVideoPath)
    }
    
    static func == (lhs: Delivery, rhs: Delivery) -> Bool {
        return lhs.id == rhs.id &&
               lhs.status == rhs.status &&
               lhs.videoURL == rhs.videoURL &&
               lhs.timestamp == rhs.timestamp &&
               lhs.releaseTimestamp == rhs.releaseTimestamp &&
               lhs.report == rhs.report &&
               lhs.speed == rhs.speed &&
               lhs.tips == rhs.tips &&
               lhs.phases == rhs.phases &&
               lhs.isFavorite == rhs.isFavorite &&
               lhs.sequence == rhs.sequence &&
               lhs.localOverlayPath == rhs.localOverlayPath
    }
}

struct StreamingEvent: Identifiable {
    let id = UUID()
    let timestamp = Date()
    let message: String
    let type: String // info, process, error
}

// MARK: - Analysis Phase (from Coach response)
struct AnalysisPhase: Identifiable, Codable, Equatable {
    let id: UUID
    let name: String
    let status: String // "GOOD" or "NEEDS WORK"
    let observation: String
    let tip: String
    let clipTimestamp: Double? // Timestamp in clip where this phase is visible

    var isGood: Bool { status.uppercased().contains("GOOD") }

    enum CodingKeys: String, CodingKey {
        case name, status, observation, tip
        case clipTimestamp = "clip_ts"
    }

    init(id: UUID = UUID(), name: String, status: String, observation: String = "", tip: String = "", clipTimestamp: Double? = nil) {
        self.id = id
        self.name = name
        self.status = status
        self.observation = observation
        self.tip = tip
        self.clipTimestamp = clipTimestamp
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = UUID()
        self.name = try container.decode(String.self, forKey: .name)
        self.status = try container.decode(String.self, forKey: .status)
        self.observation = try container.decodeIfPresent(String.self, forKey: .observation) ?? ""
        self.tip = try container.decodeIfPresent(String.self, forKey: .tip) ?? ""
        self.clipTimestamp = try container.decodeIfPresent(Double.self, forKey: .clipTimestamp)
    }
}
