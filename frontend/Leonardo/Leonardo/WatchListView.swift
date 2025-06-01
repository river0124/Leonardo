import SwiftUI

struct WatchStockItem: Identifiable {
    let id: String
    let Code: String
    let Name: String
}

struct WatchListView: View {
    @EnvironmentObject var appModel: AppModel
    @Binding var selectedStock: WatchStockItem?
    @FocusState private var focusedStockID: String?

    var body: some View {
        VStack(alignment: .leading) {
                Text("주시 종목: \(appModel.watchlistCodes.count)종목")
                    .font(.headline)
                    .padding(.horizontal)
            
            List(appModel.watchlistCodes, id: \.self) { code in

                let item = appModel.stockCache[code] ?? WatchStockItem(
                    id: code,
                    Code: code,
                    Name: "로딩 중..."
                )

                Button {
                    selectedStock = item
                    focusedStockID = item.id
                } label: {
                    Text("\(item.Name)(\(item.Code))")
                        .font(.headline)
                        .padding(.vertical, 4)
                        .padding(.horizontal)
                }
                .onAppear {
                    if appModel.stockCache[code] == nil {
                        fetchStockInfo(code: code)
                    }
                }
                .listRowBackground(focusedStockID == item.id ? Color.gray.opacity(0.2) : Color.clear)
                .buttonStyle(PlainButtonStyle())
                .focused($focusedStockID, equals: item.id)
            }
            .listStyle(.plain)
        }
    }

    func fetchStockInfo(code: String) {
        guard let url = URL(string: "http://127.0.0.1:5000/stockname?code=\(code)") else { return }

        URLSession.shared.dataTask(with: url) { data, _, _ in
            guard let data = data else { return }

            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let name = json["name"] as? String {

                    let item = WatchStockItem(
                        id: code,
                        Code: code,
                        Name: name
                    )

                    DispatchQueue.main.async {
                        appModel.stockCache[code] = item
                    }
                }
            } catch {
                print("📛 JSON 파싱 실패: \(error)")
            }
        }.resume()
    }
}
