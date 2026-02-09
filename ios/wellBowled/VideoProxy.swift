import SwiftUI
import UIKit
import Combine

/// Manages lazy loading of thumbnails and videos using the proxy pattern.
/// Thumbnails load immediately (small JPEG), videos load on-demand.
class VideoProxy: ObservableObject {
    enum State: Equatable {
        case placeholder
        case thumbnail
        case loading
        case ready
        case failed
    }
    
    let deliveryId: String
    let cloudThumbnailURL: URL?
    let cloudVideoURL: URL?
    
    @Published var state: State = .placeholder
    @Published var thumbnail: UIImage?
    @Published var localVideoURL: URL?
    
    private static let cache = ThumbnailCache.shared
    
    init(deliveryId: String, cloudThumbnailURL: URL?, cloudVideoURL: URL?) {
        self.deliveryId = deliveryId
        self.cloudThumbnailURL = cloudThumbnailURL
        self.cloudVideoURL = cloudVideoURL
    }
    
    /// Load thumbnail (called on appear)
    func loadThumbnail() {
        guard thumbnail == nil, let url = cloudThumbnailURL else { return }
        
        // Check cache first
        if let cached = Self.cache.get(for: deliveryId) {
            self.thumbnail = cached
            self.state = .thumbnail
            return
        }
        
        // Download async
        Task {
            do {
                let (data, _) = try await URLSession.shared.data(from: url)
                if let image = UIImage(data: data) {
                    await MainActor.run {
                        self.thumbnail = image
                        self.state = .thumbnail
                        Self.cache.set(image, for: deliveryId)
                    }
                }
            } catch {
                print("Thumbnail load failed: \(error)")
            }
        }
    }
    
    /// Load full video (called on focus/tap)
    func loadFullVideo() async {
        guard localVideoURL == nil, let url = cloudVideoURL else { return }
        
        await MainActor.run { self.state = .loading }
        
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            
            // Save to temp
            let tempDir = FileManager.default.temporaryDirectory
            let localURL = tempDir.appendingPathComponent("\(deliveryId).mp4")
            try data.write(to: localURL)
            
            await MainActor.run {
                self.localVideoURL = localURL
                self.state = .ready
            }
        } catch {
            await MainActor.run { self.state = .failed }
            print("Video load failed: \(error)")
        }
    }
    /// Prefetch the video content for the top N items in a list
    @MainActor
    static func prefetch(proxies: [VideoProxy], limit: Int = 3) {
        print("🚀 [Proxy] Prefetching top \(limit) videos...")
        for (index, proxy) in proxies.enumerated() where index < limit {
            Task {
                await proxy.loadFullVideo()
            }
        }
    }
}


/// Singleton cache for thumbnails with NSCache (memory) and disk backing.
class ThumbnailCache: @unchecked Sendable {
    static let shared = ThumbnailCache()
    
    private let memoryCache = NSCache<NSString, UIImage>()
    private let diskCacheURL: URL
    
    private init() {
        memoryCache.countLimit = 50
        
        let docs = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first!
        diskCacheURL = docs.appendingPathComponent("thumbnails")
        try? FileManager.default.createDirectory(at: diskCacheURL, withIntermediateDirectories: true)
    }
    
    func get(for id: String) -> UIImage? {
        // Memory first
        if let cached = memoryCache.object(forKey: id as NSString) {
            return cached
        }
        
        // Disk fallback
        let diskPath = diskCacheURL.appendingPathComponent("\(id).jpg")
        if let data = try? Data(contentsOf: diskPath),
           let image = UIImage(data: data) {
            memoryCache.setObject(image, forKey: id as NSString)
            return image
        }
        
        return nil
    }
    
    func set(_ image: UIImage, for id: String) {
        memoryCache.setObject(image, forKey: id as NSString)
        
        // Persist to disk
        let diskPath = diskCacheURL.appendingPathComponent("\(id).jpg")
        if let data = image.jpegData(compressionQuality: 0.8) {
            try? data.write(to: diskPath)
        }
    }
    
    func clear() {
        memoryCache.removeAllObjects()
        try? FileManager.default.removeItem(at: diskCacheURL)
        try? FileManager.default.createDirectory(at: diskCacheURL, withIntermediateDirectories: true)
    }
}
