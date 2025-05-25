//
//  GeneralSettingView.swift
//  Leonardo
//
//  Created by Hyung Seok Lee on 5/26/25.
//

import SwiftUI

struct GeneralSettingView: View {
    @ObservedObject var appModel = AppModel.shared
    @State private var showConfirmation = false
    @State private var pendingToggleValue = true
    @State private var originalPaperTrading = true

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            
            Text("일반설정")
                .font(.title)
                .bold()
                .padding(.bottom, 10)
            
            HStack {
                Text("실전투자")
                    .foregroundColor(.gray)

                if appModel.isSettingsLoaded {
                    Toggle("", isOn: Binding(
                        get: { appModel.isPaperTrading },
                        set: { newValue in
                            if appModel.isPaperTrading && !newValue {
                                pendingToggleValue = newValue
                                showConfirmation = true
                            } else {
                                appModel.isPaperTrading = newValue
                            }
                        })
                    )
                    .toggleStyle(SwitchToggleStyle(tint: .gray))
                    .labelsHidden()
                    .scaleEffect(0.8)
                    .alert("실전투자로 전환하시겠습니까?", isPresented: $showConfirmation) {
                        Button("취소", role: .cancel) {}
                        Button("확인") {
                            appModel.isPaperTrading = pendingToggleValue
                        }
                    }
                } else {
                    ProgressView().frame(height: 20)
                }

                Text("모의투자")
                    .foregroundColor(.gray)
            }
            .padding(.horizontal)
            
            HStack(alignment: .center){
                Spacer()
                Button(action: {
                    if let url = URL(string: "http://127.0.0.1:5051/settings") {
                        var request = URLRequest(url: url)
                        request.httpMethod = "POST"
                        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                        let body = ["is_paper_trading": appModel.isPaperTrading]
                        request.httpBody = try? JSONSerialization.data(withJSONObject: body, options: [])
                        
                        URLSession.shared.dataTask(with: request) { _, response, error in
                            if let error = error {
                                print("❌ 설정 저장 실패: \(error)")
                            } else if let httpResponse = response as? HTTPURLResponse {
                                print("✅ 설정 저장 상태 코드: \(httpResponse.statusCode)")
                                DispatchQueue.main.async {
                                    appModel.loadSettings()
                                    appModel.loadTotalAssetFromSummary()
                                    appModel.loadWatchlist()
                                    appModel.loadStockList()
                                    originalPaperTrading = appModel.isPaperTrading
                                }
                            }
                        }.resume()
                    }
                }) {
                    Text("저장")
                }
                .disabled(appModel.isPaperTrading == originalPaperTrading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .onAppear {
            appModel.loadSettings()
            originalPaperTrading = appModel.isPaperTrading
        }
        .onChange(of: appModel.isSettingsLoaded) { _, newValue in
            if newValue {
                originalPaperTrading = appModel.isPaperTrading
            }
        }
        Spacer()
    }
}

#Preview {
    GeneralSettingView()
}
