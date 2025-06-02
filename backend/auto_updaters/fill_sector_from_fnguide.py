import pandas as pd
import requests
from bs4 import BeautifulSoup
import time

def extract_sector_from_fnguide(code):
    url = f"https://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{code}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        info_table = soup.select_one("div.corp_group2")
        if not info_table:
            return None, None

        text = info_table.get_text(separator="|")
        parts = text.split("|")

        sector1 = sector2 = None
        for i, p in enumerate(parts):
            if "업종" in p:
                raw = parts[i + 1].strip()
                sector1 = raw.split(" > ")[0].strip()
                if ">" in raw:
                    sector2 = raw.split(">")[-1].strip()
                break

        return sector1, sector2
    except Exception as e:
        print(f"⚠️ [{code}] 에러 발생: {e}")
        return None, None


def update_sector_info(filepath):
    df = pd.read_csv(filepath, dtype={"Code": str})
    if "Sector1" not in df.columns:
        df["Sector1"] = ""
    if "Sector2" not in df.columns:
        df["Sector2"] = ""

    df["Sector1"] = df["Sector1"].astype(str)
    df["Sector2"] = df["Sector2"].astype(str)

    count = 0
    for i, row in df.iterrows():
        if not pd.isna(row["Sector1"]) and str(row["Sector1"]).strip():
            continue
        if not pd.isna(row["Sector2"]) and str(row["Sector2"]).strip():
            continue
        count += 1

        code = row["Code"]
        name = row["Name"]
        print(f"🔍 {code} {name} → FnGuide에서 조회 중...")
        sector1, sector2 = extract_sector_from_fnguide(code)

        if sector1:
            df.at[i, "Sector1"] = sector1
            df.at[i, "Sector2"] = sector2 if sector2 else ""
            df.to_csv(filepath, index=False)

        time.sleep(1.5)  # 너무 빠르게 크롤링하지 않도록

    df.to_csv(filepath, index=False)
    print("✅ 업데이트 완료!")
    print(f"총 {count}개의 종목이 FnGuide 크롤링 대상입니다.")

# 실행 예시
if __name__ == "__main__":
    CSV_PATH = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
    update_sector_info(CSV_PATH)