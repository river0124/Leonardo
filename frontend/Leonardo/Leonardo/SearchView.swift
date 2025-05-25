import SwiftUI

struct SearchView: View {
    @EnvironmentObject var appModel: AppModel
    @Binding var selectedStock: StockItem?
    @State private var searchText: String = ""
    @State private var showChart: Bool = false

    var filteredStocks: [StockInfo] {
        guard searchText.count >= 1 else { return [] }
        return appModel.stockList.filter {
            $0.name.localizedCaseInsensitiveContains(searchText) ||
            $0.code.contains(searchText)
        }
    }

    var body: some View {
        VStack {
            HStack {
                TextField("종목명 혹은 종목코드", text: $searchText, onCommit: {
                    if let first = filteredStocks.first {
                        selectedStock = StockItem(
                            Code: first.code,
                            Name: first.name,
                            CurrentPrice: 0,
                            High52Week: 0,
                            Ratio: 0.0
                        )
                        searchText = "\(first.name) (\(first.code))"
                        showChart = true
                    }
                })
                    .padding(10)
                    .background(Color.gray.opacity(0.1))
                    .cornerRadius(8)

            }
            .padding([.horizontal, .top])

            if !filteredStocks.isEmpty {
                List {
                    ForEach(filteredStocks.prefix(10), id: \.code) { stock in
                        Button(action: {
                            searchText = "\(stock.name) (\(stock.code))"
                            selectedStock = StockItem(
                                Code: stock.code,
                                Name: stock.name,
                                CurrentPrice: 0,
                                High52Week: 0,
                                Ratio: 0.0
                            )
                            showChart = true
                        }) {
                            HStack {
                                Text(stock.name).bold()
                                Spacer()
                                Text(stock.code)
                                    .font(.caption)
                                    .foregroundColor(.gray)
                            }
                        }
                    }
                }
                .frame(maxHeight: 200)
            }

            Spacer()
        }
    }
}
