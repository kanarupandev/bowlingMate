import SwiftUI

struct SettingsView: View {
    @Environment(\.presentationMode) var presentationMode
    @Binding var config: String
    @Binding var language: String

    let levels = ["junior", "club", "technical"]
    let languages = ["en", "ta", "hi"]

    @State private var showClearCacheAlert = false
    @State private var cacheCleared = false
    
    var body: some View {
        ZStack {
            DesignSystem.Colors.primary.opacity(0.05).ignoresSafeArea()
            
            VStack(spacing: 32) {
                // Custom Header
                HStack {
                    Text("Settings").font(.system(size: 32, weight: .black, design: .rounded))
                    Spacer()
                    Button(action: { presentationMode.wrappedValue.dismiss() }) {
                        Image(systemName: "xmark.circle.fill").font(.title).foregroundColor(.gray.opacity(0.3))
                    }
                }
                .padding(.horizontal, 30).padding(.top, 40)
                
                VStack(alignment: .leading, spacing: 20) {
                    SettingSection(title: "Coaching Level") {
                        Picker("Level", selection: $config) {
                            ForEach(levels, id: \.self) { level in
                                Text(level.capitalized).tag(level)
                            }
                        }
                        .pickerStyle(SegmentedPickerStyle())
                    }
                    
                    SettingSection(title: "Analysis Language") {
                        Picker("Language", selection: $language) {
                            ForEach(languages, id: \.self) { lang in
                                Text(lang.uppercased()).tag(lang)
                            }
                        }
                        .pickerStyle(SegmentedPickerStyle())
                    }

                    SettingSection(title: "Developer Tools") {
                        Button(action: { showClearCacheAlert = true }) {
                            HStack {
                                Image(systemName: "trash.circle.fill")
                                    .font(.system(size: 20))
                                    .foregroundColor(.red)
                                Text("Clear All Caches")
                                    .font(.system(size: 15, weight: .medium))
                                    .foregroundColor(.primary)
                                Spacer()
                                if cacheCleared {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundColor(.green)
                                }
                            }
                            .padding(.vertical, 4)
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                }
                .padding(.horizontal, 20)

                Spacer()

                Text("wellBowled v1.0 • Gemini 3 Hackathon")
                    .font(.caption).bold().foregroundColor(.gray.opacity(0.5))
                    .padding(.bottom, 30)
            }
        }
        .alert("Clear All Caches?", isPresented: $showClearCacheAlert) {
            Button("Cancel", role: .cancel) { }
            Button("Clear", role: .destructive) {
                clearAllCaches()
                cacheCleared = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    cacheCleared = false
                }
            }
        } message: {
            Text("This will delete all cached videos, overlays, thumbnails, and saved deliveries. The app will restart fresh.")
        }
    }

    private func clearAllCaches() {
        let fileManager = FileManager.default
        let documentsURL = fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]

        // Clear favorites.json
        let favoritesURL = documentsURL.appendingPathComponent("favorites.json")
        try? fileManager.removeItem(at: favoritesURL)

        // Clear all_deliveries.json
        let allDeliveriesURL = documentsURL.appendingPathComponent("all_deliveries.json")
        try? fileManager.removeItem(at: allDeliveriesURL)

        // Clear thumbnails directory
        let thumbnailsURL = documentsURL.appendingPathComponent("thumbnails")
        try? fileManager.removeItem(at: thumbnailsURL)

        // Clear overlays directory
        let overlaysURL = documentsURL.appendingPathComponent("overlays")
        try? fileManager.removeItem(at: overlaysURL)

        // Clear ThumbnailCache (NSCache + disk cache in cachesDirectory)
        ThumbnailCache.shared.clear()

        print("🗑️ All caches cleared successfully")
    }
}

struct SettingSection<Content: View>: View {
    let title: String
    let content: Content
    
    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }
    
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title.uppercased()).font(.caption2).bold().foregroundColor(.secondary).padding(.leading, 10)
            content
                .padding(12)
                .background(Color.white)
                .cornerRadius(16)
                .shadow(color: .black.opacity(0.05), radius: 5, x: 0, y: 2)
        }
    }
}
