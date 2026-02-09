import Foundation
import AVFoundation

protocol VisionEngine: AnyObject {
    /// Scans an asset for the 'Peak' of a bowling motion starting from a specific time.
    func findBowlingPeak(in asset: AVAsset, startTime: Double) async -> Double?
}
