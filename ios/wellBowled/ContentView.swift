import SwiftUI
import AVFoundation
import PhotosUI

struct ContentView: View {
    @StateObject private var cameraManager = CameraManager()
    @StateObject private var detector = VideoActionDetector()
    @StateObject private var viewModel: BowlViewModel
    
    @State private var showingSettings = false
    @State private var selectedItem: PhotosPickerItem? = nil
    
    init() {
        let camera = CameraManager()
        let detect = VideoActionDetector()
        _cameraManager = StateObject(wrappedValue: camera)
        _detector = StateObject(wrappedValue: detect)
        _viewModel = StateObject(wrappedValue: BowlViewModel(cameraManager: camera, detector: detect))
    }
    
    var body: some View {
        ZStack {
            // 0. Base Layer (Constant Dark Background)
            DesignSystem.Colors.background.ignoresSafeArea()
            
            // 1. Background Content (Camera or Hub Animation)
            Group {
                if viewModel.uiMode == .live {
                    CameraPreview(session: cameraManager.session)
                        .ignoresSafeArea()
                        .transition(.opacity)
                } else {
                    UploadBackgroundView()
                        .transition(.opacity)
                }
            }
            .zIndex(0)
            
            // 2. Main UI Layer
            VStack(spacing: 0) {
                HeaderView(
                    isRecording: cameraManager.isRecording,
                    uiMode: viewModel.uiMode,
                    hasActiveSession: !viewModel.sessionDeliveries.isEmpty,
                    selectedItem: $selectedItem,
                    onBackTap: { 
                        L("Home button clicked. Session count: \(viewModel.sessionDeliveries.count)", .info)
                        
                        withAnimation {
                            viewModel.uiMode = .live
                        }
                    },
                    onHistoryTap: { viewModel.uiMode = .history },
                    onFavoritesTap: { viewModel.uiMode = .favorites },
                    onResumeSession: { viewModel.uiMode = .upload },
                    onSettingsTap: { showingSettings.toggle() }
                )
                
                if cameraManager.isRecording {
                    RecordingIndicatorView(duration: viewModel.timeRemaining)
                        .padding(.top, 8)
                        .transition(.opacity)
                }
                
                if viewModel.uiMode == .live {
                    Spacer()
                    
                    ControlCenterView(
                        isRecording: cameraManager.isRecording,
                        onToggle: {
                            withAnimation {
                                viewModel.toggleRecording()
                            }
                        },
                        onFlip: {
                            cameraManager.flipCamera()
                        }
                    )
                    .transition(.opacity)
                }
                
                if viewModel.uiMode == .history {
                    // History View - Now using persistent historyDeliveries
                    HistoryView(
                        deliveries: viewModel.historyDeliveries, 
                        onSelect: { delivery in viewModel.selectDelivery(delivery) },
                        onAnalyze: { delivery in viewModel.requestAnalysis(for: delivery) },
                        onDelete: { delivery in viewModel.deleteDelivery(delivery) },
                        onFavorite: { delivery in viewModel.toggleFavorite(delivery) },
                        isAnyAnalysisRunning: viewModel.isAnyAnalysisRunning
                    )
                    .transition(.move(edge: .bottom))
                } else if viewModel.uiMode == .favorites {
                    FavoritesView(viewModel: viewModel)
                        .transition(.move(edge: .trailing))
                } else if viewModel.uiMode == .upload {
                    // Analysis Hub (Only for Upload mode)
                    UploadAnalysisHub(viewModel: viewModel)
                        .transition(.move(edge: .trailing))
                }
                // In .live mode, we show nothing here (letting CameraPreview show through)
            }
            .zIndex(1)
            
            // 3. Detail Overlay - Show AnalysisResultView if phases available
            // Pass viewModel directly so view observes changes (not a snapshot)
            if viewModel.selectedDelivery != nil {
                if let phases = viewModel.selectedDelivery?.phases, !phases.isEmpty {
                    AnalysisResultView(
                        viewModel: viewModel,
                        onDismiss: { viewModel.dismissDetail() }
                    )
                    .transition(.asymmetric(insertion: .move(edge: .bottom), removal: .opacity))
                    .zIndex(10)
                } else if let delivery = viewModel.selectedDelivery {
                    DeliveryDetailView(
                        delivery: delivery,
                        onDismiss: { viewModel.dismissDetail() },
                        onFavorite: { d in viewModel.toggleFavorite(d) }
                    )
                    .transition(.asymmetric(insertion: .move(edge: .bottom), removal: .opacity))
                    .zIndex(10)
                }
            }
        }
        .sheet(isPresented: $showingSettings) {
            SettingsView(config: $viewModel.configLevel, language: $viewModel.language)
        }
        .overlay {
            
            if viewModel.isSessionSummaryVisible {
                SessionSummaryView(deliveries: viewModel.sessionDeliveries) {
                    viewModel.startNewSession()
                }
                .transition(.move(edge: .bottom))
            }
        }
        .onChange(of: selectedItem) { oldValue, newItem in
            guard newItem != nil else { return }

            // PERF LOGGING: Track picker return
            let pickerReturnTime = CACurrentMediaTime()
            print("📱 [PERF] [T1] Picker RETURNED at \(Date())")
            print("   └─ Selected item: \(newItem != nil ? "YES" : "NO")")

            // 1. Immediate Feedback
            viewModel.isImporting = true
            viewModel.scoutingStatus = "Importing Media..."
            viewModel.prepareForUpload()

            // 2. Heavy Lifting
            Task {
                // Use MovieFile struct for safer, permission-aware file loading
                do {
                    // PERF LOGGING: Track loadTransferable start
                    let loadStartTime = CACurrentMediaTime()
                    print("⏳ [PERF] [T2] loadTransferable STARTED at \(Date())")

                    if let movie = try await newItem?.loadTransferable(type: MovieFile.self) {
                        // PERF LOGGING: Track loadTransferable completion
                        let loadEndTime = CACurrentMediaTime()
                        print("✅ [PERF] [T3] loadTransferable COMPLETED. Elapsed: \(String(format: "%.3f", loadEndTime - loadStartTime))s")
                        print("   └─ Total from picker: \(String(format: "%.3f", loadEndTime - pickerReturnTime))s")

                        await MainActor.run {
                            viewModel.processVideoSource(url: movie.url)
                            selectedItem = nil // Reset picker state to allow re-selection
                        }
                    }
                } catch {
                     print("Failed to load MovieFile: \(error)")
                     await MainActor.run {
                         viewModel.isImporting = false
                         viewModel.scoutingStatus = nil
                         selectedItem = nil // Reset picker state on error
                     }
                }
            }
        }
        .overlay {
            if viewModel.isImporting && viewModel.scoutingStatus == "Importing Media..." {
                 ZStack {
                     Color.black.opacity(0.6).ignoresSafeArea()
                     VStack(spacing: 16) {
                         ProgressView()
                             .tint(.white)
                             .scaleEffect(1.5)
                         Text("IMPORTING VIDEO...")
                             .font(.system(size: 12, weight: .bold))
                             .foregroundColor(.white)
                     }
                 }
            }
        }

        .alert(isPresented: $viewModel.showingError) {
            Alert(title: Text("System Message"), message: Text(viewModel.errorMessage ?? ""), dismissButton: .default(Text("OK")))
        }
        .onAppear {
            cameraManager.startSession()
        }
        .onDisappear {
            cameraManager.stopSession()
        }

}
}
