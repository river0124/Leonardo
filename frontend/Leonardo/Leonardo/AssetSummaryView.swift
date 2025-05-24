import SwiftUI

struct AssetSummaryView: View {
    @State private var summary: [String: String] = [:]

    let dynamicLabels: [String] = [
        "총평가금액",
        "금일매수수량",
        "금일매도수량",
        "금일제비용금액",
        "금일실현손익",
        "예수금총금액",
        "익일정산금액",
        "가수도정산금액"
    ]

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 12) {
                Text("총자산 요약")
                    .font(.title2)
                    .bold()
                Group {
                    HStack {
                        Text("실평가손익합").frame(width: 120, alignment: .leading).foregroundColor(.secondary)
                        Text("-").frame(width: 100, alignment: .trailing)
                    }
                    HStack {
                        Text("실현실수익금").frame(width: 120, alignment: .leading).foregroundColor(.secondary)
                        Text("-").frame(width: 100, alignment: .trailing)
                    }
                    HStack {
                        Text("자산증감금액").frame(width: 120, alignment: .leading).foregroundColor(.secondary)
                        Text("-").frame(width: 100, alignment: .trailing)
                    }
                }
                ForEach(dynamicLabels, id: \.self) { label in
                    HStack {
                        Text(displayName(for: label))
                            .frame(width: 120, alignment: .leading)
                            .foregroundColor(.secondary)
                        Text(formatNumber(summary[label]))
                            .frame(width: 100, alignment: .trailing)
                    }
                }
                Spacer()
            }
            .padding()
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .onAppear {
            fetchSummary()
        }
    }

    func formatNumber(_ number: String?) -> String {
        guard let value = Double(number ?? "") else { return number ?? "-" }
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 0
        formatter.minimumFractionDigits = 0
        return formatter.string(from: NSNumber(value: value)) ?? "\(value)"
    }

    func displayName(for key: String) -> String {
        switch key {
        case "예수금총금액": return "예수금"
        case "익일정산금액": return "D+1정산"
        case "가수도정산금액": return "D+2정산"
        case "총평가금액": return "총평가금액"
        case "금일매수수량": return "금일매수"
        case "금일매도수량": return "금일매도"
        case "금일제비용금액": return "금일제비용"
        case "금일실현손익": return "금일실현손익"
        default: return key
        }
    }

    func fetchSummary() {
        guard let url = URL(string: "http://127.0.0.1:5051/total_asset/summary") else { return }

        URLSession.shared.dataTask(with: url) { data, _, _ in
            guard let data = data else { return }

            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: String] {
                    DispatchQueue.main.async {
                        summary = json
                    }
                }
            } catch {
                print("❌ AssetSummaryView fetch 실패: \(error)")
            }
        }.resume()
    }
}
