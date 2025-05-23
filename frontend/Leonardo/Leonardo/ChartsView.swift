import SwiftUI
import Charts

struct Candle: Identifiable, Codable {
    let id = UUID()
    let date: String
    let open: Double
    let high: Double
    let low: Double
    let close: Double
    let volume: Double

    enum CodingKeys: String, CodingKey {
        case date, open, high, low, close, volume
    }
}

struct CandleResponse: Codable {
    let candles: [Candle]
}

struct ChartsView: View {
    @EnvironmentObject var appModel: AppModel

    let stock: StockItem
    @State private var candles: [Candle] = []
    @State private var show52Weeks = false
    @State private var priceInfo: [String: String] = [:]
    private var isStarred: Bool {
        appModel.watchlistCodes.contains(stock.Code)
    }

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
            HStack(alignment: .center) {
                Text("\(stock.Name)(\(stock.Code))")
                    .font(.headline)

                Text("26주")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Toggle(isOn: $show52Weeks) {
                    EmptyView()
                }
                .labelsHidden()
                .toggleStyle(SwitchToggleStyle(tint: .blue))

                Text("52주")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Spacer()

                Button(action: {
                    Task {
                        if isStarred {
                            await appModel.removeFromWatchlist(code: stock.Code)
                        } else {
                            await appModel.addToWatchlist(code: stock.Code)
                        }
                    }
                }) {
                    ZStack {
                        if isStarred {
                            Image(systemName: "star.fill")
                                .foregroundColor(.yellow)
                            Image(systemName: "star")
                                .foregroundColor(.gray)
                        } else {
                            Image(systemName: "star")
                                .foregroundColor(.gray)
                        }
                    }
                    .font(.system(size: 16))
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal)
            
            HStack{
                Spacer()
                if !priceInfo.isEmpty {
                    VStack(alignment: .trailing, spacing: 4) {
                        Text("현재가: \(priceInfo["stck_prpr"] ?? "-")")
                        Text("시가: \(priceInfo["stck_oprc"] ?? "-")")
                        Text("고가: \(priceInfo["stck_hgpr"] ?? "-")")
                        Text("저가: \(priceInfo["stck_lwpr"] ?? "-")")
                        Text("전일대비: \(priceInfo["prdy_vrss"] ?? "-")")
                        Text("등락률: \(priceInfo["prdy_ctrt"] ?? "-")%")
                        Text("누적거래량: \(priceInfo["acml_vol"] ?? "-")")
                    }
                    .font(.caption)
                    .padding(.horizontal)
                    .foregroundColor(.secondary)
                }
            }

            if candles.isEmpty {
                Text("로딩 중...").onAppear {
                    fetchCandleData(for: stock.Code)
                    fetchPriceData(for: stock.Code)
                }
            } else {
                // onChange for show52Weeks: fetch data when toggled
                EmptyView()
                    .onChange(of: show52Weeks) { _, _ in
                        fetchCandleData(for: stock.Code)
                    }

                VStack(spacing: 0) {
                    Chart {
                        ForEach(candles) { candle in
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
                            
                            let priceRange = (yRange?.upperBound ?? 1) - (yRange?.lowerBound ?? 0)
                            let volumeHeight = priceRange * 0.15
                            let maxVolume = candles.map(\.volume).max() ?? 1

                            BarMark(
                                x: .value("날짜", candle.date),
                                yStart: .value("거래량 시작", (yRange?.lowerBound ?? 0)),
                                yEnd: .value("거래량", (candle.volume / maxVolume) * volumeHeight + (yRange?.lowerBound ?? 0))
                            )
                            .foregroundStyle(.purple.opacity(0.3))
                        }

                        if let highest = candles.max(by: { $0.high < $1.high }) {
                            PointMark(
                                x: .value("날짜", highest.date),
                                y: .value("고가", highest.high)
                            )
                            .symbol {
                                Image(systemName: "xmark")
                                    .font(.system(size: 8))
                                    .foregroundColor(.gray)
                            }
                            .symbolSize(10)
                            .foregroundStyle(.red)
                            .annotation(position: .topLeading) {
                                Text("최고 \(Int(highest.high)), \(highest.date)")
                                    .font(.caption)
                                    .foregroundColor(.red)
                                    .offset(x: 40)
                            }
                        }

                        if let lowest = candles.min(by: { $0.low < $1.low }) {
                            PointMark(
                                x: .value("날짜", lowest.date),
                                y: .value("저가", lowest.low)
                            )
                            .symbol {
                                Image(systemName: "xmark")
                                    .font(.system(size: 8))
                                    .foregroundColor(.gray)
                            }
                            .symbolSize(10)
                            .foregroundStyle(.blue)
                            .annotation(position: .bottomTrailing) {
                                Text("최저 \(Int(lowest.low)), \(lowest.date)")
                                    .font(.caption)
                                    .foregroundColor(.blue)
                                    .padding(.leading, -35)
                            }
                        }
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
                    .frame(height: 360)
                    .padding(.horizontal)
                }
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .onChange(of: stock.Code, initial: false) { oldCode, newCode in
            fetchCandleData(for: newCode)
            fetchPriceData(for: newCode)
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
                    
                    let filteredCandles: [Candle] = candleArray.compactMap { dict in
                        guard let date = dict["date"] as? String,
                              let open = dict["open"] as? Double,
                              let high = dict["high"] as? Double,
                              let low = dict["low"] as? Double,
                              let close = dict["close"] as? Double,
                              let volume = dict["volume"] as? Double,
                              date.contains("-"),
                              open > 0, high > 0, low > 0, close > 0 else {
                            return nil
                        }
                        return Candle(date: date, open: open, high: high, low: low, close: close, volume: volume)
                    }
                    DispatchQueue.main.async {
                        self.candles = show52Weeks ? filteredCandles : Array(filteredCandles.suffix(130))
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
    
    func fetchPriceData(for code: String) {
        guard let url = URL(string: "http://127.0.0.1:5051/price?stock_no=\(code)") else {
            print("❌ 가격 데이터 URL 생성 실패")
            return
        }

        URLSession.shared.dataTask(with: url) { data, _, error in
            if let error = error {
                print("❌ 가격 데이터 요청 에러:", error.localizedDescription)
                return
            }

            guard let data = data else {
                print("❌ 가격 데이터 없음")
                return
            }

            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: String] {
                    DispatchQueue.main.async {
                        self.priceInfo = json
                    }
                } else {
                    print("❌ 가격 JSON 파싱 실패")
                }
            } catch {
                print("❌ 가격 JSON 에러:", error)
            }
        }.resume()
    }
}
