import SwiftUI
import Charts

struct Candle: Identifiable, Codable {
    let id = UUID()
    let date: String
    let open: Double
    let high: Double
    let low: Double
    let close: Double

    enum CodingKeys: String, CodingKey {
        case date, open, high, low, close
    }
}

struct CandleResponse: Codable {
    let candles: [Candle]
}

struct ChartsView: View {
    let stock: StockItem
    @State private var candles: [Candle] = []
    @State private var show52Weeks = false

    private var yRange: ClosedRange<Double>? {
        guard let minLow = candles.map({ $0.low }).min(),
              let maxHigh = candles.map({ $0.high }).max() else {
            return nil
        }
        let padding = (maxHigh - minLow) * 0.15
        return (minLow - padding)...(maxHigh + padding)
    }

    var body: some View {
        VStack(alignment: .leading) {
            Text("\(stock.Name)(\(stock.Code))")
                .font(.headline)
                .padding()

            if candles.isEmpty {
                Text("로딩 중...").onAppear {
                    fetchCandleData(for: stock.Code)
                }
            } else {
                HStack {
                    Button(action: {
                        show52Weeks = false
                        fetchCandleData(for: stock.Code)
                    }) {
                        Text("26주")
                            .padding(8)
                            .background(show52Weeks ? Color.gray.opacity(0.2) : Color.blue.opacity(0.2))
                            .cornerRadius(8)
                    }

                    Button(action: {
                        show52Weeks = true
                        fetchCandleData(for: stock.Code)
                    }) {
                        Text("52주")
                            .padding(8)
                            .background(show52Weeks ? Color.blue.opacity(0.2) : Color.gray.opacity(0.2))
                            .cornerRadius(8)
                    }
                }
                .padding(.horizontal)

                Chart(candles) { candle in
                    RuleMark(
                        x: .value("날짜", candle.date),
                        yStart: .value("저가", candle.low),
                        yEnd: .value("고가", candle.high)
                    )
                    .lineStyle(StrokeStyle(lineWidth: 1))
                    .foregroundStyle(.gray)

                    RectangleMark(
                        x: .value("날짜", candle.date),
                        yStart: .value("시가", candle.open),
                        yEnd: .value("종가", candle.close)
                    )
                    .foregroundStyle(candle.close >= candle.open ? .red : .blue)
                    .cornerRadius(1)
                }
                .chartXAxis {
                    AxisMarks(values: .stride(by: 15)) { value in
                        AxisGridLine()
                        AxisTick()
                        AxisValueLabel {
                            if let dateString = value.as(String.self) {
                                Text(dateString.prefix(10))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .rotationEffect(.degrees(45))
                            }
                        }
                    }
                }
                .chartYScale(domain: yRange ?? 0...1)
                .frame(height: 600)
                .padding()
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .onChange(of: stock.Code) { newCode in
            fetchCandleData(for: newCode)
        }
    }

    func fetchCandleData(for code: String) {
        guard let url = URL(string: "http://192.168.50.221:5051/candle?code=\(code)") else {
            print("❌ URL 생성 실패")
            return
        }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let error = error {
                print("❌ 요청 에러:", error.localizedDescription)
                return
            }

            guard let data = data else {
                print("❌ 데이터 없음")
                return
            }

            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let candleArray = json["candles"] as? [[String: Any]] {
                    
                    let jsonData = try JSONSerialization.data(withJSONObject: candleArray)
                    let decodedCandles = try JSONDecoder().decode([Candle].self, from: jsonData)
                    let filtered = decodedCandles.filter {
                        $0.date.contains("-") && $0.open > 0 && $0.high > 0 && $0.low > 0 && $0.close > 0
                    }
                    DispatchQueue.main.async {
                        self.candles = show52Weeks ? filtered : Array(filtered.suffix(130))
                    }
                } else {
                    print("❌ JSON 구조 오류: 'candles' 키가 없음")
                    DispatchQueue.main.async {
                        self.candles = []
                    }
                }
            } catch {
                print("❌ JSON 파싱 실패:", error)
            }
        }.resume()
    }
}
