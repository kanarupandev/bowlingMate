import Foundation
import UIKit

enum LogLevel: String {
    case info = "ℹ️"
    case warning = "⚠️"
    case error = "❌"
    case success = "✅"
    case performance = "⏱️"
    case network = "📡"
    case debug = "🔍"
}

class AppLogger {
    static let shared = AppLogger()
    
    func log(_ message: String, level: LogLevel = .info, file: String = #file, function: String = #function, line: Int = #line) {
        let fileName = (file as NSString).lastPathComponent
        let timestamp = ISO8601DateFormatter().string(from: Date())
        
        #if DEBUG
        print("\(level.rawValue) [\(timestamp)] [\(fileName):\(line)] \(function) -> \(message)")
        #endif
    }
}

// Global helper for easy access
func L(_ message: String, _ level: LogLevel = .info, file: String = #file, function: String = #function, line: Int = #line) {
    AppLogger.shared.log(message, level: level, file: file, function: function, line: line)
}
