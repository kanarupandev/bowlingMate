import Foundation
import AVFoundation

class PassthroughClipper {
    /// Exports a specific time range of a video without re-encoding.
    /// This uses the Documents directory to avoid sandbox/temporary mapping permission errors.
    /// - Parameter timeoutSeconds: Override default timeout (useful for longer source videos)
    static func clip(sourceURL: URL, startTime: Double, duration: Double, preset: String, timeoutSeconds: Int = 30) async throws -> URL {
        print("DEBUG [Clipper]: Initializing extraction for \(startTime)s using preset: \(preset), timeout: \(timeoutSeconds)s")

        return try await withThrowingTaskGroup(of: URL.self) { group in
            // Task 1: The Work (Load + Export)
            group.addTask {
                let asset = AVAsset(url: sourceURL)
                // This await is now cancellable/raceable
                _ = try? await asset.load(.tracks, .duration)

                // ... rest of setup ...
                let fileManager = FileManager.default
                let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first!
                let outputDir = documentsURL.appendingPathComponent("wellBowled_clips", isDirectory: true)
                try? fileManager.createDirectory(at: outputDir, withIntermediateDirectories: true)
                let outputURL = outputDir.appendingPathComponent("clip_\(UUID().uuidString).mov")

                guard let exportSession = AVAssetExportSession(asset: asset, presetName: preset) else {
                    // Fallback handled synchronously here for simplicity in race
                    // In a real reckless mode we just skip passthrough if failed
                     throw NSError(domain: "ClipperError", code: 5, userInfo: [NSLocalizedDescriptionKey: "Passthrough Init Failed. Preset not compatible?"])
                }

                exportSession.outputURL = outputURL
                exportSession.outputFileType = .mov
                exportSession.timeRange = CMTimeRange(start: CMTime(seconds: startTime, preferredTimescale: 600), duration: CMTime(seconds: duration, preferredTimescale: 600))

                await withTaskCancellationHandler {
                    await withCheckedContinuation { continuation in
                        exportSession.exportAsynchronously {
                            if exportSession.status == .completed {
                                continuation.resume()
                            } else {
                                continuation.resume() // Resume anyway, we check status or throw
                            }
                        }
                    }
                } onCancel: {
                    exportSession.cancelExport()
                }

                if exportSession.status == .completed {
                    return outputURL
                } else {
                     throw NSError(domain: "ClipperError", code: 2, userInfo: [NSLocalizedDescriptionKey: "Export Failed: \(exportSession.error?.localizedDescription ?? "n/a")"])
                }
            }

            // Task 2: The Timer (Insurance against hardware hang)
            group.addTask {
                try await Task.sleep(nanoseconds: UInt64(timeoutSeconds) * 1_000_000_000)
                throw NSError(domain: "ClipperError", code: 99, userInfo: [NSLocalizedDescriptionKey: "Hardware Timeout (\(timeoutSeconds)s)"])
            }

            // Wait for first result
            let result = try await group.next()!
            group.cancelAll()
            return result
        }
    }
    
    // Fallback not needed if we just fail fast
    private static func fallbackClip(asset: AVAsset, startTime: Double, duration: Double, outputURL: URL) async throws -> URL {
        return outputURL 
    }
}
