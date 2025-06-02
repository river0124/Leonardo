CACHE_DIR = "/Users/hyungseoklee/Documents/Leonardo/backend/cache"
from loguru import logger
import json
import FinanceDataReader as fdr
import pandas as pd
from tqdm import tqdm
import sys, os
from datetime import datetime, timedelta
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from slack_notifier import post_to_slack

# 📌 강세 섹터 판단 기준 설정
MIN_RISING_COUNT = 4  # 대장주 중 최소 몇 개 이상 상승해야 강세로 간주할지
MIN_AVG_RETURN = 0.03  # 대장주 평균 수익률 기준 (예: 0.03 → 3%)
MIN_PERIOD_DAYS = 20  # 상승 기간 기준 (최근 N 거래일)
REQUIRE_STRONG_WINNER = True  # 대장주 중 하나라도 +5% 이상 수익률이 있어야 하는지 여부
STRONG_WINNER_THRESHOLD = 0.05  # 대장주의 수익률이 이 수치 이상인 것이 있어야 함
MIN_RATIO_TO_HIGH52 = 0.95  # 신고가 대비 최소 근접 비율 (예: 0.98 = 98%)
MAX_RATIO_DIFF_FROM_HIGH52 = 0.5  # 52주 신고가에서 이 비율 이상 벗어난 종목은 제외 (예: 0.10 → 10%)

# Load DEBUG setting
with open(f"{CACHE_DIR}/settings.json") as f:
    settings = json.load(f)
DEBUG = settings.get("DEBUG", "False") == "True"

holidays_path = f"{CACHE_DIR}/holidays.csv"
holidays = pd.read_csv(holidays_path)
holiday_dates = set(pd.to_datetime(holidays['날짜'], format="%Y%m%d").dt.date)

def remove_holidays(df):
    return df.loc[~df.index.to_series().dt.date.isin(holiday_dates)]

def find_52week_high_candidates():
    # KRX 종목 목록 불러오기
    stock_list = fdr.StockListing('KRX')
    stock_list = stock_list[~stock_list['Name'].str.contains('관리|정지|스팩|전환|우$|우[A-Z]?$|우선', regex=True, na=False)]
    stock_list['Close'] = pd.to_numeric(stock_list['Close'], errors='coerce')
    stock_list = stock_list[stock_list['Close'] > 1000]

    # 52주 기간 설정
    end = datetime.today()
    start = end - timedelta(days=365)

    results = []

    for _, row in tqdm(stock_list.iterrows(), total=stock_list.shape[0], desc="🔎 52주 신고가 검색 중"):
        code = row['Code']
        name = row['Name']

        try:
            df = remove_holidays(fdr.DataReader(code, start, end))
            if df.empty or len(df) < 10:
                continue

            current_close = df['Close'].iloc[-1]
            high_52week = df['High'].max()

            # 🔍 현재가가 52주 신고가의 MIN_RATIO_TO_HIGH52 이상이면서 MAX_RATIO_DIFF_FROM_HIGH52 이내인 경우만 포함
            ratio = current_close / high_52week
            if MIN_RATIO_TO_HIGH52 <= ratio and ratio >= (1 - MAX_RATIO_DIFF_FROM_HIGH52):
                results.append({
                    'Code': code,
                    'Name': name,
                    'CurrentPrice': current_close,
                    'High52Week': high_52week,
                    'Ratio': round(ratio * 100, 2)
                })

        except Exception as e:
            if DEBUG: logger.error(f"[{code}] {name}: Error -> {e}")

    df_result = pd.DataFrame(results)
    if not df_result.empty:
        df_result = df_result.sort_values(by='Ratio', ascending=False)
    return df_result


# ✅ 섹터별 대장주 5개 중 최근 5일 간 상승 종목이 3개 이상인 섹터만 필터링

import os

stock_list_path = f"{CACHE_DIR}/stock_list.csv"

# 스톡 리스트 로드
df_stock_info = pd.read_csv(stock_list_path)
df_stock_info = df_stock_info.dropna(subset=['MarketCap', 'Sector'])

# 섹터별 대장주 5개 추출 (시가총액 기준 상위)
top_leaders_by_sector = (
    df_stock_info
    .sort_values(by="MarketCap", ascending=False)
    .groupby("Sector")
    .head(5)
)

# 강세 섹터 판단을 위한 준비
sector_returns = {}

# 최근 6일치 데이터 (당일 포함 5거래일)
# 대표 종목으로부터 가장 최근 거래일 구하기
ref_df = fdr.DataReader("005930", "2024-01-01")
ref_df = remove_holidays(ref_df)
end_date = ref_df.index[-1].date()
start_date = end_date - timedelta(days=MIN_PERIOD_DAYS * 2)  # 주말과 공휴일 포함 여유 확보

# 대장주들의 상승 여부 및 수익률 확인
for _, row in tqdm(top_leaders_by_sector.iterrows(), total=top_leaders_by_sector.shape[0],
                   desc="📊 대장주 상승 체크", ncols=100, dynamic_ncols=False, leave=False, position=0):
    code = str(row["Code"]).zfill(6)
    sector = row["Sector"]
    try:
        df = remove_holidays(fdr.DataReader(code, start_date, end_date.strftime('%Y-%m-%d')))
        df = df.tail(MIN_PERIOD_DAYS + 1)
        if len(df) < MIN_PERIOD_DAYS + 1:
            if DEBUG: logger.warning(f"[{code}] {row['Name']} → 데이터 부족 (len={len(df)})")
            continue

        price_start = df['Close'].iloc[0]
        price_end = df['Close'].iloc[-1]
        ret = (price_end - price_start) / price_start

        sector_returns.setdefault(sector, []).append(ret)

    except Exception as e:
        if DEBUG: logger.error(f"[{code}] {row['Name']} 오류: {e}")

# ✅ 강세 섹터 정의:
# 1) 대장주 MIN_RISING_COUNT개 이상 상승
# 2) 평균 수익률 MIN_AVG_RETURN 이상
# 3) (선택적) 하나 이상의 대장주가 STRONG_WINNER_THRESHOLD 이상 수익을 기록한 경우만 인정 (REQUIRE_STRONG_WINNER=True일 때)
strong_sectors = [
    sector for sector, returns in sector_returns.items()
    if sum(r > 0 for r in returns) >= MIN_RISING_COUNT
       and sum(returns) / len(returns) >= MIN_AVG_RETURN
       and (not REQUIRE_STRONG_WINNER or any(r >= STRONG_WINNER_THRESHOLD for r in returns))
]

# 🔥 상승 중인 강세 섹터 목록 로깅
if DEBUG:
    logger.info(f"🔥 상승 중인 강세 섹터 목록: {strong_sectors}")

def merge_sector_info(df_result, df_stock_info):
    df_result['Code'] = df_result['Code'].astype(str).str.zfill(6)
    df_stock_info['Code'] = df_stock_info['Code'].astype(str).str.zfill(6)
    return df_result.merge(df_stock_info[['Code', 'Sector']], on='Code', how='left')

def filter_by_strong_sector(df_result, strong_sectors):
    return df_result[df_result['Sector'].isin(strong_sectors)]

def filter_small_caps(df_result, df_stock_info):
    df_result = df_result.merge(df_stock_info[['Code', 'Market', 'MarketCap']], on='Code', how='left')
    df_result = df_result[
        ((df_result['Market'] == 'KOSPI') & (df_result['MarketCap'] >= 500000000000)) |
        ((df_result['Market'] == 'KOSDAQ') & (df_result['MarketCap'] >= 300000000000))
    ]
    return df_result

if __name__ == "__main__":
    df_result = find_52week_high_candidates()
    df_result = merge_sector_info(df_result, df_stock_info)

    # 🚫 강세 섹터가 없으면 종료
    if not strong_sectors:
        if DEBUG: logger.info("⚠️ 강세 섹터가 없어 추천을 종료합니다.")
        post_to_slack("⚠️ 강세 섹터가 없어 추천을 종료합니다.")
        exit()

    df_result = filter_by_strong_sector(df_result, strong_sectors)
    df_result = filter_small_caps(df_result, df_stock_info)

    # ✅ 최종 결과 저장
    output_path = f"{CACHE_DIR}/high52.json"
    df_result = df_result.drop(columns=['MarketCap'], errors='ignore')
    df_result.to_json(output_path, orient='records', force_ascii=False, indent=2)
    if DEBUG: logger.success(f"📊 강세 섹터 내 추천 종목 수: {len(df_result)}개")
    post_to_slack(f"✅ 강세 섹터 내 추천 종목 리스트가 저장되었습니다.\n총 종목 수: {len(df_result)}개")