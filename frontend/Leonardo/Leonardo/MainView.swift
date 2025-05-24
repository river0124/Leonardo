import SwiftUI

struct MainView: View {
    enum Tab {
        case stocks, watchlist, chart, portfolio, settings, portfolioDummy
    }

    @State private var selectedTab: Tab = .portfolioDummy
    @State private var selectedStock: StockItem? = nil
    @State private var selectedWatchStock: WatchStockItem? = nil

    var body: some View {
        NavigationSplitView {
            List(selection: $selectedTab) {
                Label("보유 종목", systemImage: "tray.full").tag(Tab.portfolioDummy)
                Label("추천종목", systemImage: "list.bullet").tag(Tab.stocks)
                Label("관심종목", systemImage: "star").tag(Tab.watchlist)
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
            case .portfolioDummy:
                HoldingView()
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
            case .portfolio:
                Text("보유 종목 View")
            case .portfolioDummy:
                HoldingView()
            default:
                Text("세부 정보를 선택하세요")
                    .foregroundStyle(.secondary)
            }
        }
    }
}
