//
//  LeonardoApp.swift
//  Leonardo
//
//  Created by Hyung Seok Lee on 5/21/25.
//

import SwiftUI

@main
struct LeonardoApp: App {
    @StateObject private var appModel = AppModel()

    var body: some Scene {
        WindowGroup {
            MainView()
                .environmentObject(appModel)
                .onAppear {
                    appModel.fetchWatchlist()  // 시작 시 주시목록 불러오기
                }
        }
    }
}
