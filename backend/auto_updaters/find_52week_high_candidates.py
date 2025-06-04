CACHE_DIR = "/Users/hyungseoklee/Documents/Leonardo/backend/cache"

from loguru import logger
import json
import FinanceDataReader as fdr # 이놈은 쓰면 안되겠다 데이터가 정확하지 않아.
import pandas as pd
from tqdm import tqdm
import numpy as np
import sys, os
from datetime import datetime, timedelta
# from get_investor_and_program_trend import get_foreign_institution_trend, get_foreign_net_trend, get_total_trading_volume

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from slack_notifier import post_to_slack


# 📌 강세 섹터 판단 기준 설정
MIN_PERIOD_DAYS = 20  # 상승 기간 기준 (최근 N 거래일)
STRONG_WINNER_THRESHOLD = 0.07  # 대장주의 수익률이 이 수치 이상인 것이 있어야 함
MIN_RATIO_TO_HIGH52 = 0.90  # 신고가 대비 최소 근접 비율 (예: 0.98 = 98%)
MAX_RATIO_DIFF_FROM_HIGH52 = 0.1  # 52주 신고가에서 이 비율 이상 벗어난 종목은 제외 (예: 0.10 → 10%)

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
# sector2 → Sector2, sector1 → Sector1 (if present). Ensure both columns exist.
if 'sector1' in df_stock_info.columns:
    df_stock_info = df_stock_info.rename(columns={"sector1": "Sector1"})
if 'sector2' in df_stock_info.columns:
    df_stock_info = df_stock_info.rename(columns={"sector2": "Sector2"})
# Drop rows missing MarketCap or either Sector1 or Sector2
df_stock_info = df_stock_info.dropna(subset=['MarketCap', 'Sector1', 'Sector2'])

# 섹터 크기 보정: 종목 수 10개 미만 섹터 제외
df_stock_info = df_stock_info.groupby('Sector1').filter(lambda x: len(x) >= 10)
df_stock_info = df_stock_info.groupby('Sector2').filter(lambda x: len(x) >= 10)

# 동적 대장주 개수 결정 함수
def dynamic_top_n(sector_size):
    if sector_size <= 5:
        return sector_size
    elif sector_size <= 15:
        return 3
    elif sector_size <= 30:
        return 5
    else:
        return 7

# 섹터1 기반 대장주 (시가총액 기준 상위, 동적 개수)
top_leaders_by_sector1 = (
    df_stock_info
    .sort_values(by="MarketCap", ascending=False)
    .groupby("Sector1")
    .apply(lambda g: g.head(dynamic_top_n(len(g))))
    .reset_index(drop=True)
)

# 섹터2 기반 대장주 (시가총액 기준 상위, 동적 개수)
top_leaders_by_sector2 = (
    df_stock_info
    .sort_values(by="MarketCap", ascending=False)
    .groupby("Sector2")
    .apply(lambda g: g.head(dynamic_top_n(len(g))))
    .reset_index(drop=True)
)

# 강세 섹터 판단을 위한 준비
sector1_returns = {}
sector2_returns = {}

# 최근 6일치 데이터 (당일 포함 5거래일)
# 대표 종목으로부터 가장 최근 거래일 구하기
ref_df = fdr.DataReader("005930", "2024-01-01")
ref_df = remove_holidays(ref_df)
end_date = ref_df.index[-1].date()
start_date = end_date - timedelta(days=MIN_PERIOD_DAYS * 2)  # 주말과 공휴일 포함 여유 확보

# 섹터1 대장주 상승 체크
for _, row in tqdm(top_leaders_by_sector1.iterrows(), total=top_leaders_by_sector1.shape[0], desc="📊 Sector1 대장주 상승 체크"):
    code = str(row["Code"]).zfill(6)
    sector = row["Sector1"]
    try:
        df = remove_holidays(fdr.DataReader(code, start_date, end_date.strftime('%Y-%m-%d')))
        df = df.tail(MIN_PERIOD_DAYS + 1)
        if len(df) < MIN_PERIOD_DAYS + 1:
            continue
        ret = (df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]
        sector1_returns.setdefault(sector, []).append(ret)
    except:
        continue

# 섹터2 대장주 상승 체크
for _, row in tqdm(top_leaders_by_sector2.iterrows(), total=top_leaders_by_sector2.shape[0], desc="📊 Sector2 대장주 상승 체크"):
    code = str(row["Code"]).zfill(6)
    sector = row["Sector2"]
    try:
        df = remove_holidays(fdr.DataReader(code, start_date, end_date.strftime('%Y-%m-%d')))
        df = df.tail(MIN_PERIOD_DAYS + 1)
        if len(df) < MIN_PERIOD_DAYS + 1:
            continue
        ret = (df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0]
        sector2_returns.setdefault(sector, []).append(ret)
    except:
        continue

# ✅ 강세 섹터 정의 (Sector1, Sector2 각각, 새로운 방식)

# Stricter filtering for Sector1
def calculate_strong_sector1(sector_returns_dict):
    strong_sectors = []
    for sector, returns in sector_returns_dict.items():
        if len(returns) < 2:
            continue
        # Skip if the maximum return is less than 0.03
        if max(returns) < 0.03:
            continue
        avg_return = sum(returns) / len(returns)
        rising_ratio = sum(r > 0 for r in returns) / len(returns)
        strong_ratio = sum(r >= STRONG_WINNER_THRESHOLD for r in returns) / len(returns)
        score = (avg_return * 100) + (rising_ratio * 20) + (strong_ratio * 30) - np.log(len(returns)) * 2
        pass_count = sum([
            avg_return >= 0.04,
            rising_ratio >= 0.7,
            strong_ratio >= 0.35,
            score >= 3.0
        ])
        if pass_count >= 3:
            strong_sectors.append(sector)
    return strong_sectors

# More relaxed for Sector2
def calculate_strong_sector2(sector_returns_dict):
    strong_sectors = []
    for sector, returns in sector_returns_dict.items():
        if len(returns) < 2:
            continue
        # Skip if the maximum return is less than 0.03
        if max(returns) < 0.03:
            continue
        avg_return = sum(returns) / len(returns)
        rising_ratio = sum(r > 0 for r in returns) / len(returns)
        strong_ratio = sum(r >= STRONG_WINNER_THRESHOLD for r in returns) / len(returns)
        score = (avg_return * 100) + (rising_ratio * 20) + (strong_ratio * 30) - np.log(len(returns)) * 2
        pass_count = sum([
            avg_return >= 0.03,
            rising_ratio >= 0.65,
            strong_ratio >= 0.25,
            score >= 2.5
        ])
        if pass_count >= 2:
            strong_sectors.append(sector)
    return strong_sectors

strong_sector1 = calculate_strong_sector1(sector1_returns)
strong_sector2 = calculate_strong_sector2(sector2_returns)

# 🔥 상승 중인 강세 섹터 목록 로깅 (Sector1, Sector2)
if DEBUG:
    logger.info(f"🔥 상승 중인 강세 섹터 목록 - Sector1: {strong_sector1}")
    logger.info(f"🔥 상승 중인 강세 섹터 목록 - Sector2: {strong_sector2}")

def merge_sector_info(df_result, df_stock_info):
    df_result['Code'] = df_result['Code'].astype(str).str.zfill(6)
    df_stock_info['Code'] = df_stock_info['Code'].astype(str).str.zfill(6)
    return df_result.merge(df_stock_info[['Code', 'Sector1', 'Sector2']], on='Code', how='left')

def filter_by_strong_sector(df_result, strong_sector1, strong_sector2):
    return df_result[
        df_result['Sector1'].isin(strong_sector1) |
        df_result['Sector2'].isin(strong_sector2)
    ]

def filter_small_caps(df_result, df_stock_info):
    df_result = df_result.merge(df_stock_info[['Code', 'Market', 'MarketCap']], on='Code', how='left')
    df_result = df_result[
        ((df_result['Market'] == 'KOSPI') & (df_result['MarketCap'] >= 500000000000)) |
        ((df_result['Market'] == 'KOSDAQ') & (df_result['MarketCap'] >= 300000000000))
    ]
    return df_result

# Sector1, Sector2 모두에 속한 종목은 추가 점수를 받아 상위로 정렬되도록 점수화 함수 (점수 방식 변경)
def score_strong_sector(df_result, strong_sector1, strong_sector2):
    def calc_score(row):
        s1 = row['Sector1'] in strong_sector1
        s2 = row['Sector2'] in strong_sector2
        return s1 * 2 + s2 * 2 + (s1 and s2) * 1  # 총점 최대 5점

    df_result['SectorScore'] = df_result.apply(calc_score, axis=1)
    df_result = df_result[df_result['SectorScore'] >= 2.5]
    df_result = df_result.sort_values(by='SectorScore', ascending=False)
    return df_result


if __name__ == "__main__":
    df_result = find_52week_high_candidates()
    df_result = merge_sector_info(df_result, df_stock_info)

    # 🚫 강세 섹터가 없으면 종료
    if not strong_sector1 and not strong_sector2:
        if DEBUG: logger.info("⚠️ 강세 섹터가 없어 추천을 종료합니다.")
        post_to_slack("⚠️ 강세 섹터가 없어 추천을 종료합니다.")
        exit()

    df_result = filter_by_strong_sector(df_result, strong_sector1, strong_sector2)
    df_result = filter_small_caps(df_result, df_stock_info)
    df_result = score_strong_sector(df_result, strong_sector1, strong_sector2)
    df_result = df_result.sort_values(by='SectorScore', ascending=False)
    added_count = len(df_result)
    if DEBUG:
        logger.info(f"✅ 강세 섹터 필터링 후 추가된 종목 수: {added_count}")

    # ✅ 최종 결과 저장
    output_path = f"{CACHE_DIR}/high52.json"
    df_result = df_result.drop(columns=['MarketCap'], errors='ignore')
    df_result.to_json(output_path, orient='records', force_ascii=False, indent=2)
    post_to_slack(f"✅ 강세 섹터 내 추천 종목 리스트가 저장되었습니다.\n"
                  f"Sector1: {len(strong_sector1)}개, Sector2: {len(strong_sector2)}개\n"
                  f"총 종목 수: {len(df_result)}개")