import pandas as pd
import os

# 설정
STOCK_LIST_PATH = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/stock_list.csv"
SECTOR_DB_PATH = "/Users/hyungseoklee/Documents/Leonardo/backend/cache/krx_sector_data.csv"

# 섹터 정보를 가져오는 함수 (크롤링 또는 외부 API 활용)
import requests
from bs4 import BeautifulSoup

def get_sector_from_web(code: str, name: str) -> str:
    import time
    import re

    query = f"{name} {code} 섹터"
    url = f"https://search.naver.com/search.naver?query={query}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"❌ 검색 실패: {query}")
            return ""

        soup = BeautifulSoup(response.text, "html.parser")
        text = soup.get_text()
        candidates = re.findall(r"(전자|금융|조선|의료|바이오|에너지|자동차|IT|게임|반도체|소재|통신|보험|정밀|건설|부동산|유통|제약|소비재|산업재|화학|플랫폼|항공|방산)", text)

        if not candidates:
            print(f"❓ [{code}] {name} → 검색 결과 없음. 섹터를 수동으로 입력해주세요:")
            return input("⤷ 수동 입력: ")

        from collections import Counter
        counter = Counter(candidates)
        top_sectors = counter.most_common(3)
        print(f"🔍 [{code}] {name} → 후보 섹터: {[s[0] for s in top_sectors]}")
        answer = input(f"⤷ 사용할 섹터를 입력하세요 (예: {top_sectors[0][0]}): ")
        return answer.strip()

    except Exception as e:
        print(f"⚠️ 오류 발생: {e}")
        return ""

# 기존 섹터 데이터 로드
if os.path.exists(SECTOR_DB_PATH):
    df_sector = pd.read_csv(SECTOR_DB_PATH, dtype={"Code": str})
else:
    df_sector = pd.DataFrame(columns=["Code", "Sector1"])

# 스톡 리스트 로드
df_stock = pd.read_csv(STOCK_LIST_PATH, dtype={"Code": str})
missing_sector_df = df_stock[df_stock["Sector"].isna()].copy()

if missing_sector_df.empty:
    print("✅ 모든 종목에 섹터 정보가 있습니다.")
else:
    print(f"🔍 섹터 정보가 비어있는 종목 수: {len(missing_sector_df)}")
    for _, row in missing_sector_df.iterrows():
        code = row["Code"]
        name = row["Name"]
        sector = get_sector_from_web(code, name)
        if sector and not df_sector[df_sector["Code"] == code].any().any():
            new_row = pd.DataFrame([{"Code": code, "Sector1": sector}])
            df_sector = pd.concat([df_sector, new_row], ignore_index=True)
            df_sector.to_csv(SECTOR_DB_PATH, index=False)
            print(f"✅ 섹터 정보 저장 완료: {code} | {sector}")
    print("ℹ️ 섹터 정보 입력이 완료되었습니다.")