
from loguru import logger
import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
import os
from tqdm import tqdm


logger.remove()  # Remove default console handler
logger.add("../logs/generate_daily_price.log", rotation="10 MB", encoding="utf-8", enqueue=True, backtrace=True, diagnose=True)

# 설정
metadata_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
output_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/daily_price.csv"
start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")  # 3개월

if not os.path.exists(metadata_path):
    logger.error(f"❌ 파일 없음: {metadata_path}")
    exit(1)

# stock_metadata.csv에서 종목 코드 로드
df_meta = pd.read_csv(metadata_path, dtype={"Code": str})
codes = df_meta["Code"].tolist()

# 데이터 수집
all_data = []
for code in tqdm(codes, desc="📈 가격 데이터 수집 중", unit="종목"):
    try:
        price_df = fdr.DataReader(code, start_date)
        price_df = price_df.reset_index()[["Date", "Close"]]
        price_df["Code"] = code
        all_data.append(price_df)
    except Exception as e:
        logger.warning(f"❌ {code} 실패: {e}")

pd.concat(all_data)[["Code", "Date", "Close"]].to_csv(output_path, index=False); logger.info(f"✅ 저장 완료: {output_path}")