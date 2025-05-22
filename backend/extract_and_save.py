# extract_and_save.py

import sys
from save_candle_chart import save_chart
from extract_vector import extract_vector
from pattern_db import save_pattern_vector
import FinanceDataReader as fdr

def main():
    if len(sys.argv) != 5:
        print("❌ 인자 오류: [code] [start] [end] [category]")
        return

    code = sys.argv[1]
    start = sys.argv[2]
    end = sys.argv[3]
    category = sys.argv[4]

    try:
        df = fdr.DataReader(code)
        img_path = save_chart(df, code, start, end)
        vector = extract_vector(img_path)

        label = f"{category}_{code}_{start}_{end}"
        save_pattern_vector(label, vector)

        print(f"✅ 저장 완료: {label}")

    except Exception as e:
        print(f"❌ 처리 중 오류 발생: {e}")

if __name__ == "__main__":
    main()