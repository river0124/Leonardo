import SwiftUI

struct MainView: View {
    enum Tab {
        case stocks, chart, portfolio, settings
    }

    @State private var selectedTab: Tab = .stocks
    @State private var selectedStock: StockItem? = nil

    var body: some View {
        NavigationSplitView {
            List(selection: $selectedTab) {
                Label("추천종목", systemImage: "list.bullet").tag(Tab.stocks)
                Label("차트", systemImage: "chart.line.uptrend.xyaxis").tag(Tab.chart)
                Label("포트폴리오", systemImage: "wallet.pass").tag(Tab.portfolio)
                Label("설정", systemImage: "gearshape").tag(Tab.settings)
            }
            .navigationTitle("Leonardo")
        } content: {
            switch selectedTab {
            case .stocks:
                StockListView(selectedStock: $selectedStock)
            case .chart:
                Text("Chart View")
            case .portfolio:
                Text("Portfolio View")
            case .settings:
                Text("Settings View")
            }
        } detail: {
            if let stock = selectedStock {
                ChartsView(stock: stock)
            } else {
                Text("세부 정보를 선택하세요")
                    .foregroundStyle(.secondary)
            }
        }
    }
}
