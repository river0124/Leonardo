import pandas as pd
import os, sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.abspath(os.path.join(BASE_DIR, '..', '.env'))  # 두 폴더 위로 변경
load_dotenv(dotenv_path=ENV_PATH, override=True)

# 환경변수에서 경로 읽기, 없으면 기본값으로 로컬 경로 지정
CACHE_DIR = os.getenv('CACHE_DIR', '/Users/hyungseoklee/Documents/Leonardo/backend/cache')

HOLIDAY_PATH = os.path.join(CACHE_DIR, 'holidays.csv')
STOCK_LIST_PATH = os.path.join(CACHE_DIR, 'stock_list.csv')

def load_sector_data(sector_path: str) -> pd.DataFrame:
    return pd.read_csv(sector_path, dtype={'Code': str}, usecols=["Code", "Sector1", "Sector2"])

def merge_sector_data(df: pd.DataFrame, df_sector: pd.DataFrame) -> pd.DataFrame:
    df = df.drop(columns=["Sector1", "Sector2"], errors='ignore')
    df = df.merge(df_sector, on="Code", how="left")
    return df

def log_sector_summary(df: pd.DataFrame, logger):
    sector1_counts = df['Sector1'].value_counts(dropna=False)
    sector2_counts = df['Sector2'].value_counts(dropna=False)

    logger.info("📌 섹터1별 종목 수:")
    logger.info(sector1_counts)
    logger.info(f"🔢 총 섹터1 수: {df['Sector1'].nunique(dropna=True)} (NaN 제외)")

    logger.info("📌 섹터2별 종목 수:")
    logger.info(sector2_counts)
    logger.info(f"🔢 총 섹터2 수: {df['Sector2'].nunique(dropna=True)} (NaN 제외)")

    return df

if __name__ == "__main__":
    STOCK_LIST_PATH = os.path.join(CACHE_DIR, "stock_list.csv")
    SECTOR_DATA_PATH = os.path.join(CACHE_DIR, "krx_sector_data_fnguide.csv")
    OUTPUT_PATH = os.path.join(CACHE_DIR, "stock_list_with_sectors.csv")

    # 스톡리스트 로딩
    df_stock = pd.read_csv(STOCK_LIST_PATH, dtype={"Code": str})

    # 섹터 정보 로딩
    df_sector = load_sector_data(SECTOR_DATA_PATH)

    # 병합
    df_merged = merge_sector_data(df_stock, df_sector)

    # 저장
    df_merged.to_csv(OUTPUT_PATH, index=False)
    print(f"✅ 섹터 정보 병합 완료: {OUTPUT_PATH}")