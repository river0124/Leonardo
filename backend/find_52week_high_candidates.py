def find_52week_high_candidates():
    import FinanceDataReader as fdr
    from tqdm import tqdm
    import pandas as pd
    from datetime import datetime, timedelta
    import requests
    from bs4 import BeautifulSoup

    stock_list = fdr.StockListing('KRX')
    stock_list = stock_list[~stock_list['Name'].str.contains('관리|정지|스팩|전환|우$|우[A-Z]?$|우선', regex=True, na=False)]
    stock_list['Close'] = pd.to_numeric(stock_list['Close'], errors='coerce')
    stock_list = stock_list[stock_list['Close'] > 1000]

    end = datetime.today()
    start = end - timedelta(days=365)

    excluded_names = []
    results = []

    # def is_trading_halted(code):
    #     url = f"https://finance.naver.com/item/main.naver?code={code}"
    #     try:
    #         res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    #         if res.status_code != 200:
    #             return False
    #         soup = BeautifulSoup(res.text, "html.parser")
    #         status_tag = soup.select_one("em.halt")
    #         return status_tag is not None and "거래정지" in status_tag.text
    #     except:
    #         return False

    for _, row in tqdm(stock_list.iterrows(), total=stock_list.shape[0], desc="Processing"):
        code = row['Code']
        name = row['Name']

        df = fdr.DataReader(code, start, end)
        if df.empty or len(df) < 10:
            excluded_names.append(name)
            continue

        # Improved exclusion: stocks with 7 consecutive days of zero volume or no price movement
        recent = df.tail(7)
        if (recent['Volume'] == 0).all() or recent[['Open', 'High', 'Low', 'Close']].nunique().eq(1).all():
            excluded_names.append(name)
            continue

        try:
            # df = fdr.DataReader(code, start, end)
            # if df.empty or len(df) < 10 or df['Close'].iloc[-1] == 0:
            #     excluded_names.append(name)
            #     continue

            high_52week = df['High'].max()
            current_price = df['Close'].iloc[-1]
            ratio = current_price / high_52week

            if ratio >= 0.95:
                results.append({
                    'Code': code,
                    'Name': name,
                    'CurrentPrice': current_price,
                    'High52Week': high_52week,
                    'Ratio': round(ratio * 100, 2)
                })

        except Exception as e:
            print(f"[{code}] {name}: Error -> {e}")

    df_result = pd.DataFrame(results)
    df_result = df_result.sort_values(by='Ratio', ascending=False)

    # if excluded_names:
    #     print("\n🚫 거래 정지 또는 데이터 부족 종목 목록:")
    #     print(excluded_names)

    return df_result