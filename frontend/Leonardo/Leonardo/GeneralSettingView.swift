//
//  GeneralSettingView.swift
//  Leonardo
//
//  Created by Hyung Seok Lee on 5/26/25.
//



import SwiftUI

struct GeneralSettingView: View {
    var body: some View {
        VStack {
            Spacer()

            Button(action: {
                print("저장 버튼 눌림")
            }) {
                Text("저장")
                    .padding(.horizontal, 40)
                    .padding(.vertical, 10)
                    .background(Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(8)
            }

            Spacer()
        }
    }
}

#Preview {
    GeneralSettingView()
}
