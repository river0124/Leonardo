import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re

def get_active_stock_codes():
    stock_list_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
    try:
        df = pd.read_csv(stock_list_path, dtype={"Code": str})
        return df["Code"].unique().tolist()
    except Exception as e:
        print(f"⚠️ stock_list.csv 로딩 에러: {e}")
        return []

def extract_sector_from_fnguide(code):
    url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{code}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        span_fics = soup.select_one("#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt2")
        span_sector1 = soup.select_one("#compBody > div.section.ul_corpinfo > div.corp_group1 > p > span.stxt.stxt1")
        if span_sector1:
            sector1_raw = span_sector1.text.strip()
            sector1 = re.sub(r"^(KSE|KQ|코스피|코스닥)\s+", "", sector1_raw)  # Remove prefixes like 'KSE', 'KQ', '코스피', '코스닥'
            sector1 = sector1.replace("\xa0", " ").replace(" ", " ").strip()
            sector1 = re.sub(r'\s+', ' ', sector1)
            if sector1 in ["KSE", "KQ", "코스피", "코스닥", ""]:
                sector1 = None
        else:
            sector1 = None
        if span_fics:
            sector2 = span_fics.text.strip().replace("FICS", "").strip()
            sector2 = sector2.replace("\xa0", " ").replace(" ", " ").strip()
            sector2 = re.sub(r'\s+', ' ', sector2)
            return sector1, sector2
        return sector1, None
    except Exception as e:
        print(f"⚠️ [{code}] 에러 발생: {e}")
        return None, None


def update_sector_info(filepath):
    active_codes = get_active_stock_codes()
    df = pd.read_csv(filepath, dtype={"Code": str})
    df = df[df["Code"].isin(active_codes)].copy()
    if "Sector1" not in df.columns:
        df["Sector1"] = ""
    if "Sector2" not in df.columns:
        df["Sector2"] = ""

    df["Sector1"] = df["Sector1"].astype(str)
    df["Sector2"] = df["Sector2"].astype(str)

    total = len(df)
    count = 0
    for i, row in df.iterrows():
        invalid_values = ["", "nan", "-", "NaN"]
        if str(row["Sector1"]).strip() not in invalid_values:
            continue
        count += 1

        code = row["Code"]
        name = row["Name"]
        print(f"\r🔍 [{count}/{total}] {code} {name} → 추출 중... ", end="", flush=True)
        sector1, sector2 = extract_sector_from_fnguide(code)
        print(f"\r📝 [{count}/{total}] {code} | Sector1: {sector1}, Sector2: {sector2}", end="", flush=True)

        if sector1:
            df.at[i, "Sector1"] = sector1
            df.at[i, "Sector2"] = sector2 if sector2 else ""
            df.to_csv(filepath, index=False)

            # Also update krx_sector_data.csv
            sector_path = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/krx_sector_data_fnguide.csv"
            try:
                df_sector = pd.read_csv(sector_path, dtype={"Code": str})
            except FileNotFoundError:
                df_sector = pd.DataFrame(columns=["Code", "Sector1", "Sector2"])

            existing = df_sector[df_sector["Code"] == code]
            if not existing.empty:
                df_sector.loc[df_sector["Code"] == code, "Sector1"] = sector1
                df_sector.loc[df_sector["Code"] == code, "Sector2"] = sector2 if sector2 else ""
            else:
                df_sector = pd.concat([
                    df_sector,
                    pd.DataFrame([{
                        "Code": code,
                        "Sector1": sector1,
                        "Sector2": sector2 if sector2 else ""
                    }])
                ], ignore_index=True)

            df_sector.to_csv(sector_path, index=False)
            print(f"💾 {code} → {sector_path}에 저장됨 (Sector1: {sector1}, Sector2: {sector2})")

        time.sleep(1.5)  # 너무 빠르게 크롤링하지 않도록

    print("✅ 업데이트 완료!")
    print(f"총 {count}개의 종목이 FnGuide 크롤링 대상입니다.")

def refresh_all_sector_info(filepath):
    active_codes = get_active_stock_codes()
    df = pd.read_csv(filepath, dtype={"Code": str})
    df = df[df["Code"].isin(active_codes)].copy()
    if "Sector1" not in df.columns:
        df["Sector1"] = ""
    if "Sector2" not in df.columns:
        df["Sector2"] = ""

    df["Sector1"] = df["Sector1"].astype(str)
    df["Sector2"] = df["Sector2"].astype(str)

    # print(f"🔁 상위 10개 종목 섹터2 (FICS) 갱신 시작")
    for i, row in df.iterrows():
        code = row["Code"]
        # print(f"🔄 {code} → FnGuide에서 전체 갱신 중...")
        print(f"\r🔍 [{i+1}/{len(df)}] {code} → 추출 중...", end="", flush=True)
        prev_sector1 = row["Sector1"]
        prev_sector2 = row["Sector2"]
        sector1, sector2 = extract_sector_from_fnguide(code)

        print(f"\r📝 [{i+1}/{len(df)}] {code} | 이전: ({prev_sector1}, {prev_sector2}) → 새로: ({sector1 if sector1 else prev_sector1}, {sector2 if sector2 else prev_sector2})", end="", flush=True)
        if sector1:
            df.at[i, "Sector1"] = sector1
        if sector2:
            df.at[i, "Sector2"] = sector2
        df.to_csv(filepath, index=False)

        time.sleep(1.5)

    updated_count = df["Sector1"].apply(lambda x: x.strip() != "").sum()
    print(f"✅ 전체 섹터 정보 갱신 완료! ({updated_count}개 항목)")

# 실행 예시
if __name__ == "__main__":
    CSV_PATH = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
    update_sector_info(CSV_PATH)

#전체 갱신을 원할 경우 주석을 해제하세요:
#refresh_all_sector_info("/Users/hyungseoklee/Documents/Leonardo/backend/cache/krx_sector_data_fnguide.csv")