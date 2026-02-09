import SwiftUI

// MARK: - Page 1: Expert Analysis (All Phases)
struct ExpertAnalysisPage: View {
    let phases: [AnalysisPhase]
    var isOverlayReady: Bool = true // When false, shows "Annotating" indicator

    // Sort: GOOD phases first, then NEEDS WORK
    var sortedPhases: [AnalysisPhase] {
        phases.sorted { $0.isGood && !$1.isGood }
    }

    var body: some View {
        GeometryReader { geo in
            let contentWidth = geo.size.width * 0.80

            VStack(spacing: 0) {
                // Phase cards content — scrollable, NO top padding
                ScrollView(.vertical, showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(sortedPhases.prefix(6)) { phase in
                            ExpertPhaseCard(phase: phase)
                        }
                    }
                    .frame(width: contentWidth)
                    .padding(.bottom, 20)
                }
                .frame(maxWidth: .infinity)

                Spacer()

                // Annotating indicator (above swipe)
                if !isOverlayReady {
                    AnnotatingIndicator(text: "Annotating for interactive analysis")
                        .padding(.bottom, 8)
                }

                // PINNED: Swipe indicator at bottom
                SwipeIndicator()
                    .padding(.bottom, 20)
            }
            .background(Color.black)
        }
        .background(Color.black)
        .onAppear {
            print("📋 [ExpertPage] Appeared with \(phases.count) phases, overlayReady: \(isOverlayReady)")
        }
    }
}

// MARK: - Expert Phase Card (Detailed)
struct ExpertPhaseCard: View {
    let phase: AnalysisPhase

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Header row
            HStack {
                Circle()
                    .fill(phase.isGood ? DesignSystem.Colors.success : DesignSystem.Colors.error)
                    .frame(width: 10, height: 10)

                Text(phase.name.uppercased())
                    .font(.system(size: 13, weight: .black))
                    .foregroundColor(.white)

                Spacer()

                Text(phase.isGood ? "GOOD" : "NEEDS WORK")
                    .font(.system(size: 9, weight: .black))
                    .foregroundColor(phase.isGood ? DesignSystem.Colors.success : DesignSystem.Colors.error)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background((phase.isGood ? DesignSystem.Colors.success : DesignSystem.Colors.error).opacity(0.2))
                    .cornerRadius(6)
            }

            // Observation
            if !phase.observation.isEmpty {
                Text(phase.observation)
                    .font(.system(size: 14))
                    .foregroundColor(.white.opacity(0.85))
                    .fixedSize(horizontal: false, vertical: true)
            }

            // Tip
            if !phase.tip.isEmpty {
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: "lightbulb.fill")
                        .foregroundColor(DesignSystem.Colors.accent)
                        .font(.system(size: 12))
                    Text(phase.tip)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(DesignSystem.Colors.accent)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 4)
            }
        }
        .padding(16)
        .background(
            RoundedRectangle(cornerRadius: 14)
                .fill(Color.white.opacity(0.05))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke((phase.isGood ? DesignSystem.Colors.success : DesignSystem.Colors.error).opacity(0.3), lineWidth: 1)
        )
    }
}
