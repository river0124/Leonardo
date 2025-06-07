import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from slack_notifier import post_to_slack  # ✅ 슬랙 전송 모듈

from dotenv import load_dotenv
from loguru import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '.env'))  # 두 폴더 위로 변경
load_dotenv(dotenv_path=ENV_PATH, override=True)

CACHE_DIR = os.getenv('CACHE_DIR')

HOLIDAY_PATH = os.path.join(CACHE_DIR, 'holidays.csv')
STOCK_LIST_PATH = os.path.join(CACHE_DIR, 'stock_list.csv')

import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from tqdm import tqdm

def get_active_stock_codes():
    stock_list_path = os.path.join(CACHE_DIR, "stock_list.csv")
    try:
        df = pd.read_csv(stock_list_path, dtype={"Code": str})
        return df["Code"].unique().tolist()
    except Exception as e:
        logger.info(f"⚠️ stock_list.csv 로딩 에러: {e}")
        return []

def extract_sector_from_fnguide(code):
    url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{code}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        span_fics = soup.select_one("#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt2")
        span_sector1 = soup.select_one("#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt1")
        # print(f"🔍 [DEBUG] Raw span_sector1 text for {code}: {span_sector1.text.strip() if span_sector1 else 'None'}")
        # print(f"🔍 [DEBUG] Raw span_fics text for {code}: {span_fics.text.strip() if span_fics else 'None'}")
        if span_sector1:
            sector1_raw = span_sector1.text.strip()
            sector1 = sector1_raw.replace("코스피", "").replace("코스닥", "").replace("KOSPI", "").replace("KOSDAQ", "")
            sector1 = re.sub(r"^(KSE|KQ)\s*", "", sector1)
            sector1 = sector1.replace("\xa0", " ").replace(" ", " ").strip()
            sector1 = re.sub(r'\s+', ' ', sector1)
            if sector1 in ["KSE", "KQ", "", "-", "nan", "NaN"]:
                sector1 = ""
        else:
            sector1 = ""
        if span_fics:
            sector2 = span_fics.text.strip().replace("FICS", "").strip()
            sector2 = sector2.replace("\xa0", " ").replace(" ", " ").strip()
            sector2 = re.sub(r'\s+', ' ', sector2)
            sector2 = sector2 if sector2 else ""
            return sector1, sector2
        sector2 = ""
        return sector1, sector2
    except Exception as e:
        logger.info(f"⚠️ [{code}] 에러 발생: {e}")
        return None, None


def refresh_all_sector_info(filepath):
    active_codes = get_active_stock_codes()
    df = pd.read_csv(filepath, usecols=["Code", "Sector1", "Sector2"], dtype={"Code": str})
    # --- 동기화: stock_list.csv와 섹터 파일의 코드 일치 ---
    stock_list_path = os.path.join(CACHE_DIR, "stock_list.csv")
    try:
        df_stock_list = pd.read_csv(stock_list_path, dtype={"Code": str})
    except Exception as e:
        logger.info(f"⚠️ stock_list.csv 로딩 실패: {e}")
        return

    stock_codes_set = set(df_stock_list["Code"].unique())
    sector_codes_set = set(df["Code"].unique())

    codes_to_remove = sector_codes_set - stock_codes_set
    codes_to_add = stock_codes_set - sector_codes_set
    if codes_to_remove:
        logger.info(f"🗑️ 제거된 종목 수: {len(codes_to_remove)}")
        logger.info("🗑️ 제거된 종목 목록:", sorted(codes_to_remove))
    if codes_to_add:
        logger.info(f"➕ 추가된 종목 수: {len(codes_to_add)}")
        logger.info("➕ 추가된 종목 목록:", sorted(codes_to_add))
    if not codes_to_remove and not codes_to_add:
        logger.info("✅ 변화 없음: 종목 추가/제거가 없습니다.")

    # Remove outdated codes
    if codes_to_remove:
        df = df[~df["Code"].isin(codes_to_remove)]

    # Add new codes
    if codes_to_add:
        new_rows = df_stock_list[df_stock_list["Code"].isin(codes_to_add)][["Code"]].copy()
        new_rows["Sector1"] = ""
        new_rows["Sector2"] = ""
        df = pd.concat([df, new_rows], ignore_index=True)
        # print(f"➕ 추가된 종목 수: {len(codes_to_add)}")  # Removed duplicate print statement

    if "Sector1" not in df.columns:
        df["Sector1"] = ""
    if "Sector2" not in df.columns:
        df["Sector2"] = ""

    df["Sector1"] = df["Sector1"].astype(str)
    df["Sector2"] = df["Sector2"].astype(str)

    update_targets = df[
        (df["Sector1"].str.strip().isin(["", "nan", "NaN", "-", "None"])) |
        (df["Sector2"].str.strip().isin(["", "nan", "NaN", "-", "None"]))
    ].reset_index(drop=True)
    total_updates = len(update_targets)

    logger.info(f"🔢 총 {total_updates}개의 종목이 업데이트 대상입니다.")

    for i, row in tqdm(update_targets.iterrows(), total=len(update_targets), desc="📊 진행률", unit="종목"):
        code = row["Code"]
        prev_sector1 = row["Sector1"]
        prev_sector2 = row["Sector2"]
        sector1, sector2 = extract_sector_from_fnguide(code)
        # Clean sector1
        if sector1:
            sector1 = sector1.replace("코스피", "").replace("코스닥", "").replace("KOSPI", "").replace("KOSDAQ", "")
            sector1 = re.sub(r"^(KSE|KQ)\s*", "", sector1)
            sector1 = sector1.replace("\xa0", " ").replace(" ", " ").strip()
            sector1 = re.sub(r'\s+', ' ', sector1)
            if sector1 in ["KSE", "KQ", "", "-", "nan", "NaN", None]:
                sector1 = ""

        if sector1:
            df.loc[df["Code"] == code, "Sector1"] = sector1
        if sector2:
            df.loc[df["Code"] == code, "Sector2"] = sector2
        df["Sector1"] = df["Sector1"].apply(lambda x: "" if str(x).strip() in ["KSE", "KQ", "", "-", "nan", "NaN", "None"] else x)
        df["Sector2"] = df["Sector2"].apply(lambda x: "" if str(x).strip() in ["KSE", "KQ", "", "-", "nan", "NaN", "None"] else x)

        time.sleep(1.5)

    updated_count = total_updates
    logger.info(f"✅ 전체 섹터 정보 갱신 완료! ({total_updates}개 종목)")
    post_to_slack(f"✅ 전체 섹터 정보 갱신 완료! ({total_updates}개 종목)")

# 실행 예시
if __name__ == "__main__":
    CSV_PATH = os.path.join(CACHE_DIR, "krx_sector_data_fnguide.csv")
    refresh_all_sector_info(CSV_PATH)

#전체 갱신을 원할 경우 주석을 해제하세요:
# refresh_all_sector_info(os.path.join(CACHE_DIR, "krx_sector_data_fnguide.csv"))