import SwiftUI

struct FavoritesView: View {
    @ObservedObject var viewModel: BowlViewModel
    
    var body: some View {
        ZStack {
            DesignSystem.Colors.background.ignoresSafeArea()
            
            VStack(alignment: .leading, spacing: DesignSystem.Layout.standardPadding) {
                if viewModel.favoriteDeliveries.isEmpty {
                    // Empty state
                    VStack(spacing: DesignSystem.Layout.standardPadding) {
                        Image(systemName: "heart.slash")
                            .font(.system(size: 40))
                            .foregroundColor(.white.opacity(0.2))
                        Text("No favorites yet")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(.white.opacity(0.4))
                        Text("Heart your best clips to save them here")
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.25))
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ScrollView {
                        VStack(spacing: DesignSystem.Layout.detailPadding) {
                            ForEach(viewModel.favoriteDeliveries.sorted { $0.sequence > $1.sequence }) { delivery in
                                UploadDeliveryCard(
                                    delivery: delivery,
                                    isActive: true,
                                    onAnalyze: { viewModel.requestAnalysis(for: delivery) },
                                    onDelete: { viewModel.deleteDelivery(delivery) },
                                    onFavorite: { viewModel.toggleFavorite(delivery) },
                                    onSelect: { viewModel.selectDelivery(delivery) },
                                    isAnyAnalysisRunning: viewModel.isAnyAnalysisRunning
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
