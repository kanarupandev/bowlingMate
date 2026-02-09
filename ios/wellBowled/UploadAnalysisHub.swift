import SwiftUI

struct UploadAnalysisHub: View {
    @ObservedObject var viewModel: BowlViewModel
    
    var body: some View {
        ZStack {
            VStack(spacing: 0) {
                // 1. GLASS TELEMETRY CONSOLE
                // 0. GLOBAL CONNECTION ERROR
                if viewModel.isBackendOffline {
                    HStack {
                        Image(systemName: "wifi.slash")
                        Text(viewModel.connectionError ?? "Connection Lost")
                            .font(.system(size: 12, weight: .bold))
                        Spacer()
                    }
                    .padding()
                    .background(DesignSystem.Colors.error.opacity(0.8))
                    .foregroundColor(.white)
                    .cornerRadius(12)
                    .padding(.horizontal)
                    .padding(.top, 10)
                }

                // 1. ENGINE CONFIGURATION TOGGLE
                if AppConfig.showEngineTelemetry {
                    StreamingLogView(logs: viewModel.streamingLogs)
                        .padding(.horizontal, 20)
                    
                    HStack {
                        Circle().fill(DesignSystem.Colors.primary).frame(width: 4, height: 4)
                        Text("CLOUD ENGINE CONSOLE")
                            .font(.system(size: 8, weight: .black))
                            .foregroundColor(.white.opacity(0.3))
                            .tracking(1.5)
                    }
                    .padding(.top, 8)
                    
                    Rectangle()
                        .fill(Color.white.opacity(0.05))
                        .frame(height: 1)
                        .padding(.vertical, 16)
                } else {
                    // PERSISTENT STATUS HEADER (Visible during discovery)
                    if let status = viewModel.scoutingStatus {
                        VStack(spacing: 0) {
                            HStack(spacing: 8) {
                                if (status.contains("Scanning") || status.contains("Looking") || status.contains("Processing")) && !status.contains("Complete") {
                                    ProgressView()
                                        .tint(DesignSystem.Colors.primary)
                                        .scaleEffect(0.7)
                                } else if status.contains("Complete") {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundColor(DesignSystem.Colors.accent)
                                        .font(.system(size: 14))
                                }
                                
                                Text(status.uppercased())
                                    .font(.system(size: 10, weight: .black))
                                    .foregroundColor(.white.opacity(0.6))
                                    .tracking(1.5)
                            }
                            
                            // Thin Lime-Green Progress Bar
                            ZStack(alignment: .leading) {
                                Rectangle()
                                    .fill(Color.white.opacity(0.05))
                                    .frame(height: 2)
                                
                                GeometryReader { proxy in
                                    Rectangle()
                                        .fill(DesignSystem.Colors.primary)
                                        .frame(width: proxy.size.width * CGFloat(viewModel.scoutingProgress), height: 2)
                                        .animation(.linear, value: viewModel.scoutingProgress)
                                }
                            }
                            .frame(height: 2)
                            .padding(.top, 8)
                        }
                        .padding(.vertical, 12)
                        .padding(.horizontal, 24)
                        .background(Color.white.opacity(0.05))
                        .cornerRadius(20)
                        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.white.opacity(0.05), lineWidth: 0.5))
                        .transition(.move(edge: .top).combined(with: .opacity))
                        .padding(.top, 10)
                    } else {
                         Spacer().frame(height: 20)
                    }
                }
                
                // 2. MAIN INTERFACE LOGIC
                // Horizontal Carousel or Empty State
                if viewModel.sessionDeliveries.isEmpty {
                     VStack(spacing: 20) {
                        Image(systemName: "video.badge.plus")
                            .font(.system(size: 60))
                            .foregroundColor(.white.opacity(0.2))
                        if !viewModel.isImporting {
                            Text(viewModel.scoutingStatus ?? "SYSTEM IDLE")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(.white.opacity(0.4))
                            
                            if viewModel.scoutingStatus == nil {
                                 Text("Record or upload videos to start analysis.")
                                    .font(.system(size: 14))
                                    .foregroundColor(.white.opacity(0.3))
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    PageCarousel(
                        deliveries: viewModel.sessionDeliveries,
                        viewModel: viewModel,
                        currentID: $viewModel.currentCarouselID // We need to bind this to persist/track
                    )
                }
            }
        }
        .background(Color.black.ignoresSafeArea())
        .onAppear {
            print("👁️ [VIEW] UploadAnalysisHub appeared")
            print("   └─ Deliveries: \(viewModel.sessionDeliveries.count)")
        }
        .onDisappear {
            print("👁️ [VIEW] UploadAnalysisHub disappeared")
            print("   └─ Discovery task still running: \(viewModel.isDiscoveryTaskRunning)")
        }
    }
}

// Sub-view to manage local state cleanly or bind upwards
struct PageCarousel: View {
    let deliveries: [Delivery]
    @ObservedObject var viewModel: BowlViewModel
    @Binding var currentID: UUID?
    
    var body: some View {
        GeometryReader { geometry in
            TabView(selection: $currentID) {
                ForEach(deliveries, id: \.id) { delivery in
                    UploadDeliveryCard(
                        delivery: delivery,
                        isActive: currentID == delivery.id,
                        onAnalyze: { viewModel.requestAnalysis(for: delivery) },
                        onDelete: {
                            // iOS-standard delete: slide to neighbor, then remove with fade
                            let allIDs = deliveries.map { $0.id }
                            if let currentIndex = allIDs.firstIndex(of: delivery.id) {
                                let nextID: UUID? = (currentIndex + 1 < allIDs.count) ? allIDs[currentIndex + 1] : (currentIndex > 0 ? allIDs[currentIndex - 1] : nil)

                                if let targetID = nextID {
                                    // 1. Smooth slide to neighbor
                                    withAnimation(.easeInOut(duration: 0.35)) {
                                        currentID = targetID
                                    }

                                    // 2. Remove after slide completes (standard iOS timing)
                                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
                                        withAnimation(.easeOut(duration: 0.25)) {
                                            viewModel.deleteDelivery(delivery)
                                        }
                                    }
                                } else {
                                    // Last item - fade out gracefully
                                    withAnimation(.easeOut(duration: 0.3)) {
                                        viewModel.deleteDelivery(delivery)
                                    }
                                }
                            }
                        },
                        onFavorite: { viewModel.toggleFavorite(delivery) },
                        onSelect: { viewModel.selectDelivery(delivery) },
                        isAnyAnalysisRunning: viewModel.isAnyAnalysisRunning,
                        resolveOverlayURL: { viewModel.resolveOverlayURL(for: $0) }
                    )
                    .frame(maxWidth: UIDevice.current.userInterfaceIdiom == .pad ? 500 : .infinity)
                    .tag(delivery.id as UUID?) // Explicit cast for optional binding match
                    .padding(.horizontal, UIDevice.current.userInterfaceIdiom == .pad ? max(0, (geometry.size.width - 500) / 2) : 0)
                    .padding(.vertical, 20) // Give room to breathe
                    .transition(.asymmetric(
                        insertion: .scale(scale: 0.95).combined(with: .opacity),
                        removal: .scale(scale: 0.9).combined(with: .opacity)
                    ))
                }
            }
            .tabViewStyle(PageTabViewStyle(indexDisplayMode: .always))
        }
        .onAppear {
            print("🎠 [CAROUSEL] Appeared with \(deliveries.count) deliveries")
            if currentID == nil {
                currentID = deliveries.first?.id
            }
        }
        .onDisappear {
            print("🎠 [CAROUSEL] Disappeared, currentID: \(currentID?.uuidString.prefix(8) ?? "nil")")
        }
        .onChange(of: deliveries.count) { oldValue, newValue in
            // Handle deletion edge cases (if current is deleted, move to nearest)
             if currentID == nil || !deliveries.contains(where: { $0.id == currentID }) {
                 currentID = deliveries.first?.id
             }
        }
    }
}
