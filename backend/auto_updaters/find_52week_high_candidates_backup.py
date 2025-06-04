from loguru import logger
import time
import pandas as pd
import json
import get_total_data_for_candidates as td
import FinanceDataReader as fdr
import pandas as pd
from tqdm import tqdm
import numpy as np
import sys, os
from datetime import datetime, timedelta


MIN_RATIO_TO_HIGH52 = 0.92  # 신고가 대비 최소 근접 비율 (예: 0.98 = 98%)
MAX_RATIO_DIFF_FROM_HIGH52 = 0.05  # 52주 신고가에서 이 비율 이상 벗어난 종목은 제외 (예: 0.10 → 10%)

CACHE_DIR = "/Users/hyungseoklee/Documents/Leonardo/backend/cache"

def get_total_data_for_candidates():
    start_time = time.time()
    with open("/Users/hyungseoklee/Documents/Leonardo/backend/cache/elements_map.json", "r", encoding="utf-8") as map_file:
        element_map = json.load(map_file)

    stock_list_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
    df = pd.read_csv(stock_list_path)
    stock_name_map = dict(zip(df["Code"].astype(str).str.zfill(6), df["Name"]))
    candidates = {}

    tqdm_bar = tqdm(df.iterrows(), total=len(df), desc="📈 후보 종목 스캔 중", dynamic_ncols=True)
    for _, row in tqdm_bar:
        elapsed_time = time.time() - start_time
        if elapsed_time >= 60:
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            time_str = f"{minutes}분 {seconds}초"
        else:
            time_str = f"{elapsed_time:.2f}초"
        tqdm_bar.set_description(f"📈 후보 종목 스캔 중 | ⏱️ 경과: {time_str}")
        code = str(row["Code"]).zfill(6)
        stock_name = stock_name_map.get(code, "")
        try:
            data = td.get_total_trading_data(code)
            rate = data.get("52주 최고가 대비 현재가 비율")
            time.sleep(0.5)
            if rate is not None:
                rate = float(rate)
                high52 = data.get("52주 최고가")
                current_price = data.get("현재가")
                if high52 and current_price:
                    ratio = float(current_price) / float(high52)
                    upper_limit = 1.0 + MAX_RATIO_DIFF_FROM_HIGH52
                    if MIN_RATIO_TO_HIGH52 <= ratio <= upper_limit:
                        candidates[code] = data

                        institution_trend_data = td.get_foreign_institution_trend(code)
                        if institution_trend_data:
                            for key, value in institution_trend_data.items():
                                if key not in data:
                                    data[key] = value
                        time.sleep(0.5)

                        foreign_net_trend_data = td.get_foreign_net_trend(code)
                        if foreign_net_trend_data:
                            for key, value in foreign_net_trend_data.items():
                                if key not in data:
                                    data[key] = value
                        time.sleep(0.5)

        except Exception as e:
            logger.info(f"❌ {code} 처리 중 오류 발생: {e}")

    logger.info(candidates)

    # 필요한 필드만 추출하여 저장
    filtered_candidates = {}
    for code, data in candidates.items():
        stock_name = stock_name_map.get(code, "")
        filtered_candidates[code] = {
            '종목명': stock_name,
            '현재가': data.get('현재가'),
            '52주 최고가': data.get('52주 최고가'),
            '52주 최고일자': data.get('52주 최고일자'),
            '52주 최고가 대비 현재가 비율': data.get('52주 최고가 대비 현재가 비율'),
            '누적거래량': data.get('누적거래량'),
            '외국인매수량': data.get('외국인'),
            '기관매수량': data.get('기관'),
            '외국계매수량': data.get('외국계')
        }

    with open("/Users/hyungseoklee/Documents/Leonardo/backend/cache/high52.json", "w", encoding="utf-8") as f:
        json.dump(filtered_candidates, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 총 {len(filtered_candidates)}개 종목이 high52.json에 저장되었습니다.")
    logger.info(f"⏱️ 저장까지 총 소요 시간: {time.time() - start_time:.2f}초")

if __name__ == "__main__":
    get_total_data_for_candidates()