def find_52week_high_candidates():
    import FinanceDataReader as fdr
    from tqdm import tqdm
    import pandas as pd
    from datetime import datetime, timedelta

    stock_list = fdr.StockListing('KRX')
    stock_list = stock_list[~stock_list['Name'].str.contains('관리|정지|스팩|전환|우$|우[A-Z]?$|우선', regex=True, na=False)]
    stock_list['Close'] = pd.to_numeric(stock_list['Close'], errors='coerce')
    stock_list = stock_list[stock_list['Close'] > 1000]

    end = datetime.today()
    start = end - timedelta(days=365)

    excluded_names = []
    results = []

    for _, row in tqdm(stock_list.iterrows(), total=stock_list.shape[0], desc="Processing"):
        code = row['Code']
        name = row['Name']

        df = fdr.DataReader(code, start, end)
        if df.empty or len(df) < 10:
            excluded_names.append(name)
            continue

        recent = df.tail(7)
        if (recent['Volume'] == 0).all() or recent[['Open', 'High', 'Low', 'Close']].nunique().eq(1).all():
            excluded_names.append(name)
            continue

        try:
            high_before_today = df['High'].iloc[:-1].max()
            current_price = df['Close'].iloc[-1]
            ratio = current_price / high_before_today

            if 0.95 <= ratio < 1.0 and current_price < high_before_today:
                results.append({
                    'Code': code,
                    'Name': name,
                    'CurrentPrice': current_price,
                    'High52Week': high_before_today,
                    'Ratio': round(ratio * 100, 2)
                })

        except Exception as e:
            print(f"[{code}] {name}: Error -> {e}")

    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values(by='Ratio', ascending=False)

    return df_result