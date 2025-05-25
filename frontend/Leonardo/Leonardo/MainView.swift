import SwiftUI

struct MainView: View {
    enum Tab {
        case stocks, watchlist, chart, portfolio, settings, portfolioDummy
    }

    enum AssetDetailTab: Hashable {
        case summary
        case holdings
        case profits
        case orders
        case trends
    }

    @State private var selectedTab: Tab = .portfolioDummy
    @State private var selectedStock: StockItem? = nil
    @State private var selectedWatchStock: WatchStockItem? = nil
    @State private var selectedAssetTab: AssetDetailTab? = .summary
    @State private var selectedSettingsTab: String? = nil

    var body: some View {
        NavigationSplitView {
            List(selection: $selectedTab) {
                Label("자산현황", systemImage: "wonsign.bank.building").tag(Tab.portfolioDummy)
                Label("추천종목", systemImage: "hand.thumbsup").tag(Tab.stocks)
                Label("관심종목", systemImage: "star").tag(Tab.watchlist)
                Label("종목검색", systemImage: "magnifyingglass").tag(Tab.chart)
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
                SearchView(selectedStock: $selectedStock)
            case .portfolio:
                Text("Portfolio View")
            case .settings:
                List(selection: $selectedSettingsTab) {
                    NavigationLink("일반설정", value: "B")
                    NavigationLink("베팅관련설정", value: "A")
                }
                .navigationTitle("설정")
            case .portfolioDummy:
                List(selection: $selectedAssetTab) {
                    NavigationLink("총자산", value: AssetDetailTab.summary)
                    NavigationLink("보유종목", value: AssetDetailTab.holdings)
                    NavigationLink("매매손익", value: AssetDetailTab.profits)
                    NavigationLink("체결", value: AssetDetailTab.orders)
                    NavigationLink("손익추이", value: AssetDetailTab.trends)
                }
                .navigationTitle("자산현황")
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
            case .chart:
                if let stock = selectedStock {
                    ChartsView(stock: stock)
                } else {
                    Text("세부 정보를 선택하세요")
                        .foregroundStyle(.secondary)
                }
            case .portfolio:
                Text("보유 종목 View")
            case .portfolioDummy:
                switch selectedAssetTab {
                case .summary:
                    AssetSummaryView()
                case .holdings:
                    HoldingView()
                case .profits:
                    Text("매매손익 View (더미)")
                case .orders:
                    Text("체결 View (더미)")
                case .trends:
                    Text("손익추이 View (더미)")
                case .none:
                    Text("세부 정보를 선택하세요")
                        .foregroundStyle(.secondary)
                }
            case .settings:
                switch selectedSettingsTab {
                case "A":
                    BettingSettingsView()
                case "B":
                    GeneralSettingView()
                default:
                    Text("설정 내용을 선택하세요")
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}
