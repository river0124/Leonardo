import FinanceDataReader as fdr
import json
import sys

def get_code_by_name(name):
    try:
        df = fdr.StockListing('KRX')
        name = name.strip()
        # 1차: 정확히 일치하는 경우
        exact_match = df[df['Name'] == name]
        if not exact_match.empty:
            code = exact_match.iloc[0]['Code']
            return {"code": code, "message": "✅ 정확히 일치하는 종목입니다."}

        # 2차: 부분 문자열 일치하는 경우
        partial_match = df[df['Name'].str.contains(name) & (df['Name'] != name)]
        if not partial_match.empty:
            code = partial_match.iloc[0]['Code']
            return {"code": code, "warning": "⚠️ 정확히 일치하지 않는 유사 종목입니다."}

        return {"error": "❌ 해당 종목명을 찾을 수 없습니다."}
    except Exception as e:
        return {"error": str(e)}

def main():
    try:
        stock_name = input().strip()
        result = get_code_by_name(stock_name)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == "__main__":
    main()