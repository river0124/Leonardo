import FinanceDataReader as fdr
import pandas as pd
import json

def calculate_atr(stock_code: str, period: int = 20, return_only: bool = False):
    df = fdr.DataReader(stock_code)
    if df is None or len(df) < period + 1:
        error_msg = {"error": f"❌ 데이터가 부족합니다: {stock_code}"}
        if return_only:
            return None
        else:
            print(json.dumps(error_msg))
            return
    df["H-L"] = df["High"] - df["Low"]
    df["H-PC"] = abs(df["High"] - df["Close"].shift(1))
    df["L-PC"] = abs(df["Low"] - df["Close"].shift(1))
    df["TR"] = df[["H-L", "H-PC", "L-PC"]].max(axis=1)
    df["ATR"] = df["TR"].rolling(window=period).mean()

    atr_value = df["ATR"].iloc[-1]

    if return_only:
        return atr_value
    else:
        print(json.dumps({"code": stock_code, "atr": f"{atr_value:.2f}"}))

if __name__ == "__main__":
    try:
        stock_code = input().strip()
        period = int(input().strip())
        calculate_atr(stock_code, period)
    except Exception as e:
        print(json.dumps({"error": str(e)}))