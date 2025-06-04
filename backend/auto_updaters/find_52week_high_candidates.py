CACHE_DIR = "/Users/hyungseoklee/Documents/Leonardo/backend/cache"

from loguru import logger
import json
import FinanceDataReader as fdr # 이놈은 쓰면 안되겠다 데이터가 정확하지 않아.
import pandas as pd
from tqdm import tqdm
import numpy as np
import sys, os
from datetime import datetime, timedelta
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from get_total_data_for_candidates import get_foreign_institution_trend,get_foreign_net_trend
from utils import KoreaInvestAPI, KoreaInvestEnv
from settings import cfg
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

stock_list_path = f"{CACHE_DIR}/stock_list_with_sectors.csv"

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

def get_foreign_institution_trend(stock_code):
    original_mode = settings.get("is_paper_trading", True)

    if original_mode:
        cfg["is_paper_trading"] = False
    else:
        # logger.info("현재는 실전투자 상태입니다.")
        pass

    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    response = api.summarize_foreign_institution_estimates(stock_code)
    response_json = response.json()
    output2 = response_json.get("output2", [])

    if output2:
        # 시간대 기준으로 내림차순 정렬
        latest = max(output2, key=lambda x: int(x["bsop_hour_gb"]))
        frgn = int(latest["frgn_fake_ntby_qty"])
        orgn = int(latest["orgn_fake_ntby_qty"])

        return {"외국인": frgn, "기관": orgn}
    else:
        return {"외국인": 0, "기관": 0}

def get_foreign_net_trend(stock_code):
    original_mode = settings.get("is_paper_trading", True)

    if original_mode:
        cfg["is_paper_trading"] = False
    else:
        # logger.info("현재는 실전투자 상태입니다.")
        pass

    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    response = api.summarize_foreign_net_estimates(stock_code)
    response_json = response.json()
    output = response_json.get("output", [])

    if output:
        # 시간대 기준으로 내림차순 정렬
        latest = max(output, key=lambda x: int(x["bsop_hour"]))
        glob_ntby_qty = int(latest["glob_ntby_qty"])
        return {"외국계": glob_ntby_qty}
    else:
        return {"외국계": 0}

def get_total_trading_data(stock_code):
    env = KoreaInvestEnv(cfg)
    api = KoreaInvestAPI(cfg, env.get_base_headers())

    response = api.get_current_price(stock_code)
    output = response["output"][0] if isinstance(response.get("output"), list) else response

    # 누적거래량 추출 및 매핑
    acml_vol = output.get("acml_vol")

    try:
        return {"누적거래량": int(acml_vol)} if acml_vol is not None else {"누적거래량": 0}
    except ValueError:
        return {"누적거래량": 0}

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

    # ✅ 외국인, 기관, 외국계 매수량 데이터 수집 및 추가
    foreign_orgn_list = []
    foreign_net_list = []
    volume_list = []

    for _, row in tqdm(df_result.iterrows(), total=len(df_result), desc="🌍 외국인/기관/외국계 매수량 조회 중"):
        code = row["Code"]
        try:
            trend = get_foreign_institution_trend(code)
            # 필터: 외국인 또는 기관 순매수 음수면 제외
            if trend["외국인"] < 0 or trend["기관"] < 0:
                # logger.debug(f"[FILTERED] {code} 제외됨 - 외국인 또는 기관 순매수 음수")
                continue
            # 필터: 주석으로 제거 가능
            time.sleep(0.4)
            net = get_foreign_net_trend(code)
            time.sleep(0.4)
            volume = get_total_trading_data(code)
            time.sleep(0.4)
        except Exception as e:
            logger.warning(f"[{code}] 외국인/기관/외국계 데이터 조회 실패: {e}")
            trend = {"외국인": 0, "기관": 0}
            net = {"외국계": 0}
            volume = {"누적거래량": 0}

        foreign_orgn_list.append(trend)
        foreign_net_list.append(net)
        volume_list.append(volume)

    # 리스트를 DataFrame으로 변환하고 df_result에 병합
    df_foreign_orgn = pd.DataFrame(foreign_orgn_list)
    df_foreign_net = pd.DataFrame(foreign_net_list)
    df_volume = pd.DataFrame(volume_list)
    df_result = pd.concat([df_result.reset_index(drop=True), df_foreign_orgn, df_foreign_net, df_volume], axis=1)

    def refined_score(row):
        total_volume = row["누적거래량"]
        if total_volume <= 0:
            return 0

        score = 0
        weights = {}

        # ✅ 1. 개별 주체 스코어링
        for key in ["기관", "외국인", "외국계"]:
            buy = row.get(key, 0)
            ratio = max(0, buy / total_volume)
            multiplier = 1.0
            if key == "외국인" and row.get("Market") == "KOSPI":
                multiplier = 1.2
            weights[key] = min(3, round(np.log1p(ratio) * 5 * multiplier, 2)) if buy > 0 else 0
            score += weights[key]

        # ✅ 2. 양매수 조건
        orgn_buy = row.get("기관", 0)
        frgn_buy = row.get("외국인", 0)
        if orgn_buy > 10000000 and frgn_buy > 10000000:
            score += 2
        elif orgn_buy > 0 and frgn_buy > 0:
            score += 1
        elif orgn_buy > 0 or frgn_buy > 0:
            score += 0.5

        # ✅ 3. 총매수 강도
        total_buy = max(0, orgn_buy + frgn_buy + row.get("외국계", 0))
        ratio = total_buy / total_volume
        score += min(3.0, round(np.log1p(ratio * 100), 2))

        return round(score, 3)

    df_result["BuyStrengthScore"] = df_result.apply(refined_score, axis=1)
    df_result = df_result.sort_values(by="BuyStrengthScore", ascending=False)
    df_result_top10 = df_result.head(10)

    # ✅ 최종 결과 저장
    output_path = f"{CACHE_DIR}/high52.json"
    df_result = df_result.drop(columns=['MarketCap'], errors='ignore')
    logger.info(f"📦 최종 저장할 종목 수: {len(df_result)}개")
    df_result.to_json(output_path, orient='records', force_ascii=False, indent=2)
    post_to_slack(f"✅ 강세 섹터 내 추천 종목 리스트가 저장되었습니다.\n"
                  f"Sector1: {len(strong_sector1)}개, Sector2: {len(strong_sector2)}개\n"
                  f"총 종목 수: {len(df_result)}개")

    top10_path = f"{CACHE_DIR}/high52_top10.json"
    df_result_top10.to_json(top10_path, orient='records', force_ascii=False, indent=2)
    # 🏅 상위 추천 종목 리스트 (Top 10)
    message = ["🏅 상위 추천 종목 리스트 (Top 10):"]

    for idx, row in df_result_top10.iterrows():
        total_volume = row.get('누적거래량', 0)
        frgn = row.get('외국인', 0)
        orgn = row.get('기관', 0)
        glob = row.get('외국계', 0)

        def pct(value):
            return f"{value:,} ({(value / total_volume * 100):.1f}%)" if total_volume > 0 else f"{value:,} (0%)"

        msg = (
            f"{row['Name']} ({row['Code']}): "
            f"Score = {row['BuyStrengthScore']} | "
            f"외국인 = {pct(frgn)}, 기관 = {pct(orgn)}, 외국계 = {pct(glob)}"
        )
        logger.info(msg)
        message.append(msg)

    post_to_slack("\n".join(message))