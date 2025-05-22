import SwiftUI

class StockViewModel: ObservableObject {
    @Published var stocks: [StockItem] = []

    init() {
        loadStockData()
    }

    func loadStockData() {
        guard let url = URL(string: "http://127.0.0.1:5051/high52") else {
            print("❌ URL 생성 실패")
            return
        }

        URLSession.shared.dataTask(with: url) { data, response, error in
            if let error = error {
                print("❌ 요청 실패: \(error.localizedDescription)")
                return
            }

            guard let data = data else {
                print("❌ 데이터 없음")
                return
            }

            if let raw = String(data: data, encoding: .utf8) {
                print("📦 응답 JSON 원본:\n\(raw)")
            }

            do {
                let decoded = try JSONDecoder().decode([StockItem].self, from: data)
                DispatchQueue.main.async {
                    self.stocks = decoded.filter { !$0.Name.contains("스팩") }
                }
            } catch {
                print("📛 JSON 디코딩 실패: \(error.localizedDescription)")
            }
        }.resume()
    }
}

struct StockItem: Identifiable, Decodable {
    var id: String { Code }
    let Code: String
    let Name: String
    let CurrentPrice: Int
    let High52Week: Int
    let Ratio: Double
}

struct StockListView: View {
    @StateObject private var viewModel = StockViewModel()
    @Binding var selectedStock: StockItem?

    var body: some View {
        VStack {
            List {
                ForEach(viewModel.stocks) { stock in
                    VStack(alignment: .leading, spacing: 6) {
                        Button(action: {
                            selectedStock = stock
                        }) {
                            Text("\(stock.Name)(\(stock.Code))")
                                .font(.headline)
                        }
                        Text("현재가: \(stock.CurrentPrice), 신고가: \(stock.High52Week), 비율: \(String(format: "%.1f", stock.Ratio))%")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
    }
}
