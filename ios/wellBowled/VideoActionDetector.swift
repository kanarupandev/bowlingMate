import Foundation
import Vision
import AVFoundation
import Combine

class VideoActionDetector: NSObject, ObservableObject, VisionEngine {
    
    // For VisionEngine Protocol
    func findBowlingPeak(in asset: AVAsset, startTime: Double) async -> Double? {
        print("🔍 Scouting for peak starting at \(startTime)s")
        return await processVideoForPeak(asset: asset, startTime: startTime, duration: ClipConfig.chunkDuration)
    }

    // MARK: - Cloud Scouting Logic (Gemini Flash)
    
    private func processVideoForPeak(asset: AVAsset, startTime: Double, duration: Double) async -> Double? {
        // Safe clamping to avoid export failure at end of video
        let assetDuration = (try? await asset.load(.duration).seconds) ?? 0
        let safeDuration = min(duration, assetDuration - startTime)
        
        if safeDuration < 1.0 { return nil } // Skip tiny tail chunks
        
        print("☁️ [Cloud Engine] Analyzing Segment: \(startTime)s - \(startTime + safeDuration)s")
        
        let range = CMTimeRange(start: CMTime(seconds: startTime, preferredTimescale: 600),
                               duration: CMTime(seconds: safeDuration, preferredTimescale: 600))
        
        // Export Chunk to Temp File (Optimized for upload speed)
        guard let exportSession = AVAssetExportSession(asset: asset, presetName: ClipConfig.scoutExportPreset) else { return nil }
        
        let tempUrl = FileManager.default.temporaryDirectory.appendingPathComponent("chunk_\(UUID().uuidString).mp4")
        exportSession.outputURL = tempUrl
        exportSession.outputFileType = .mp4
        exportSession.timeRange = range // Crucial: Clip exactly what was asked
        exportSession.shouldOptimizeForNetworkUse = true
        
        await exportSession.export()
        
        if exportSession.status == .completed {
            // Verify file actually exists
            if FileManager.default.fileExists(atPath: tempUrl.path) {
                print("✅ [Clipper] Chunk export successful: \(tempUrl.path)")
                // Call Network Service
                let resultResult: Result<ActionDetectionResult, Error>
                do {
                    let detection = try await CompositeNetworkService.shared.detectAction(videoChunkURL: tempUrl)
                    resultResult = .success(detection)
                } catch {
                    resultResult = .failure(error)
                }
                
                // Cleanup matches
                try? FileManager.default.removeItem(at: tempUrl)
                
                switch resultResult {
                case .success(let detection):
                    if detection.found, let timeInChunk = detection.deliveries_detected_at_time.first {
                        let absoluteTime = startTime + timeInChunk
                        print("✅ [Gemini] FOUND DELIVERY at \(absoluteTime)s (Chunk offset: \(timeInChunk)s)")
                        return absoluteTime
                    } else {
                        print("🚫 [Gemini] No delivery in this segment. JSON: \(detection)")
                    }
                case .failure(let error):
                    print("❌ [Gemini] Detection request failed: \(error.localizedDescription)")
                }
            } else {
                 print("❌ [Clipper] Export reported success but file is MISSING at \(tempUrl.path)")
            }
        } else {
            print("❌ [Clipper] Export failed: \(exportSession.error?.localizedDescription ?? "Unknown error")")
        }
        
        return nil
    }
}
