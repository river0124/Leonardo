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

class AppModel: ObservableObject {
    @Published var stockList: [StockInfo] = []
    @Published var stockCache: [String: WatchStockItem] = [:]
    @Published var watchlistCodes: [String] = []
    @Published var showWatchlistWarning: Bool = false

    @Published var atrPeriod: Int = 20
    @Published var maxLossRatio: Double = -0.01
    @Published var totalAsset: Int = 0

    init() {
        loadStockList()
    }

    struct Settings: Codable {
        let atr_period: Int
        let max_loss_ratio: Double
    }

    func loadSettings() {
        guard let url = URL(string: "http://127.0.0.1:5051/settings") else { return }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let settings = try JSONDecoder().decode(Settings.self, from: data)
                    DispatchQueue.main.async {
                        self.atrPeriod = settings.atr_period
                        self.maxLossRatio = settings.max_loss_ratio
                    }
                } catch {
                    print("❌ 설정 디코딩 실패:", error)
                }
            }
        }.resume()
    }

    func fetchWatchlist() {
        guard let url = URL(string: "http://127.0.0.1:5051/watchlist") else { return }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let result = try JSONDecoder().decode([String: [String]].self, from: data)
                    DispatchQueue.main.async {
                        self.watchlistCodes = result["watchlist"] ?? []
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

    private func loadStockList() {
        guard let url = URL(string: "http://127.0.0.1:5051/stock/list") else { return }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let data = data {
                do {
                    let list = try JSONDecoder().decode([StockInfo].self, from: data)
                    DispatchQueue.main.async {
                        self.stockList = list
                    }
                } catch {
                    print("❌ Failed to decode stock_list:", error)
                }
            } else if let error = error {
                print("❌ Failed to fetch stock_list:", error.localizedDescription)
            }
        }.resume()
    }
}
