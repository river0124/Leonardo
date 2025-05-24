//
//  BettingSettingsView .swift
//  Leonardo
//
//  Created by Hyung Seok Lee on 5/24/25.
//

import SwiftUI

struct BettingSettingsView: View {
    @EnvironmentObject var appModel: AppModel

    @State private var draftAtrPeriod: Int = 20
    @State private var draftMaxLossRatio: Double = -0.01

    let lossOptions: [Double] = [-0.01, -0.015, -0.02]

    var isModified: Bool {
        draftAtrPeriod != appModel.atrPeriod || draftMaxLossRatio != appModel.maxLossRatio
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("베팅관련설정")
                .font(.title)
                .bold()
                .padding(.bottom, 10)

            HStack {
                Text("ATR 기간 설정:")
                    .frame(width: 200, alignment: .leading)
                Stepper(value: $draftAtrPeriod, in: 1...60) {
                    Text("\(draftAtrPeriod)일")
                }
            }

            HStack {
                Text("총자산 대비 손실 허용 비율:")
                    .frame(width: 200, alignment: .leading)
                Menu {
                    ForEach(lossOptions, id: \.self) { value in
                        Button(action: {
                            draftMaxLossRatio = value
                        }) {
                            Text(String(format: "%.1f%%", value * 100))
                        }
                    }
                } label: {
                    Text(String(format: "%.1f%%", draftMaxLossRatio * 100))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(Color.gray.opacity(0.2))
                        .cornerRadius(5)
                        .fixedSize()
                }
            }

            HStack {
                Button("저장") {
                    saveSettings()
                }
                .disabled(!isModified)
                .tint(isModified ? .blue : .gray)
                .padding(.top, 10)
            }

            Spacer()
        }
        .padding()
        .onAppear {
            draftAtrPeriod = appModel.atrPeriod
            draftMaxLossRatio = appModel.maxLossRatio
        }
    }

    func saveSettings() {
        guard let url = URL(string: "http://127.0.0.1:5051/settings") else { return }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let settings: [String: Any] = [
            "atr_period": draftAtrPeriod,
            "max_loss_ratio": draftMaxLossRatio
        ]

        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: settings, options: [])
        } catch {
            print("❌ JSON 직렬화 실패:", error)
            return
        }

        // Update app model immediately
        appModel.atrPeriod = draftAtrPeriod
        appModel.maxLossRatio = draftMaxLossRatio

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                print("❌ 저장 실패:", error)
                return
            }
        }.resume()
    }
}
