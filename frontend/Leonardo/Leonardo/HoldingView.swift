import SwiftUI

struct HoldingItem: Identifiable, Codable {
    var id: String { code }

    let code: String
    let name: String
    let quantity: Int
    let availableQuantity: Int?
    let avgPrice: Double?
    let currentPrice: Int?
    let evaluationAmount: Int?
    let profitLoss: Int?
    let profitLossRate: Double?
}

struct HoldingView: View {
    @State private var holdings: [HoldingItem] = []

    var body: some View {
        VStack(alignment: .leading) {
            Text("보유 종목 (\(holdings.count)개)")
                .font(.title2)
                .padding()

            List(holdings) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(item.name) (\(item.code))")
                        .font(.headline)
                    HStack {
                        Text("수량: \(item.quantity)")
                        Text("평균가: \(item.avgPrice ?? 0, specifier: "%.1f")")
                        Text("현재가: \(item.currentPrice ?? 0)")
                    }
                    .font(.subheadline)
                    HStack {
                        Text("평가손익: \(item.profitLoss ?? 0)")
                        Text("수익률: \(item.profitLossRate ?? 0, specifier: "%.2f")%")
                    }
                    .font(.footnote)
                    .foregroundColor((item.profitLoss ?? 0) >= 0 ? .red : .blue)
                }
                .padding(.vertical, 4)
            }
        }
        .onAppear(perform: fetchHoldings)
    }

    func fetchHoldings() {
        guard let url = URL(string: "http://127.0.0.1:5051/holdings") else { return }

        URLSession.shared.dataTask(with: url) { data, _, _ in
            guard let data = data else { return }

            do {
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                let result = try decoder.decode([HoldingItem].self, from: data)

                DispatchQueue.main.async {
                    holdings = result
                }
            } catch {
                print("❌ 보유 종목 디코딩 실패: \(error)")
            }
        }.resume()
    }
}
