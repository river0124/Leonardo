import SwiftUI

struct MainView: View {
    enum Tab {
        case stocks, watchlist, chart, portfolio, settings
    }

    @State private var selectedTab: Tab = .stocks
    @State private var selectedStock: StockItem? = nil
    @State private var selectedWatchStock: WatchStockItem? = nil

    var body: some View {
        NavigationSplitView {
            List(selection: $selectedTab) {
                Label("추천종목", systemImage: "list.bullet").tag(Tab.stocks)
                Label("주시종목", systemImage: "star").tag(Tab.watchlist)
                Label("차트", systemImage: "chart.line.uptrend.xyaxis").tag(Tab.chart)
                Label("포트폴리오", systemImage: "wallet.pass").tag(Tab.portfolio)
                Label("설정", systemImage: "gearshape").tag(Tab.settings)
            }
            .navigationTitle("Leonardo")
        } content: {
            switch selectedTab {
            case .stocks:
                StockListView(selectedStock: $selectedStock)
            case .watchlist:
                WatchListView(selectedStock: $selectedWatchStock)
            case .chart:
                Text("Chart View")
            case .portfolio:
                Text("Portfolio View")
            case .settings:
                Text("Settings View")
            }
        } detail: {
            switch selectedTab {
            case .stocks:
                if let stock = selectedStock {
                    ChartsView(stock: stock)
                } else {
                    Text("세부 정보를 선택하세요")
                        .foregroundStyle(.secondary)
                }
            case .watchlist:
                if let stock = selectedWatchStock {
                    ChartsView(stock: StockItem(
                        Code: stock.Code,
                        Name: stock.Name,
                        CurrentPrice: 0,
                        High52Week: 0,
                        Ratio: 0
                    ))
                } else {
                    Text("세부 정보를 선택하세요")
                        .foregroundStyle(.secondary)
                }
            default:
                Text("세부 정보를 선택하세요")
                    .foregroundStyle(.secondary)
            }
        }
    }
}
