//
//  AppModel.swift
//  Leonardo
//
//  Created by Hyung Seok Lee on 5/23/25.
//
import Foundation

class AppModel: ObservableObject {
    @Published var stockCache: [String: WatchStockItem] = [:]
    @Published var watchlistCodes: [String] = []
    @Published var showWatchlistWarning: Bool = false

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
}
