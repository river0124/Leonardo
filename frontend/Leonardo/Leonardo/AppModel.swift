//
//  AppModel.swift
//  Leonardo
//
//  Created by Hyung Seok Lee on 5/23/25.
//
import Foundation

struct StockInfo: Identifiable, Codable {
    var id: String { code }
    let name: String
    let code: String
}

struct Settings: Codable {
    let atr_period: Int
    let max_loss_ratio: Double
    let is_paper_trading: Bool
}


class AppModel: ObservableObject {
    static let shared = AppModel()
    @Published var stockList: [StockInfo] = []
    @Published var stockCache: [String: WatchStockItem] = [:]
    @Published var watchlistCodes: [String] = []
    @Published var showWatchlistWarning: Bool = false

    @Published var atrPeriod: Int = 20
    @Published var maxLossRatio: Double = -0.01
    @Published var totalAsset: Int = 0
    @Published var isMarketOrder: Bool = true
    @Published var isPaperTrading: Bool = true {
        didSet {
            updateTradingModeOnServer()
            loadTotalAssetFromSummary()
        }
    }
    @Published var isSettingsLoaded: Bool = false

    init() {
        loadSettings {
            self.loadTotalAssetFromSummary()
            self.loadStockList()
            self.loadWatchlist()
        }
    }


    func applyTradingModeAndReload() {
        guard let url = URL(string: "http://127.0.0.1:5051/settings") else { return }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let settings = try JSONDecoder().decode(Settings.self, from: data)
                    DispatchQueue.main.async {
                        self.isPaperTrading = settings.is_paper_trading
                        print("📌 서버에서 받은 isPaperTrading:", self.isPaperTrading)
                        self.reloadAllData()
                    }
                } catch {
                    print("❌ applyTradingModeAndReload 디코딩 실패:", error)
                }
            } else if let error = error {
                print("❌ applyTradingModeAndReload 요청 실패:", error.localizedDescription)
            }
        }.resume()
    }

    func loadSettings(completion: (() -> Void)? = nil) {
        guard let url = URL(string: "http://127.0.0.1:5051/settings") else {
            completion?()
            return
        }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let settings = try JSONDecoder().decode(Settings.self, from: data)
                    DispatchQueue.main.async {
                        self.atrPeriod = settings.atr_period
                        self.maxLossRatio = settings.max_loss_ratio
                        self.objectWillChange.send()
                        self.isPaperTrading = settings.is_paper_trading
                        self.isSettingsLoaded = true
                        print("✅ Settings loaded.")
                        completion?()
                    }
                } catch {
                    print("❌ 설정 디코딩 실패:", error)
                    completion?()
                }
            } else {
                if let error = error {
                    print("❌ loadSettings 요청 실패:", error.localizedDescription)
                }
                completion?()
            }
        }.resume()
    }

    func fetchWatchlist() {
        guard let url = URL(string: "http://127.0.0.1:5051/watchlist") else { return }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let decoded = try JSONDecoder().decode([String: [String]].self, from: data)
                    if let codes = decoded["watchlist"] {
                        DispatchQueue.main.async {
                            self.watchlistCodes = codes
                            for code in codes {
                                self.fetchStockInfo(code: code)
                            }
                            print("✅ Watchlist loaded.")
                        }
                    }
                } catch {
                    print("❌ 디코딩 실패:", error)
                }
            }
        }.resume()
    }

    @MainActor
    func addToWatchlist(code: String) async {
        guard let url = URL(string: "http://127.0.0.1:5051/watchlist") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["code": code]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                if !watchlistCodes.contains(code) {
                    watchlistCodes.append(code)
                }
            }
        } catch {
            print("❌ addToWatchlist 에러: \(error)")
        }
    }

    @MainActor
    func removeFromWatchlist(code: String) async {
        guard let url = URL(string: "http://127.0.0.1:5051/watchlist") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body = ["code": code]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                watchlistCodes.removeAll { $0 == code }
            }
        } catch {
            print("❌ removeFromWatchlist 에러: \(error)")
        }
    }

    func loadStockList() {
        guard let url = URL(string: "http://127.0.0.1:5051/stock/list") else { return }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let list = try JSONDecoder().decode([StockInfo].self, from: data)
                    DispatchQueue.main.async {
                        self.stockList = list
                        print("✅ Stock list loaded.")
                    }
                } catch {
                    print("❌ Failed to decode stock_list:", error)
                }
            } else if let error = error {
                print("❌ Failed to fetch stock_list:", error.localizedDescription)
            }
        }.resume()
    }
    
    func reloadAllData() {
        print("🔄 Reloading all data...")
        print("📌 현재 isPaperTrading 상태:", self.isPaperTrading)

        print("📥 Loading settings...")
        loadSettings()

        print("📥 Loading total asset summary...")
        loadTotalAssetFromSummary()

        print("📥 Loading watchlist...")
        loadWatchlist()

        print("📥 Loading stock list...")
        loadStockList()
    }

    func loadTotalAssetFromSummary() {
        guard let url = URL(string: "http://127.0.0.1:5051/total_asset/summary") else { return }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let summary = try JSONDecoder().decode([String: String].self, from: data)
                    if let amountString = summary["총평가금액"],
                       let amount = Int(amountString.replacingOccurrences(of: ",", with: "")) {
                        DispatchQueue.main.async {
                            self.totalAsset = amount
                            print("✅ Total asset summary loaded.")
                            print("📊 총자산 업데이트됨: \(self.totalAsset)원 (isPaperTrading: \(self.isPaperTrading))")
                        }
                    }
                } catch {
                    print("❌ 총평가금액 디코딩 실패:", error)
                }
            } else if let error = error {
                print("❌ 총평가금액 요청 실패:", error.localizedDescription)
            }
        }.resume()
    }
    func loadWatchlist() {
        fetchWatchlist()
    }
    
    func fetchStockInfo(code: String) {
        guard let url = URL(string: "http://127.0.0.1:5051/stockname?code=\(code)") else { return }

        URLSession.shared.dataTask(with: url) { data, _, _ in
            if let data = data {
                do {
                    if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let name = json["name"] as? String {
                        let item = WatchStockItem(id: code, Code: code, Name: name)
                        DispatchQueue.main.async {
                            self.stockCache[code] = item
                        }
                    }
                } catch {
                    print("❌ 종목명 디코딩 실패:", error)
                }
            }
        }.resume()
    }
    func updateTradingModeOnServer() {
        guard let url = URL(string: "http://127.0.0.1:5051/settings") else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = ["is_paper_trading": isPaperTrading]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        URLSession.shared.dataTask(with: request).resume()
    }
}
