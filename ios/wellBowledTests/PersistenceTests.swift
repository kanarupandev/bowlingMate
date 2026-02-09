import XCTest
import AVFoundation
@testable import wellBowled

@MainActor
final class PersistenceTests: XCTestCase {
    
    var persistence: PersistenceManager!
    
    override func setUp() {
        super.setUp()
        persistence = PersistenceManager()
        // Clear before tests
        persistence.save([])
        persistence.saveAll([])
    }
    
    func testSaveAndLoadFavorites() {
        let delivery = Delivery(timestamp: 10.0, sequence: 1)
        persistence.save([delivery])
        
        let loaded = persistence.load()
        XCTAssertEqual(loaded.count, 1)
        XCTAssertEqual(loaded.first?.id, delivery.id)
    }
    
    func testSaveAndLoadHistory() {
        let delivery1 = Delivery(timestamp: 5.0, sequence: 1)
        let delivery2 = Delivery(timestamp: 15.0, sequence: 2)
        persistence.saveAll([delivery1, delivery2])
        
        let loaded = persistence.loadAll()
        XCTAssertEqual(loaded.count, 2)
    }

    func testThumbnailPersistence() {
        let testID = UUID()
        let size = CGSize(width: 100, height: 100)
        let rect = CGRect(origin: .zero, size: size)
        UIGraphicsBeginImageContextWithOptions(size, false, 0)
        UIColor.red.setFill()
        UIRectFill(rect)
        let image = UIGraphicsGetImageFromCurrentImageContext()!
        UIGraphicsEndImageContext()
        
        let savedPath = persistence.saveThumbnail(image, for: testID)
        XCTAssertNotNil(savedPath)
        XCTAssertEqual(savedPath, "\(testID.uuidString).jpg")
        
        let loadedImage = persistence.loadThumbnail(named: savedPath!)
        XCTAssertNotNil(loadedImage)
    }
}
