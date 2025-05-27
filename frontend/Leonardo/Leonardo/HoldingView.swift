import SwiftUI

struct HoldingItem: Identifiable, Codable {
    var id: String { code }

    let code: String
    let name: String
    let quantity: String
    let availableQuantity: String?
    let avgPrice: String?
    let currentPrice: String?
    let evaluationAmount: String?
    let profitLoss: String?
    let profitLossRate: String?
    let pchsAmt: String?
    let evluErngRt: String?
    let flttRt: String?

    enum CodingKeys: String, CodingKey {
        case code = "pdno"
        case name = "prdt_name"
        case quantity = "hldg_qty"
        case availableQuantity = "ord_psbl_qty"
        case avgPrice = "pchs_avg_pric"
        case currentPrice = "prpr"
        case evaluationAmount = "evlu_amt"
        case profitLoss = "evlu_pfls_amt"
        case profitLossRate = "evlu_pfls_rt"
        case pchsAmt = "pchs_amt"
        case evluErngRt = "evlu_erng_rt"
        case flttRt = "fltt_rt"
    }
}

struct HoldingView: View {
    @State private var holdings: [HoldingItem] = []
    @State private var depositSummary: [String: String] = [:]
    @State private var timer: Timer?

    func formatNumber(_ number: String?) -> String {
        guard let value = Double(number ?? "") else { return number ?? "-" }
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        formatter.minimumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
    }
    
    func formatPercent(_ number: String?, decimals: Int = 2) -> String {
        guard let value = Double(number ?? "") else { return number ?? "-" }
        return String(format: "%.\(decimals)f%%", value)
    }

    var body: some View {
        VStack(alignment: .leading) {
            Text("보유 종목 (\(holdings.count)개)")
                .font(.title2)
                .padding()
            
            if !depositSummary.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("💰 예수금 요약")
                        .font(.headline)
                    Text("D 예수금: \(formatNumber(depositSummary["예수금총금액"]))")
                    Text("D+1 예수금: \(formatNumber(depositSummary["익일정산금액"]))")
                    Text("D+2 예수금: \(formatNumber(depositSummary["가수도정산금액"]))")
                }
                .padding()
            }

            List(holdings) { item in
                VStack(alignment: .leading, spacing: 4) {
                    Text("종목명: \(item.name) (\(item.code))")
                        .font(.headline)
                    HStack {
                        Text("보유수량: \(formatNumber(item.quantity))")
                        Text("주문가능수량: \(formatNumber(item.availableQuantity))")
                    }
                    HStack {
                        Text("매입평균가격: \(formatNumber(item.avgPrice))")
                        Text("매입금액: \(formatNumber(item.pchsAmt))")
                    }
                    HStack {
                        Text("현재가: \(formatNumber(item.currentPrice))")
                        Text("평가금액: \(formatNumber(item.evaluationAmount))")
                    }
                    HStack {
                        Text("평가손익금액: \(formatNumber(item.profitLoss))")
                        Text("평가손익률: \(formatPercent(item.profitLossRate))")
                    }
                    HStack {
                        Text("평가수익률(정밀): \(formatPercent(item.evluErngRt, decimals: 4))")
                        Text("전일대비등락률: \(formatPercent(item.flttRt))")
                    }
                    .foregroundColor((Int(item.profitLoss ?? "0") ?? 0) >= 0 ? .red : .blue)
                    .font(.footnote)
                }
                .padding(.vertical, 4)
            }
        }
        .onAppear {
            fetchHoldings()

            guard let marketStatusURL = URL(string: "http://127.0.0.1:5051/market/is_open") else { return }

            URLSession.shared.dataTask(with: marketStatusURL) { data, _, _ in
                guard let data = data else { return }
                do {
                    let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                    if let isMarketOpen = json?["is_market_open"] as? Bool, isMarketOpen {
                        DispatchQueue.main.async {
                            timer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
                                fetchHoldings()
                            }
                        }
                    } else {
                        print("📌 시장이 열리지 않았습니다. 리프레시 비활성화")
                    }
                } catch {
                    print("❌ 시장 개장 여부 확인 실패: \(error)")
                }
            }.resume()
        }
        .onDisappear {
            timer?.invalidate()
            timer = nil
        }
    }

    func fetchHoldings() {
        guard let url = URL(string: "http://127.0.0.1:5051/holdings/detail") else { return }

        URLSession.shared.dataTask(with: url) { data, _, _ in
            guard let data = data else { return }

            do {
                let decoder = JSONDecoder()
                let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                if let stockData = json?["stocks"] {
                    let stockJSON = try JSONSerialization.data(withJSONObject: stockData)
                    let result = try decoder.decode([HoldingItem].self, from: stockJSON)
                    DispatchQueue.main.async {
                        holdings = result
                    }
                }
                if let summary = json?["summary"] as? [String: Any] {
                    var result: [String: String] = [:]
                    for (key, value) in summary {
                        if let stringValue = value as? String {
                            result[key] = stringValue
                        } else {
                            result[key] = "\(value)"
                        }
                    }
                    DispatchQueue.main.async {
                        depositSummary = result
                    }
                }
            } catch {
                print("❌ 보유 종목 디코딩 실패: \(error)")
            }
        }.resume()
    }
}
