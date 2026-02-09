import Foundation
import UIKit

class PersistenceManager: Sendable {
    static let shared = PersistenceManager()
    private let fileName = "favorites.json"
    
    private var fileURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent(fileName)
    }

    private var allDeliveriesURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("all_deliveries.json")
    }

    private var thumbnailsDirectory: URL {
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("thumbnails")
        try? FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
    
    func save(_ deliveries: [Delivery]) {
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = .prettyPrinted
            let data = try encoder.encode(deliveries)
            try data.write(to: fileURL)
            L("Saved \(deliveries.count) FAVORITE deliveries to disk.", .success)
        } catch {
            L("Failed to save deliveries: \(error)", .error)
        }
    }
    
    func load() -> [Delivery] {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return [] }
        do {
            let data = try Data(contentsOf: fileURL)
            let deliveries = try JSONDecoder().decode([Delivery].self, from: data)
            print("📂 Loaded \(deliveries.count) FAVORITE deliveries from disk.")
            return deliveries
        } catch {
            print("❌ Failed to load favorites: \(error)")
            return []
        }
    }

    func saveAll(_ deliveries: [Delivery]) {
        do {
            let data = try JSONEncoder().encode(deliveries)
            try data.write(to: allDeliveriesURL)
        } catch {
            print("❌ Failed to save all deliveries: \(error)")
        }
    }

    func loadAll() -> [Delivery] {
        guard FileManager.default.fileExists(atPath: allDeliveriesURL.path) else { return [] }
        do {
            let data = try Data(contentsOf: allDeliveriesURL)
            return try JSONDecoder().decode([Delivery].self, from: data)
        } catch {
            return []
        }
    }

    func saveThumbnail(_ image: UIImage, for deliveryID: UUID) -> String? {
        let fileName = "\(deliveryID.uuidString).jpg"
        let fileURL = thumbnailsDirectory.appendingPathComponent(fileName)
        guard let data = image.jpegData(compressionQuality: 0.7) else { return nil }
        do {
            try data.write(to: fileURL)
            return fileName
        } catch {
            print("❌ Failed to save thumbnail: \(error)")
            return nil
        }
    }

    func loadThumbnail(named fileName: String) -> UIImage? {
        let fileURL = thumbnailsDirectory.appendingPathComponent(fileName)
        return UIImage(contentsOfFile: fileURL.path)
    }
}
