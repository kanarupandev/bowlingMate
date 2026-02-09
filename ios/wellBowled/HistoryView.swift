import SwiftUI

struct HistoryView: View {
    let deliveries: [Delivery]
    let onSelect: (Delivery) -> Void
    let onAnalyze: ((Delivery) -> Void)?
    let onDelete: (Delivery) -> Void
    let onFavorite: (Delivery) -> Void
    let isAnyAnalysisRunning: Bool
    
    var body: some View {
        ZStack {
            DesignSystem.Colors.background.ignoresSafeArea()
            
            VStack(alignment: .leading, spacing: DesignSystem.Layout.standardPadding) {
                if deliveries.isEmpty {
                    // Empty state
                    VStack(spacing: DesignSystem.Layout.standardPadding) {
                        Image(systemName: "archivebox")
                            .font(.system(size: 40))
                            .foregroundColor(.white.opacity(0.2))
                        Text("No clips yet")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white.opacity(0.4))
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    let sortedDeliveries = deliveries.sorted { $0.sequence > $1.sequence }
                    
                    if UIDevice.current.userInterfaceIdiom == .pad {
                        // iPad: Grid Layout
                        ScrollView {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 280), spacing: DesignSystem.Layout.standardPadding)], spacing: DesignSystem.Layout.standardPadding) {
                                ForEach(sortedDeliveries) { delivery in
                                    UploadDeliveryCard(
                                        delivery: delivery,
                                        isActive: true, 
                                        onAnalyze: { onAnalyze?(delivery) },
                                        onDelete: { onDelete(delivery) },
                                        onFavorite: { onFavorite(delivery) },
                                        onSelect: { onSelect(delivery) },
                                        isAnyAnalysisRunning: isAnyAnalysisRunning
                                    )
                                    .frame(height: 380)
                                }
                            }
                            .padding(DesignSystem.Layout.detailPadding)
                        }
                    } else {
                        // iPhone: Vertical Scroll List
                        ScrollView {
                            VStack(spacing: DesignSystem.Layout.detailPadding) {
                                ForEach(sortedDeliveries) { delivery in
                                    UploadDeliveryCard(
                                        delivery: delivery,
                                        isActive: true, 
                                        onAnalyze: { onAnalyze?(delivery) },
                                        onDelete: { onDelete(delivery) },
                                        onFavorite: { onFavorite(delivery) },
                                        onSelect: { onSelect(delivery) },
                                        isAnyAnalysisRunning: isAnyAnalysisRunning
                                    )
                                    .frame(height: 400) 
                                }
                            }
                            .padding(DesignSystem.Layout.standardPadding)
                        }
                    }
                }
            }
        }
    }
}
