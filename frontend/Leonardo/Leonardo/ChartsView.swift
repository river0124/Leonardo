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
    @State private var bettingTextResult: String? = nil
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

            VStack {
                HStack(alignment: .top) {
                    if let text = bettingTextResult {
                        Text(text)
                            .font(.caption)
                            .padding()
                            .frame(minWidth: 180, maxWidth: 220, alignment: .leading)
                            .background(.ultraThinMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 6))
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }

                    Spacer()

                    if !priceInfo.isEmpty {
                        VStack(alignment: .trailing) {
                            Text("현재가: \(formattedNumber(priceInfo["stck_prpr"]))")
                            Text("시가: \(formattedNumber(priceInfo["stck_oprc"]))")
                            Text("고가: \(formattedNumber(priceInfo["stck_hgpr"]))")
                            Text("저가: \(formattedNumber(priceInfo["stck_lwpr"]))")
                            Text("전일대비: \(formattedNumber(priceInfo["prdy_vrss"]))")
                            Text("등락률: \(priceInfo["prdy_ctrt"] ?? "-")%")
                            Text("누적거래량: \(formattedNumber(priceInfo["acml_vol"]))")
                        }
                        .font(.caption)
                        .padding(.horizontal)
                        .foregroundColor(.secondary)
                    }
                }
                .padding(.horizontal)
                .padding(.top, 4)
                .frame(height: 130) // fixed height for betting area
            }

            if candles.isEmpty {
                Text("로딩 중...")
                    .onAppear {
                        fetchCandleData(for: stock.Code)
                        fetchPriceData(for: stock.Code)
                        calculateBettingSize()
                    }
            } else {
                // onChange for show52Weeks: fetch data when toggled
                EmptyView()
                    .onChange(of: show52Weeks) { _, _ in
                        fetchCandleData(for: stock.Code)
                    }

                ZStack(alignment: .topLeading) {
                    Chart {
                        // MA5 (5-day moving average) line
                        let ma5 = candles.enumerated().map { index, _ in
                            let start = max(0, index - 4)
                            let subset = candles[start...index]
                            let avg = subset.map(\.close).reduce(0, +) / Double(subset.count)
                            return (candles[index].date, avg)
                        }
                        ForEach(ma5, id: \.0) { (date, avg) in
                            LineMark(
                                x: .value("날짜", date),
                                y: .value("MA5", avg),
                                series: .value("Series", "MA5")
                            )
                            .foregroundStyle(.green)
                            .lineStyle(StrokeStyle(lineWidth: 1.5))
                            .opacity(0.6)
                        }

                        // MA20 (20-day moving average) line
                        let ma20 = candles.enumerated().map { index, _ in
                            let start = max(0, index - 19)
                            let subset = candles[start...index]
                            let avg = subset.map(\.close).reduce(0, +) / Double(subset.count)
                            return (candles[index].date, avg)
                        }
                        ForEach(ma20, id: \.0) { (date, avg) in
                            LineMark(
                                x: .value("날짜", date),
                                y: .value("MA20", avg),
                                series: .value("Series", "MA20")
                            )
                            .foregroundStyle(.red)
                            .lineStyle(StrokeStyle(lineWidth: 1.5))
                            .opacity(0.6)
                        }

                        let ma60 = candles.enumerated().map { index, _ in
                            let start = max(0, index - 59)
                            let subset = candles[start...index]
                            let avg = subset.map(\.close).reduce(0, +) / Double(subset.count)
                            return (candles[index].date, avg)
                        }
                        ForEach(ma60, id: \.0) { (date, avg) in
                            LineMark(
                                x: .value("날짜", date),
                                y: .value("MA60", avg),
                                series: .value("Series", "MA60")
                            )
                            .foregroundStyle(.orange)
                            .lineStyle(StrokeStyle(lineWidth: 1.5))
                            .opacity(0.6)
                        }

                        let ma120 = candles.enumerated().map { index, _ in
                            let start = max(0, index - 119)
                            let subset = candles[start...index]
                            let avg = subset.map(\.close).reduce(0, +) / Double(subset.count)
                            return (candles[index].date, avg)
                        }
                        ForEach(ma120, id: \.0) { (date, avg) in
                            LineMark(
                                x: .value("날짜", date),
                                y: .value("MA120", avg),
                                series: .value("Series", "MA120")
                            )
                            .foregroundStyle(.purple)
                            .lineStyle(StrokeStyle(lineWidth: 1.5))
                            .opacity(0.6)
                        }

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
                            .annotation(position: .top) {
                                VStack(spacing: 2) {
                                    Text("최고 \(formattedNumber("\(Int(highest.high))"))")
                                    Text("\(highest.date)")
                                        .font(.system(size: 9))
                                }
                                .font(.caption)
                                .foregroundColor(.red)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: .infinity)
                                .zIndex(1)
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
                                VStack(spacing: 2) {
                                    Text("최저 \(formattedNumber("\(Int(lowest.low))"))")
                                    Text("\(lowest.date)")
                                        .font(.system(size: 9))
                                }
                                .font(.caption)
                                .foregroundColor(.blue)
                                .multilineTextAlignment(.center)
                                .frame(maxWidth: .infinity, alignment: .center)
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
                                        .multilineTextAlignment(.center)
                                        .frame(maxWidth: .infinity, alignment: .center)
                                }
                            }
                        }
                    }
                    .chartYScale(domain: yRange ?? 0...1)
                    .frame(height: 360)
                    .padding(.horizontal)

                    // 평균선 안내 레이블 (Chart 위에 표시)
                    HStack(spacing: 12) {
                        Text("5").foregroundColor(.green).opacity(0.6)
                        Text("20").foregroundColor(.red).opacity(0.6)
                        Text("60").foregroundColor(.orange).opacity(0.6)
                        Text("120").foregroundColor(.purple).opacity(0.6)
                    }
                    .font(.caption2)
                    .padding(6)
                    .background(.ultraThinMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 6))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.top, 12)
                }
            }
            // (bettingTextResult block moved above)
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .onChange(of: stock.Code, initial: false) { oldCode, newCode in
            bettingTextResult = nil
            fetchCandleData(for: newCode)
            fetchPriceData(for: newCode)
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                calculateBettingSize()
            }
        }
    }

    func fetchCandleData(for code: String) {
        guard let url = URL(string: "http://127.0.0.1:5051/candle?code=\(code)") else {
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
    func formattedNumber(_ value: String?) -> String {
        guard let value = value, let number = Int(value) else { return value ?? "-" }
        return NumberFormatter.localizedString(from: NSNumber(value: number), number: .decimal)
    }

    private func calculateBettingSize() {
        let capital = 50000000.0
        let riskRatio = abs(appModel.maxLossRatio)
        let atrPeriod = appModel.atrPeriod
        let atr = 1000.0 // 예시 ATR 값
        let entryPriceStr = priceInfo["stck_prpr"]?.replacingOccurrences(of: ",", with: "") ?? "13000"
        let entryPrice = Double(entryPriceStr) ?? 13000
        let stopLoss = entryPrice - (2 * atr)
        let quantity = Int(floor((capital * riskRatio) / (atr * 2)))
        let totalInvestment = Double(quantity) * entryPrice
        let investmentRatio = capital > 0 ? totalInvestment / capital : 0

        bettingTextResult = """
        총자산: \(formattedNumber("\(Int(capital))"))
        ATR 기간: \(atrPeriod)일
        손실허용비율: \(-(riskRatio * 100))%
        ATR 값: \(formattedNumber("\(Int(atr))"))
        매수량: \(quantity)주
        목표매수가: \(formattedNumber("\(Int(entryPrice))"))
        손절가: \(formattedNumber("\(Int(stopLoss))"))
        투입자금: \(formattedNumber("\(Int(totalInvestment))"))원
        투입비중: \((investmentRatio * 100).formatted(.number.precision(.fractionLength(1))))%
        """
    }
}
