import pandas as pd
import FinanceDataReader as fdr
import datetime

DEBUG_PRINT = 0  # 1 to enable prints, 0 to disable

def get_candle_chart_data(code):
    """
    주어진 종목 코드(code)에 대해 약 400일간 일봉 데이터를 가져와
    날짜, 시가, 고가, 저가, 종가, 거래량 정보를 포함하는 리스트를 반환한다.
    """
    try:
        end_date = datetime.datetime.today()
        start_date = end_date - datetime.timedelta(days=400)
        df = fdr.DataReader(code, start_date, end_date)

        df = df.reset_index()
        df['Date'] = pd.to_datetime(df['Date'])

        if DEBUG_PRINT:
            print(f"✅ 가져온 일봉 데이터 수: {len(df)}")
            print(df.head())

        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')

        # Load holiday dates
        holidays_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/holidays.csv"
        holidays_df = pd.read_csv(holidays_path, encoding="utf-8-sig")
        holidays_list = set(pd.to_datetime(holidays_df["날짜"]).dt.date)

        # Filter out weekends and holidays
        df['Weekday'] = pd.to_datetime(df['Date']).dt.weekday
        df = df[~df['Weekday'].isin([5, 6])]  # Remove Saturdays and Sundays
        df = df[~pd.to_datetime(df['Date']).dt.date.isin(holidays_list)]   # Remove holidays

        candles = []
        for _, row in df.iterrows():
            if row['Open'] == 0 and row['High'] == 0 and row['Low'] == 0 and row['Close'] == 0:
                continue  # 유효하지 않은 데이터는 제외
            candles.append({
                "date": row['Date'],
                "open": row['Open'],
                "high": row['High'],
                "low": row['Low'],
                "close": row['Close'],
                "volume": int(row['Volume'])
            })

        return {"code": code, "candles": candles}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    from pprint import pprint

    result = get_candle_chart_data("005930")
    pprint(result)